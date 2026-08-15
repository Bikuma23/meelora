"""P1.13A — Password/activation security foundation.

No administrator may read a user's password, and Meelora support may never set a
permanent client password. Emergency Client Admin activation/replacement uses a
one-time, single-use, expiring activation token; the new admin chooses their own
password. This module implements the DATA MODEL + HELPERS only — the full email
lifecycle/UI belongs to P1.13B.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from typing import Optional

from fastapi import HTTPException

ACTIVATION_PURPOSES = {"client_admin_activation", "client_admin_replacement"}
_now = lambda: datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def public_activation(doc: dict) -> dict:
    return {
        "id": doc.get("_id"),
        "workspace_id": doc.get("workspace_id"),
        "email": doc.get("email"),
        "user_id": doc.get("user_id"),
        "purpose": doc.get("purpose"),
        "status": doc.get("status"),
        "expires_at": doc.get("expires_at"),
        "used_at": doc.get("used_at"),
    }


async def create_activation_token(db, workspace_id: str, email: str, *, purpose: str,
                                  actor_id: str, ttl_hours: int = 48,
                                  user_id: Optional[str] = None) -> tuple[dict, str]:
    """Create a single-use activation token. Returns (public_doc, raw_token).

    The raw token is returned exactly once and is never stored in clear text.
    """
    if purpose not in ACTIVATION_PURPOSES:
        raise HTTPException(status_code=422, detail=f"Motif d'activation inconnu: {purpose}")
    norm = (email or "").strip().lower()
    if not norm:
        raise HTTPException(status_code=422, detail="Email requis")
    raw = secrets.token_urlsafe(32)
    now = _now()
    doc = {
        "_id": f"act_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "email": norm,
        "user_id": user_id,
        "token_hash": _hash_token(raw),
        "purpose": purpose,
        "status": "pending",
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "used_at": None,
        "created_at": now.isoformat(),
        "created_by": actor_id,
    }
    await db.client_admin_activations.insert_one(doc)
    return public_activation(doc), raw


async def consume_activation_token(db, raw_token: str) -> dict:
    """Validate + single-use consume a token. Never reveals a password."""
    doc = await db.client_admin_activations.find_one(
        {"token_hash": _hash_token(raw_token or ""), "status": "pending"})
    if not doc:
        raise HTTPException(status_code=400, detail="Jeton d'activation invalide ou déjà utilisé")
    try:
        expires = datetime.fromisoformat(doc.get("expires_at"))
    except Exception:
        expires = _now() - timedelta(seconds=1)
    if expires < _now():
        await db.client_admin_activations.update_one(
            {"_id": doc["_id"]}, {"$set": {"status": "expired"}})
        raise HTTPException(status_code=400, detail="Jeton d'activation expiré")
    await db.client_admin_activations.update_one(
        {"_id": doc["_id"]}, {"$set": {"status": "used", "used_at": _now().isoformat()}})
    doc = await db.client_admin_activations.find_one({"_id": doc["_id"]})
    return public_activation(doc)


async def replace_client_admin(db, workspace_id: str, company_id: str, old_membership_id: str,
                               new_email: str, *, actor_id: str, ttl_hours: int = 48) -> dict:
    """Emergency Client Admin replacement foundation.

    old admin  → company membership disabled + sessions marked revoked
    new admin  → existing global identity reused if present (by email),
                 otherwise an invitation/activation identity is prepared via a
                 one-time activation token. No permanent password is ever set.
    """
    now = _now().isoformat()
    old = await db.company_memberships.find_one(
        {"_id": old_membership_id, "workspace_id": workspace_id, "company_id": company_id})
    if not old:
        raise HTTPException(status_code=404, detail="Administrateur sortant introuvable")
    await db.company_memberships.update_one(
        {"_id": old_membership_id},
        {"$set": {"status": "inactive", "updated_at": now, "updated_by": actor_id}})
    # Revoke sessions (JWT is stateless today; record the revocation timestamp as
    # foundation — enforcement wiring belongs to P1.13B).
    old_user_id = old.get("user_id")
    if old_user_id:
        for key in ("_id", "id"):
            try:
                from bson import ObjectId
                _id = ObjectId(old_user_id) if key == "_id" else old_user_id
            except Exception:
                _id = old_user_id
            updated = await db.users.update_one(
                {key: _id}, {"$set": {"session_revoked_at": now}})
            if getattr(updated, "modified_count", 0):
                break

    norm = (new_email or "").strip().lower()
    reused = await db.users.find_one({"email": norm})
    reused_user_id = str(reused["_id"]) if reused else None
    activation, raw = await create_activation_token(
        db, workspace_id, norm, purpose="client_admin_replacement",
        actor_id=actor_id, ttl_hours=ttl_hours, user_id=reused_user_id)
    return {
        "old_membership_id": old_membership_id,
        "old_user_id": old_user_id,
        "reused_identity": bool(reused_user_id),
        "activation": activation,
        "activation_token": raw,  # returned once; caller delivers via P1.13B email flow
    }


async def ensure_indexes(db) -> None:
    await db.client_admin_activations.create_index(
        [("token_hash", 1)], unique=True, name="uniq_activation_token")
    await db.client_admin_activations.create_index(
        [("workspace_id", 1), ("email", 1)], name="idx_activation_ws_email")
