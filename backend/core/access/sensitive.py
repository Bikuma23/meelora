"""P1.13F — Sensitive financial permission enforcement.

Thin route-level guard that cables real sensitive financial actions onto the
central ``resolve_effective_access`` resolver. Every sensitive action verifies,
in one place and fail-closed:

    module access  +  explicit sensitive permission  +  company scope
    +  active company membership  +  company active status

``manage`` (module level) or admin role NEVER implies a sensitive permission —
the resolver requires an explicit grant. No financial calculation is touched.
"""
from fastapi import HTTPException

from .effective_access import resolve_effective_access

# Denial reason -> HTTP status. cross_workspace / unknown company are no-leak 404;
# everything else is a fail-closed 403.
_NOT_FOUND_REASONS = {"cross_workspace"}


async def require_sensitive_permission(db, user: dict, company_id: str, permission: str,
                                       *, workspace_id: str = None) -> dict:
    ws = workspace_id or user.get("workspace_id")
    res = await resolve_effective_access(
        db, user, workspace_id=ws, company_id=company_id, permission=permission)
    if not res.get("allowed"):
        reason = res.get("reason")
        if reason in _NOT_FOUND_REASONS:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
        raise HTTPException(
            status_code=403,
            detail=f"Action sensible refusée ({permission}) : {reason}")
    return res
