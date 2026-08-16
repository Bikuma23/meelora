"""P1.13F — Sensitive financial permission enforcement.

Thin route-level guard that cables real sensitive financial actions onto the
central ``resolve_effective_access`` resolver. Every sensitive action verifies,
in one place and fail-closed:

    module access  +  explicit sensitive permission  +  company scope
    +  active company membership  +  company active status

``manage`` (module level) or admin role NEVER implies a sensitive permission —
the resolver requires an explicit grant. No financial calculation is touched.

Denied attempts emit a STRUCTURED security event (``security.sensitive_denied``)
with volume protection (identical denials are coalesced within a 60s window).
The event carries NO financial data — only actor, company, permission and reason.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .effective_access import resolve_effective_access

# Denial reason -> HTTP status. cross_workspace / unknown company are no-leak 404;
# everything else is a fail-closed 403.
_NOT_FOUND_REASONS = {"cross_workspace"}
_DEDUP_WINDOW_SECONDS = 60


async def _record_sensitive_denial(db, user: dict, company_id: str, permission: str, reason: str):
    """Structured, volume-protected security event. Never raises (audit must not
    break the request). No financial data is stored — only access metadata."""
    try:
        now = datetime.now(timezone.utc)
        window_start = (now - timedelta(seconds=_DEDUP_WINDOW_SECONDS)).isoformat()
        key = {"event_type": "security.sensitive_denied", "actor_id": user.get("id"),
               "company_id": company_id, "permission": permission, "reason": reason}
        existing = await db.security_events.find_one({**key, "last_at": {"$gte": window_start}})
        if existing:
            await db.security_events.update_one(
                {"_id": existing["_id"]},
                {"$inc": {"count": 1}, "$set": {"last_at": now.isoformat()}})
            return
        await db.security_events.insert_one({
            "_id": f"sec_{uuid.uuid4().hex}", "severity": "warning",
            "workspace_id": user.get("workspace_id"),
            "actor_id": user.get("id"), "actor_email": user.get("email"),
            "company_id": company_id, "permission": permission, "reason": reason,
            "count": 1, "first_at": now.isoformat(), "last_at": now.isoformat(),
            **{"event_type": "security.sensitive_denied"}})
    except Exception:
        pass


async def require_module_level(db, user: dict, company_id: str, module: str,
                               required_level: str = "contribute", *, workspace_id: str = None) -> dict:
    """Non-sensitive module access gate (e.g. draft/submit require ACCOUNTING
    write). Same fail-closed scope/membership/active checks; no permission needed."""
    ws = workspace_id or user.get("workspace_id")
    res = await resolve_effective_access(
        db, user, workspace_id=ws, company_id=company_id, module=module, required_level=required_level)
    if not res.get("allowed"):
        reason = res.get("reason")
        if reason in _NOT_FOUND_REASONS:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
        raise HTTPException(status_code=403, detail=f"Accès {module} insuffisant : {reason}")
    return res


async def require_sensitive_permission(db, user: dict, company_id: str, permission: str,
                                       *, workspace_id: str = None) -> dict:
    ws = workspace_id or user.get("workspace_id")
    res = await resolve_effective_access(
        db, user, workspace_id=ws, company_id=company_id, permission=permission)
    if not res.get("allowed"):
        reason = res.get("reason")
        await _record_sensitive_denial(db, user, company_id, permission, reason)
        if reason in _NOT_FOUND_REASONS:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
        raise HTTPException(
            status_code=403,
            detail=f"Action sensible refusée ({permission}) : {reason}")
    return res
