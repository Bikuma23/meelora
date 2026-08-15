"""P1.13C — Access administration & lifecycle governance (service layer).

Backend governance for the future User & Access Management UI. Composes the
P1.13A resolver + P1.13B lifecycle; it NEVER duplicates access logic and NEVER
grants access from an email match alone (fail-closed). No financial behavior.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import HTTPException

from .activation import create_activation_token, public_activation, revoke_user_sessions
from .effective_access import resolve_effective_access
from .entitlements import is_module_enabled_for_company, is_module_entitled
from .module_access import get_user_module_level, list_user_permissions
from .modules import list_modules
from .permissions_catalog import PERMISSION_MODULE

_now = lambda: datetime.now(timezone.utc)
_VERIFIED_IDENTITY = {"active"}  # identity_status values considered verified


# ---------------------------------------------------------------------------
# Identity reuse (security check from P1.13B)
# ---------------------------------------------------------------------------
def identity_is_verified(user: Optional[dict]) -> bool:
    """A stored identity counts as verified only if explicitly active. An
    UNVERIFIED existing identity must never gain access from an email match —
    it must first prove control via the one-time activation flow."""
    if not user:
        return False
    return (user.get("identity_status") or ("active" if user.get("password_hash") or user.get("auth_provider") == "google" else "pending_verification")) in _VERIFIED_IDENTITY


# ---------------------------------------------------------------------------
# Invitation journal / lifecycle
# ---------------------------------------------------------------------------
def invitation_status(doc: dict) -> str:
    raw = doc.get("status")
    if raw == "used":
        return "accepted"
    if raw in ("revoked", "expired"):
        return raw
    # pending — derive expiry lazily
    try:
        if datetime.fromisoformat(doc.get("expires_at")) < _now():
            return "expired"
    except Exception:
        return "expired"
    return "pending"


def public_invitation(doc: dict) -> dict:
    """Admin-facing invitation view. NEVER exposes the raw/hashed token."""
    intent = doc.get("intent") or {}
    return {
        "id": doc.get("_id"),
        "email": doc.get("email"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": intent.get("company_id"),
        "purpose": doc.get("purpose"),
        "intended": {"type": intent.get("type"),
                     "role": intent.get("role"),
                     "membership_type": intent.get("membership_type")},
        "invited_by": doc.get("created_by"),
        "created_at": doc.get("created_at"),
        "expires_at": doc.get("expires_at"),
        "status": invitation_status(doc),
        "accepted_at": doc.get("used_at"),
        "revoked_at": doc.get("revoked_at"),
    }


async def list_invitations(db, workspace_id: str, status: Optional[str] = None) -> list[dict]:
    rows = await db.client_admin_activations.find({"workspace_id": workspace_id}).to_list(None)
    out = [public_invitation(r) for r in rows]
    if status:
        out = [i for i in out if i["status"] == status]
    out.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return out


async def _load_invitation(db, workspace_id: str, invitation_id: str) -> dict:
    doc = await db.client_admin_activations.find_one({"_id": invitation_id, "workspace_id": workspace_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    return doc


async def get_invitation(db, workspace_id: str, invitation_id: str) -> dict:
    return public_invitation(await _load_invitation(db, workspace_id, invitation_id))


async def revoke_invitation(db, workspace_id: str, invitation_id: str, actor_id: str) -> dict:
    doc = await _load_invitation(db, workspace_id, invitation_id)
    if doc.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Seule une invitation en attente peut être révoquée")
    await db.client_admin_activations.update_one(
        {"_id": invitation_id}, {"$set": {"status": "revoked", "revoked_at": _now().isoformat(),
                                          "revoked_by": actor_id}})
    return public_invitation(await _load_invitation(db, workspace_id, invitation_id))


async def resend_invitation(db, workspace_id: str, invitation_id: str, actor_id: str,
                            ttl_hours: int = 48) -> dict:
    """Revoke the old token (making it unusable) and issue a fresh one with the
    same target. Returns {invitation, activation_token}."""
    doc = await _load_invitation(db, workspace_id, invitation_id)
    if invitation_status(doc) == "accepted":
        raise HTTPException(status_code=409, detail="Invitation déjà acceptée")
    await db.client_admin_activations.update_one(
        {"_id": invitation_id}, {"$set": {"status": "revoked", "revoked_at": _now().isoformat(),
                                          "revoked_by": actor_id, "resent": True}})
    activation, raw = await create_activation_token(
        db, workspace_id, doc.get("email"), purpose=doc.get("purpose"), actor_id=actor_id,
        ttl_hours=ttl_hours, user_id=doc.get("user_id"), intent=doc.get("intent"))
    return {"invitation": public_activation(activation) | {"status": "pending"},
            "activation_token": raw}


# ---------------------------------------------------------------------------
# User / membership admin views
# ---------------------------------------------------------------------------
async def _user_by_id(db, user_id: str) -> Optional[dict]:
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if doc:
            return doc
    except Exception:
        pass
    return await db.users.find_one({"_id": user_id}) or await db.users.find_one({"id": user_id})


def _identity_view(user: dict) -> dict:
    return {
        "id": str(user.get("_id") or user.get("id")),
        "email": user.get("email"),
        "name": user.get("name", ""),
        "identity_status": user.get("identity_status") or user.get("status", "active"),
        "status": user.get("status", "active"),
        "platform_role": user.get("platform_role"),
        "auth_provider": user.get("auth_provider"),
    }


async def list_workspace_users(db, workspace_id: str) -> list[dict]:
    users = await db.users.find({"workspace_id": workspace_id}).to_list(None)
    out = []
    for u in users:
        uid = str(u["_id"])
        ws_m = await db.workspace_memberships.find_one({"workspace_id": workspace_id, "user_id": uid})
        cm = await db.company_memberships.find({"workspace_id": workspace_id, "user_id": uid}).to_list(None)
        out.append({
            "identity": _identity_view(u),
            "workspace_membership": ({"role": ws_m.get("role"), "status": ws_m.get("status")} if ws_m else None),
            "company_memberships": [{"company_id": m.get("company_id"), "membership_type": m.get("membership_type"),
                                     "role": m.get("role"), "status": m.get("status")} for m in cm],
        })
    out.sort(key=lambda x: x["identity"].get("email") or "")
    return out


async def get_user_admin_view(db, workspace_id: str, user_id: str) -> dict:
    user = await _user_by_id(db, user_id)
    if not user or user.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    uid = str(user["_id"])
    ws_m = await db.workspace_memberships.find_one({"workspace_id": workspace_id, "user_id": uid})
    cm = await db.company_memberships.find({"workspace_id": workspace_id, "user_id": uid}).to_list(None)
    companies = []
    for m in cm:
        matrix = await module_access_matrix(db, workspace_id, m.get("company_id"), user)
        companies.append({"company_id": m.get("company_id"), "membership_type": m.get("membership_type"),
                          "role": m.get("role"), "status": m.get("status"), "modules": matrix})
    return {
        "identity": _identity_view(user),
        "workspace_membership": ({"role": ws_m.get("role"), "status": ws_m.get("status")} if ws_m else None),
        "companies": companies,
    }


# ---------------------------------------------------------------------------
# Module-access administrative representation (single source: the resolver)
# ---------------------------------------------------------------------------
def _user_ctx(user: dict) -> dict:
    return {"id": str(user.get("_id") or user.get("id")),
            "status": user.get("status", "active"),
            "identity_status": user.get("identity_status")}


async def module_access_matrix(db, workspace_id: str, company_id: str, user: dict) -> list[dict]:
    ctx = _user_ctx(user)
    perms_all = await list_user_permissions(db, workspace_id, company_id, ctx["id"])
    out = []
    for m in list_modules():
        code = m["code"]
        entitled = await is_module_entitled(db, workspace_id, code)
        enabled = await is_module_enabled_for_company(db, workspace_id, company_id, code)
        assigned = await get_user_module_level(db, workspace_id, company_id, ctx["id"], code)
        # Effective level derived ONLY via resolve_effective_access.
        effective = "none"
        for lvl in ("manage", "contribute", "read"):
            r = await resolve_effective_access(db, ctx, workspace_id=workspace_id,
                                               company_id=company_id, module=code, required_level=lvl)
            if r["allowed"]:
                effective = lvl
                break
        out.append({
            "module_code": code,
            "entitled": entitled,
            "company_enabled": enabled,
            "assigned_level": assigned,
            "effective_level": effective,
            "sensitive_permissions": [p for p in perms_all if PERMISSION_MODULE.get(p) == code],
        })
    return out


# ---------------------------------------------------------------------------
# Effective-access explanation (admin diagnostic)
# ---------------------------------------------------------------------------
_REASON_FR = {
    "identity_inactive": "identité non active",
    "no_workspace_context": "contexte workspace manquant",
    "no_company_context": "contexte société manquant",
    "cross_workspace": "société hors du workspace (aucune fuite)",
    "no_company_membership": "aucune appartenance active à la société",
    "unknown_module": "module inconnu",
    "unknown_permission": "permission inconnue",
    "module_not_entitled": "module non souscrit par le workspace",
    "module_not_enabled_for_company": "module désactivé pour la société",
    "module_access_insufficient": "niveau d'accès module insuffisant",
    "permission_not_granted": "permission sensible non attribuée",
    "group_not_in_scope": "groupe de consolidation hors périmètre",
    "member": "appartenance société active",
    "granted": "accès accordé",
}


async def explain_effective_access(db, user: dict, *, workspace_id: str, company_id: str,
                                    module: Optional[str] = None, permission: Optional[str] = None,
                                    required_level: str = "read", group_id: Optional[str] = None) -> dict:
    ctx = _user_ctx(user)
    res = await resolve_effective_access(db, ctx, workspace_id=workspace_id, company_id=company_id,
                                         module=module, permission=permission,
                                         required_level=required_level, group_id=group_id)
    factors = [{"check": k, "value": v} for k, v in (res.get("checks") or {}).items()]
    return {
        "allowed": res["allowed"],
        "reason_code": res["reason"],
        "reason": _REASON_FR.get(res["reason"], res["reason"]),
        "module": res.get("module"),
        "permission": res.get("permission"),
        "required_level": required_level,
        "factors": factors,
    }


# ---------------------------------------------------------------------------
# Identity lifecycle (suspend / disable / reactivate) with session revocation
# ---------------------------------------------------------------------------
IDENTITY_STATUSES = {"pending_verification", "active", "suspended", "disabled"}


async def set_identity_status(db, workspace_id: str, user_id: str, status: str, actor_id: str) -> dict:
    if status not in IDENTITY_STATUSES:
        raise HTTPException(status_code=422, detail=f"Statut d'identité invalide: {status}")
    user = await _user_by_id(db, user_id)
    if not user or user.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    now = _now().isoformat()
    # Suspended/disabled block all access; use the existing status gate + revoke JWTs.
    account_status = "active" if status == "active" else "inactive"
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"identity_status": status, "status": account_status,
                                        "identity_status_updated_at": now, "identity_status_by": actor_id}})
    if status in ("suspended", "disabled"):
        await revoke_user_sessions(db, str(user["_id"]))
    return {"user_id": str(user["_id"]), "identity_status": status, "status": account_status}


# ---------------------------------------------------------------------------
# Client Admin replacement visibility
# ---------------------------------------------------------------------------
async def company_admin_history(db, workspace_id: str, company_id: str) -> dict:
    active_admins = await db.company_memberships.find(
        {"workspace_id": workspace_id, "company_id": company_id,
         "membership_type": "company_user", "role": "admin", "status": "active"}).to_list(None)
    previous = await db.company_memberships.find(
        {"workspace_id": workspace_id, "company_id": company_id,
         "membership_type": "company_user", "role": "admin", "status": "inactive"}).to_list(None)
    replacements = await db.platform_logs.find(
        {"event_type": "client_admin.replaced", "metadata.company_id": company_id}).to_list(None)
    replacements.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    async def _uinfo(m):
        uid = m.get("user_id")
        u = await _user_by_id(db, uid) if uid else None
        return {"membership_id": m.get("_id"), "user_id": uid, "email": (u or {}).get("email")}
    return {
        "current_admins": [await _uinfo(m) for m in active_admins],
        "previous_admins": [await _uinfo(m) for m in previous],
        "replacements": [{
            "date": r.get("timestamp"),
            "actor_user_id": r.get("actor_user_id"),
            "new_email": (r.get("metadata") or {}).get("new_email"),
            "old_user_id": (r.get("metadata") or {}).get("old_user_id"),
            "reused_identity": (r.get("metadata") or {}).get("reused_identity"),
        } for r in replacements],
    }
