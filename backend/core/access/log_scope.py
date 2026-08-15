"""P1.13A — Log scope architecture (platform / workspace / company).

Strict separation, enforced in the backend (never only frontend filtering):

* PLATFORM logs live in their own collection (``platform_logs``) and only ever
  contain platform-level events (client.created, client_admin.replaced, support
  actions, platform config...). They MUST NOT become an aggregate stream of
  client operational events (invoice created, TB imported, report generated...).
* WORKSPACE / COMPANY logs live in the existing tenant-scoped ``logs``
  collection and are always filtered by the caller's workspace_id (no cross-
  client leak). Company logs additionally filter by company_id.

Meelora platform staff may only read a specific client's logs by entering that
client's context (a workspace_id must be supplied by an authorized platform
actor); there is no "all customer logs" screen.
"""
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from fastapi import HTTPException

_now = lambda: datetime.now(timezone.utc).isoformat()

# Event types (and prefixes) that belong to the PLATFORM scope.
PLATFORM_EVENT_TYPES = {
    "client.created", "client.activated", "client.deactivated",
    "client_admin.linked", "client_admin.replaced", "client_admin.deactivated",
    "platform.login", "platform.config", "support.action",
}
_PLATFORM_PREFIXES = ("platform.", "client.", "client_admin.", "support.")


def classify_scope(event_type: Optional[str], company_id: Optional[str] = None) -> str:
    et = event_type or ""
    if et in PLATFORM_EVENT_TYPES or et.startswith(_PLATFORM_PREFIXES):
        return "platform"
    return "company" if company_id else "workspace"


def public_platform_log(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id", "")),
        "scope": "platform",
        "event_type": doc.get("event_type"),
        "actor_user_id": doc.get("actor_user_id"),
        "actor_email": doc.get("actor_email", ""),
        "target_workspace_id": doc.get("target_workspace_id"),
        "label": doc.get("label", ""),
        "details": doc.get("details", ""),
        "metadata": dict(doc.get("metadata") or {}),
        "timestamp": doc.get("timestamp"),
    }


def _require_platform(user: dict) -> None:
    if user.get("platform_role") not in ("platform_admin", "support"):
        raise HTTPException(status_code=403, detail="Réservé au personnel plateforme")


async def write_platform_log(db, user: dict, *, event_type: str, label: str,
                             target_workspace_id: Optional[str] = None, details: str = "",
                             metadata: Optional[dict[str, Any]] = None) -> dict:
    """Append one platform-scoped event. Kept physically separate from tenant logs."""
    if classify_scope(event_type) != "platform":
        raise HTTPException(status_code=422, detail=f"Type d'évènement non plateforme: {event_type}")
    doc = {
        "_id": f"plog_{uuid.uuid4().hex}",
        "event_type": event_type,
        "actor_user_id": user.get("id"),
        "actor_email": user.get("email", ""),
        "target_workspace_id": target_workspace_id,
        "label": label,
        "details": details,
        "metadata": metadata or {},
        "timestamp": _now(),
    }
    await db.platform_logs.insert_one(doc)
    return public_platform_log(doc)


async def list_platform_logs(db, user: dict, *, target_workspace_id: Optional[str] = None,
                             limit: int = 300) -> list[dict]:
    _require_platform(user)
    limit = max(1, min(int(limit or 300), 1000))
    query: dict[str, Any] = {}
    if target_workspace_id:
        query["target_workspace_id"] = target_workspace_id
    docs = await db.platform_logs.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
    return [public_platform_log(d) for d in docs]


async def list_workspace_logs(db, user: dict, *, company_id: Optional[str] = None,
                              limit: int = 300) -> list[dict]:
    """Tenant-scoped operational logs. Never returns platform-scoped events and
    always constrained to the caller's own workspace (no cross-client leak)."""
    from ..logs import public_log  # reuse existing tenant log shape
    workspace_id = user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=403, detail="Contexte workspace requis")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    limit = max(1, min(int(limit or 300), 1000))
    query: dict[str, Any] = {"workspace_id": workspace_id}
    if company_id is not None:
        query["company_id"] = company_id
    docs = await db.logs.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
    # Defense-in-depth: never surface a platform-classified event via tenant logs.
    return [public_log(d) for d in docs
            if classify_scope(d.get("event_type"), d.get("company_id")) != "platform"]


async def ensure_indexes(db) -> None:
    await db.platform_logs.create_index([("timestamp", -1)], name="idx_platform_log_ts")
    await db.platform_logs.create_index([("target_workspace_id", 1)], name="idx_platform_log_ws")
