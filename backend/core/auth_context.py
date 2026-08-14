"""Tenant-aware authentication context helpers for Meelora V2 Foundation.

P1.2 enriches the authenticated user with its workspace context while keeping
legacy users (without workspace_id) able to sign in until P1.1 is committed in
all environments.
"""
from typing import Optional

from .workspaces import public_workspace


async def load_workspace_for_user(db, user_doc: dict) -> Optional[dict]:
    """Return the user's workspace document, or None for a legacy user.

    Workspace IDs are string IDs (``ws_<uuid>``), so no ObjectId coercion is
    performed here.
    """
    workspace_id = user_doc.get("workspace_id")
    if not workspace_id:
        return None
    return await db.workspaces.find_one({"_id": workspace_id})


def build_auth_user(user_doc: dict, workspace_doc: Optional[dict] = None) -> dict:
    """Build the internal authenticated-user context used by FastAPI routes.

    Password hashes are never copied. ``workspace`` is the safe public shape,
    while ``workspace_id`` remains available for permission helpers introduced
    in P1.3.
    """
    raw_id = user_doc.get("_id", user_doc.get("id"))
    user = {k: v for k, v in user_doc.items() if k not in {"_id", "password_hash"}}
    user["id"] = str(raw_id) if raw_id is not None else ""
    # P1.10: the public/authenticated role surface is now strictly admin/user.
    # Legacy rows can still contain ``editor`` until a DB cleanup is performed.
    if user.get("role") == "editor":
        user["role"] = "user"
    user["workspace_id"] = user_doc.get("workspace_id")
    user["workspace"] = public_workspace(workspace_doc)
    user["tenant_migrated"] = bool(user_doc.get("workspace_id") and workspace_doc)
    # P1.12: platform_role is a Meelora-internal privilege and is intentionally
    # separate from customer membership — it never grants customer data access.
    user["platform_role"] = user_doc.get("platform_role")
    return user


def auth_me_payload(user: dict) -> dict:
    """Stable public response for ``GET /api/auth/me``."""
    prefs = user.get("preferences") or {}
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "user"),
        "status": user.get("status", "active"),
        "workspace_id": user.get("workspace_id"),
        "workspace": user.get("workspace"),
        "tenant_migrated": bool(user.get("tenant_migrated")),
        "platform_role": user.get("platform_role"),
        "has_avatar": bool(prefs.get("avatar_path")),
    }
