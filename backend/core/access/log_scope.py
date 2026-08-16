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

# Secrets that must NEVER be persisted/returned in an audit log (defense in depth).
_REDACT_KEYS = {
    "password", "password_hash", "pwd", "hash", "jwt", "token", "access_token",
    "refresh_token", "activation_token", "invite_token", "secret", "api_key",
    "apikey", "credentials", "authorization", "session", "cookie",
}


def _redact(md: Optional[dict]) -> dict:
    """Strip secret-bearing keys from metadata (audit ≠ secret store)."""
    if not isinstance(md, dict):
        return {}
    out = {}
    for k, v in md.items():
        if str(k).strip().lower() in _REDACT_KEYS:
            out[str(k)] = "[redacted]"
        elif isinstance(v, dict):
            out[str(k)] = _redact(v)
        else:
            out[str(k)] = v
    return out

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
    md = _redact(doc.get("metadata") or {})
    et = doc.get("event_type") or ""
    return {
        "id": str(doc.get("_id", "")),
        "scope": "platform",
        "event_type": et,
        "category": doc.get("category") or md.get("category") or (et.split(".")[0] if et else "autre"),
        "actor_user_id": doc.get("actor_user_id"),
        "actor_email": doc.get("actor_email", ""),
        "actor_platform_role": doc.get("actor_platform_role") or md.get("actor_platform_role"),
        "target_workspace_id": doc.get("target_workspace_id"),
        "target_user_id": doc.get("target_user_id") or md.get("target_user_id"),
        "resource": doc.get("resource") or md.get("resource"),
        "action": doc.get("action") or md.get("action"),
        "result": doc.get("result") or md.get("result"),
        "reason": doc.get("reason") or md.get("reason"),
        "ip": doc.get("ip") or md.get("ip"),
        "user_agent": doc.get("user_agent") or md.get("user_agent"),
        "request_id": doc.get("request_id") or md.get("request_id"),
        "before": md.get("before"),
        "after": md.get("after"),
        "label": doc.get("label", ""),
        "details": doc.get("details", ""),
        "metadata": md,
        "timestamp": doc.get("timestamp"),
    }


def _require_platform(user: dict) -> None:
    if user.get("platform_role") not in ("platform_admin", "support"):
        raise HTTPException(status_code=403, detail="Réservé au personnel plateforme")


async def write_platform_log(db, user: dict, *, event_type: str, label: str,
                             target_workspace_id: Optional[str] = None, details: str = "",
                             metadata: Optional[dict[str, Any]] = None) -> dict:
    """Append one platform-scoped event. Kept physically separate from tenant
    logs. Secrets are redacted before persistence. Writing is a server-internal
    action; READING is gated by platform role (see list_platform_logs)."""
    if classify_scope(event_type) != "platform":
        raise HTTPException(status_code=422, detail=f"Type d'évènement non plateforme: {event_type}")
    md = _redact(metadata or {})
    doc = {
        "_id": f"plog_{uuid.uuid4().hex}",
        "event_type": event_type,
        "category": md.get("category") or (event_type.split(".")[0] if event_type else "autre"),
        "actor_user_id": user.get("id"),
        "actor_email": user.get("email", ""),
        "actor_platform_role": user.get("platform_role"),
        "target_workspace_id": target_workspace_id,
        "label": label,
        "details": details,
        "result": md.get("result", "success"),
        "metadata": md,
        "timestamp": _now(),
    }
    await db.platform_logs.insert_one(doc)
    return public_platform_log(doc)


async def list_platform_logs(db, user: dict, *, target_workspace_id: Optional[str] = None,
                             q: Optional[str] = None, event_type: Optional[str] = None,
                             actor: Optional[str] = None, category: Optional[str] = None,
                             result: Optional[str] = None, date_from: Optional[str] = None,
                             date_to: Optional[str] = None, limit: int = 300) -> list[dict]:
    _require_platform(user)
    limit = max(1, min(int(limit or 300), 1000))
    query: dict[str, Any] = {}
    if target_workspace_id:
        query["target_workspace_id"] = target_workspace_id
    if event_type:
        query["event_type"] = event_type
    if category:
        query["category"] = category
    # ISO-8601 strings sort lexicographically -> safe range filter on timestamp.
    if date_from or date_to:
        ts: dict[str, Any] = {}
        if date_from:
            ts["$gte"] = date_from
        if date_to:
            ts["$lte"] = date_to if len(date_to) > 10 else date_to + "T23:59:59.999999+00:00"
        query["timestamp"] = ts
    docs = await db.platform_logs.find(query).sort("timestamp", -1).limit(1000).to_list(1000)
    out = [public_platform_log(d) for d in docs]
    if result:
        out = [e for e in out if (e.get("result") or "").lower() == result.lower()]
    if actor:
        a = actor.lower()
        out = [e for e in out if a in (e.get("actor_email") or "").lower() or a in (e.get("actor_user_id") or "").lower()]
    if q:
        ql = q.lower()
        def _hit(e):
            hay = " ".join(str(e.get(k) or "") for k in (
                "event_type", "category", "actor_email", "actor_user_id", "target_workspace_id",
                "target_user_id", "resource", "action", "result", "reason", "ip", "user_agent",
                "request_id", "label", "details"))
            hay += " " + " ".join(f"{k}={v}" for k, v in (e.get("metadata") or {}).items())
            return ql in hay.lower()
        out = [e for e in out if _hit(e)]
    return out[:limit]


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
