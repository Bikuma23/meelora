"""P1.13B — User lifecycle & Client Admin replacement (service layer).

Invitation → one-time activation → membership provisioning, plus the end-to-end
Client Admin replacement flow. Strict rules:

* No permanent password is ever set or visible by an admin. The invited user
  sets their own password when consuming a single-use, expiring token.
* An existing identity is reused when the email matches (identity key).
* Activation provisions an ORGANIZATIONAL membership only — NEVER module access
  or sensitive permissions (no automatic financial access).
* Financial data / formulas are never touched here.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from ..memberships import (
    create_company_membership,
    upsert_workspace_membership,
    validate_combo,
)
from .activation import (
    consume_activation_token,
    create_activation_token,
    peek_activation_token,
)
from .module_access import set_user_module_access, set_user_permission
from .entitlements import is_module_entitled

_now = lambda: datetime.now(timezone.utc).isoformat()


def _norm(email: str) -> str:
    return (email or "").strip().lower()


async def _find_user_by_email(db, email: str) -> Optional[dict]:
    return await db.users.find_one({"email": _norm(email)})


def _validate_intent(intent: dict) -> None:
    t = (intent or {}).get("type")
    if t == "workspace_member":
        if intent.get("role") not in ("admin", "user"):
            raise HTTPException(status_code=422, detail="Rôle workspace invalide")
    elif t == "company_member":
        if not intent.get("company_id"):
            raise HTTPException(status_code=422, detail="company_id requis pour l'invitation société")
        validate_combo(intent.get("membership_type"), intent.get("role"))
    else:
        raise HTTPException(status_code=422, detail=f"Type d'invitation inconnu: {t}")


async def invite_user(db, *, actor_id: str, workspace_id: str, email: str,
                      purpose: str, intent: dict, ttl_hours: int = 48) -> dict:
    """Create an invitation (single-use activation token) for a new OR existing
    identity. Returns the public activation + the raw token (delivered by the
    caller via email / returned to the inviting admin)."""
    _validate_intent(intent)
    norm = _norm(email)
    if not norm:
        raise HTTPException(status_code=422, detail="Email requis")
    existing = await _find_user_by_email(db, norm)
    reused_user_id = str(existing["_id"]) if existing else None
    activation, raw = await create_activation_token(
        db, workspace_id, norm, purpose=purpose, actor_id=actor_id,
        ttl_hours=ttl_hours, user_id=reused_user_id, intent=intent)
    return {"activation": activation, "activation_token": raw,
            "reused_identity": bool(reused_user_id)}


async def preview_activation(db, raw_token: str) -> dict:
    """Non-consuming validation for the activation page."""
    return await peek_activation_token(db, raw_token)


async def invite_user_full(db, *, actor_id: str, workspace_id: str, email: str,
                           name: Optional[str] = None, companies: list,
                           access: Optional[list] = None, permissions: Optional[list] = None,
                           ttl_hours: int = 48) -> dict:
    """Full-wizard invitation: one or more companies + planned module levels +
    explicit sensitive permissions. The planned access is stored on the invitation
    and applied ONLY at activation (after the invitee proves email control). An
    unentitled module can never be planned (rejected here, fail-closed)."""
    norm = _norm(email)
    if not norm:
        raise HTTPException(status_code=422, detail="Email requis")
    if not companies:
        raise HTTPException(status_code=422, detail="Au moins une société est requise")
    for c in companies:
        if not c.get("company_id"):
            raise HTTPException(status_code=422, detail="company_id requis")
        validate_combo(c.get("membership_type", "company_user"), c.get("role", "user"))
    for a in (access or []):
        if a.get("access_level") not in ("none", "read", "contribute", "manage"):
            raise HTTPException(status_code=422, detail="Niveau d'accès invalide")
        if a.get("access_level") != "none" and not await is_module_entitled(db, workspace_id, a.get("module_code")):
            raise HTTPException(status_code=409, detail=f"Module non souscrit: {a.get('module_code')}")
    intent = {"type": "access_grant", "companies": companies,
              "planned_access": [a for a in (access or []) if a.get("access_level") != "none"],
              "planned_permissions": permissions or []}
    existing = await _find_user_by_email(db, norm)
    reused = str(existing["_id"]) if existing else None
    activation, raw = await create_activation_token(
        db, workspace_id, norm, purpose="company_invitation", actor_id=actor_id,
        ttl_hours=ttl_hours, user_id=reused, intent=intent)
    return {"activation": activation, "activation_token": raw, "reused_identity": bool(reused)}


async def _provision_membership(db, workspace_id: str, user_id: str, intent: dict, actor_id: str) -> dict:
    t = intent.get("type")
    if t == "workspace_member":
        return await upsert_workspace_membership(db, workspace_id, user_id, intent.get("role", "user"), actor_id)
    # company_member
    return await create_company_membership(
        db, workspace_id, intent["company_id"], user_id,
        intent.get("membership_type"), intent.get("role"), actor_id)


async def activate_account(db, raw_token: str, *, password_hash: str,
                           name: Optional[str] = None) -> dict:
    """Consume a token, reuse/create the identity, set the user's own password,
    activate the identity, and provision the intended organizational membership.
    Returns {user_id, email}. Never grants module access or permissions."""
    doc = await consume_activation_token(db, raw_token)
    workspace_id = doc.get("workspace_id")
    email = _norm(doc.get("email"))
    intent = doc.get("intent") or {}
    now = _now()

    user = None
    if doc.get("user_id"):
        for key in ("_id", "id"):
            try:
                from bson import ObjectId
                _id = ObjectId(doc["user_id"]) if key == "_id" else doc["user_id"]
            except Exception:
                _id = doc["user_id"]
            user = await db.users.find_one({key: _id})
            if user:
                break
    if not user:
        user = await _find_user_by_email(db, email)

    if user:
        uid = str(user["_id"])
        update = {
            "password_hash": password_hash,
            "status": "active",
            "identity_status": "active",
            "workspace_id": user.get("workspace_id") or workspace_id,
            "activated_at": now,
        }
        if name and not user.get("name"):
            update["name"] = name
        await db.users.update_one({"_id": user["_id"]}, {"$set": update})
    else:
        res = await db.users.insert_one({
            "email": email,
            "name": name or email,
            "password_hash": password_hash,
            "role": "user",
            "status": "active",
            "identity_status": "active",
            "platform_role": None,
            "auth_provider": "password",
            "workspace_id": workspace_id,
            "created_at": now,
            "activated_at": now,
        })
        uid = str(res.inserted_id)

    membership = None
    if intent:
        if intent.get("type") == "access_grant":
            for c in intent.get("companies", []):
                membership = await create_company_membership(
                    db, workspace_id, c["company_id"], uid,
                    c.get("membership_type", "company_user"), c.get("role", "user"), "activation")
            # Apply admin-configured planned access (only after proof of control).
            for a in intent.get("planned_access", []):
                await set_user_module_access(db, workspace_id, a["company_id"], uid,
                                             a["module_code"], a["access_level"], "activation")
            for p in intent.get("planned_permissions", []):
                await set_user_permission(db, workspace_id, p["company_id"], uid,
                                          p["permission_code"], True, "activation")
        else:
            membership = await _provision_membership(db, workspace_id, uid, intent, actor_id="activation")

    return {"user_id": uid, "email": email, "workspace_id": workspace_id, "membership": membership}
