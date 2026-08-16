"""P1.13F — Sensitive financial permissions: positive/negative matrix.

Runnable standalone: `python tests/test_p1_13f_sensitive.py` (exit 0 = all pass).
Tests the central resolver used by every cabled sensitive route, per permission,
multi-company and cross-workspace. No financial data is mutated (only per-user
access/permission grants, restored at the end).

Invariant proven: module access alone (even `manage`) NEVER authorizes a
sensitive action — an explicit permission grant is mandatory; scope, membership
and active-company checks are fail-closed.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.access.effective_access import resolve_effective_access
from core.access.module_access import set_user_permission, set_user_module_access, get_user_module_level

MEE = "965f0770-8cf2-4199-a99f-819ff270436a"   # Meelora (interne) — Julie: ACCOUNTING read
QC = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"    # 9434 — Julie: aucune adhésion
GHOST = "cmp_ghost_p1_13f_000"
PERMS = ["accounting.period_close", "accounting.period_reopen", "accounting.entry_post",
         "accounting.customer_invoice_post", "accounting.entry_reverse"]

_failures = []


def check(name, got, expected):
    ok = got == expected
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got} expected={expected}")
    if not ok:
        _failures.append(name)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ju = await db.users.find_one({"email": "julie@accslegro.com"})
    j = {"id": str(ju["_id"]), "workspace_id": ju.get("workspace_id"),
         "status": ju.get("status", "active"), "identity_status": ju.get("identity_status"),
         "role": ju.get("role"), "platform_role": ju.get("platform_role"), "email": ju["email"]}
    ws = j["workspace_id"]

    async def R(company_id, permission):
        r = await resolve_effective_access(db, j, workspace_id=ws, company_id=company_id, permission=permission)
        return r["allowed"], r["reason"]

    # Baseline: Julie has ACCOUNTING read on Meelora, no sensitive permissions.
    for p in PERMS:
        await set_user_permission(db, ws, MEE, j["id"], p, False, "test")
    await set_user_module_access(db, ws, MEE, j["id"], "ACCOUNTING", "read", "test")

    print("== Per-permission positive/negative (Meelora) ==")
    for p in PERMS:
        # NEGATIVE — module access (read) but NO explicit permission.
        check(f"{p} · NEG no grant", await R(MEE, p), (False, "permission_not_granted"))
        # NEGATIVE — module 'manage' alone must NOT imply the permission.
        await set_user_module_access(db, ws, MEE, j["id"], "ACCOUNTING", "manage", "test")
        check(f"{p} · NEG manage-alone", await R(MEE, p), (False, "permission_not_granted"))
        # POSITIVE — explicit grant.
        await set_user_permission(db, ws, MEE, j["id"], p, True, "test")
        check(f"{p} · POS explicit grant", await R(MEE, p), (True, "granted"))
        # restore for next permission
        await set_user_permission(db, ws, MEE, j["id"], p, False, "test")
        await set_user_module_access(db, ws, MEE, j["id"], "ACCOUNTING", "read", "test")

    print("== Scope / membership / company-status (entry_post) ==")
    P = "accounting.entry_post"
    await set_user_permission(db, ws, MEE, j["id"], P, True, "test")
    # Cross-workspace / unknown company -> no-leak.
    check("cross-workspace ghost", await R(GHOST, P), (False, "cross_workspace"))
    # No membership on another company (9434).
    check("no company membership (9434)", await R(QC, P), (False, "no_company_membership"))
    # Inactive company -> fail-closed even with the permission.
    await db.companies.update_one({"id": MEE}, {"$set": {"status": "inactive"}})
    check("company inactive", await R(MEE, P), (False, "company_inactive"))
    await db.companies.update_one({"id": MEE}, {"$set": {"status": "active"}})

    # Cleanup — restore Julie to the P1.13A migration state (ACCOUNTING read, no perms).
    for p in PERMS:
        await set_user_permission(db, ws, MEE, j["id"], p, False, "test")
    await set_user_module_access(db, ws, MEE, j["id"], "ACCOUNTING", "read", "test")
    lvl = await get_user_module_level(db, ws, MEE, j["id"], "ACCOUNTING")
    print(f"cleanup: julie ACCOUNTING level = {lvl}")

    print(f"\n{'ALL PASS' if not _failures else 'FAILURES: ' + ', '.join(_failures)}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
