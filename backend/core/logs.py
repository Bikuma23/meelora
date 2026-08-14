"""Tenant-aware immutable log service for Meelora V2 Foundation (P1.6)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import re
import uuid

from fastapi import HTTPException

from .permissions import require_tenant_context


def _slug(value: str) -> str:
    text = (value or "event").strip().lower()
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i", "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u", "ç": "c",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "event"


def build_event_type(action: str, entity: str) -> str:
    """Stable machine-friendly event type derived from legacy labels."""
    return f"{_slug(entity)}.{_slug(action)}"


def public_log(doc: dict) -> dict:
    """Return the read-only log payload exposed to administrators."""
    return {
        "id": str(doc.get("_id", "")),
        "workspace_id": doc.get("workspace_id"),
        "user_id": doc.get("user_id"),
        "user_email": doc.get("user_email", ""),
        "user_name": doc.get("user_name", ""),
        "company_id": doc.get("company_id"),
        "mandate_id": doc.get("mandate_id"),
        "event_type": doc.get("event_type"),
        "entity_type": doc.get("entity_type") or doc.get("entity"),
        "entity_id": doc.get("entity_id"),
        "severity": doc.get("severity", "info"),
        "action": doc.get("action", ""),
        "entity": doc.get("entity", ""),
        "label": doc.get("label", ""),
        "details": doc.get("details", ""),
        "changes": list(doc.get("changes") or []),
        "metadata": dict(doc.get("metadata") or {}),
        "timestamp": doc.get("timestamp"),
    }


def _actor_id(user: dict) -> Optional[str]:
    return user.get("id") or user.get("_id")


async def write_log(
    db,
    user: dict,
    *,
    action: str,
    entity: str,
    label: str,
    details: str = "",
    changes: Optional[list] = None,
    company_id: Optional[str] = None,
    mandate_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: str = "info",
    metadata: Optional[dict[str, Any]] = None,
) -> dict:
    """Append one immutable tenant-aware log event.

    New application code should call this service directly. The legacy
    ``log_action`` wrapper remains during the strangler migration and delegates
    here so existing modules gain workspace scoping without being rewritten.
    """
    workspace_id = user.get("workspace_id")
    # System/background legacy calls may not yet carry a workspace. Keep them
    # loggable during P1.6, but never expose them through tenant-scoped /logs.
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": f"log_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "user_id": _actor_id(user),
        "user_email": user.get("email", "système"),
        "user_name": user.get("name", ""),
        "company_id": company_id,
        "mandate_id": mandate_id,
        "event_type": event_type or build_event_type(action, entity),
        "entity_type": _slug(entity),
        "entity_id": entity_id,
        "severity": severity,
        "action": action,
        "entity": entity,
        "label": label,
        "details": details,
        "changes": changes or [],
        "metadata": metadata or {},
        "timestamp": now,
    }
    await db.logs.insert_one(doc)
    return doc


async def list_logs_for_admin(
    db,
    user: dict,
    *,
    limit: int = 300,
    company_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[dict]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    workspace_id = require_tenant_context(user)
    limit = max(1, min(int(limit or 300), 1000))
    query: dict[str, Any] = {"workspace_id": workspace_id}
    if company_id:
        query["company_id"] = company_id
    if event_type:
        query["event_type"] = event_type
    if severity:
        query["severity"] = severity
    docs = await db.logs.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
    return [public_log(d) for d in docs]
