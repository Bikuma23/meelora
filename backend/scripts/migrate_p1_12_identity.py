"""P1.12 migration — users.workspace_id -> workspace_memberships,
company_access -> company_memberships. Dry-run by default; --commit to write.

Non-destructive: company_access is preserved (legacy bridge). platform_role is
NOT inferred; users missing it get an explicit null. No company-local users are
invented.
"""
import argparse
import asyncio
import os
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")


def _norm_role(r):
    return "user" if r in (None, "editor") else r


async def run(commit: bool):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    mode = "COMMIT" if commit else "DRY-RUN"
    print(f"[{mode}] P1.12 identity migration on {os.environ['DB_NAME']}")

    ws_created = ws_skipped = 0
    async for u in db.users.find({"workspace_id": {"$exists": True, "$ne": None}}):
        uid = str(u["_id"])
        wsid = u["workspace_id"]
        role = "admin" if _norm_role(u.get("role")) == "admin" else "user"
        exists = await db.workspace_memberships.find_one({"workspace_id": wsid, "user_id": uid, "status": "active"})
        if exists:
            ws_skipped += 1
            continue
        ws_created += 1
        print(f"  + workspace_membership user={u.get('email')} role={role}")
        if commit:
            await db.workspace_memberships.insert_one({
                "_id": f"wsm_{uuid.uuid4().hex}", "workspace_id": wsid, "user_id": uid,
                "role": role, "status": "active", "created_at": now, "created_by": "migration_p1_12"})

    plat = await db.users.count_documents({"platform_role": {"$exists": False}})
    print(f"  users without platform_role: {plat} (set to null)")
    if commit and plat:
        await db.users.update_many({"platform_role": {"$exists": False}}, {"$set": {"platform_role": None}})

    cm_created = cm_skipped = 0
    async for a in db.company_access.find({"active": True}):
        role = a.get("access_role") or a.get("role") or "collaborator"
        if role not in ("principal", "collaborator"):
            role = "collaborator"
        exists = await db.company_memberships.find_one({
            "workspace_id": a.get("workspace_id"), "company_id": a.get("company_id"),
            "user_id": a.get("user_id"), "membership_type": "workspace_staff", "status": "active"})
        if exists:
            cm_skipped += 1
            continue
        cm_created += 1
        print(f"  + company_membership company={a.get('company_id')} user={a.get('user_id')} staff/{role}")
        if commit:
            await db.company_memberships.insert_one({
                "_id": f"cpm_{uuid.uuid4().hex}", "workspace_id": a.get("workspace_id"),
                "company_id": a.get("company_id"), "user_id": a.get("user_id"),
                "membership_type": "workspace_staff", "role": role, "status": "active",
                "created_at": now, "created_by": "migration_p1_12"})

    print(f"\nworkspace_memberships: +{ws_created} (skipped {ws_skipped})")
    print(f"company_memberships:  +{cm_created} (skipped {cm_skipped})")
    print("company_access preserved (legacy bridge). No company-local users invented.")
    if not commit:
        print("\nDRY-RUN terminé — relancer avec --commit pour écrire.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args.commit))
