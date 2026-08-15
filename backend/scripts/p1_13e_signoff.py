"""P1.13E — Persona & security sign-off runner.

Runs the effective-access resolver against the REAL database for every persona
(expected vs actual matrix) and performs LIVE HTTP negative tests (privilege
escalation, tenant isolation, cross-workspace no-leak). Exits non-zero if any
expectation fails. READ-ONLY: no writes, no migration.
"""
import asyncio
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.access.effective_access import resolve_effective_access as rea

WS = "ws_56c492936ea64c4db53a2f14a0825ef5"
CA = "965f0770-8cf2-4199-a99f-819ff270436a"
CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"
BOGUS = "00000000-0000-0000-0000-000000000000"
API = os.environ.get("E2E_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL")

# (label, kwargs, expected_allowed, expected_reason_if_denied)
MATRIX = {
    "A platform@meelora.com": [
        ("CA ACCOUNTING read (bare membership)", dict(company_id=CA, module="ACCOUNTING", required_level="read"), False, "module_access_insufficient"),
        ("CA accounting.entry_post", dict(company_id=CA, permission="accounting.entry_post"), False, "module_access_insufficient"),
    ],
    "B persona_employe@accslegro.com": [
        ("CA ACCOUNTING read", dict(company_id=CA, module="ACCOUNTING", required_level="read"), True, None),
        ("CA ACCOUNTING contribute", dict(company_id=CA, module="ACCOUNTING", required_level="contribute"), False, "module_access_insufficient"),
        ("CA REPORTING read", dict(company_id=CA, module="REPORTING", required_level="read"), True, None),
        ("CA FIXED_ASSETS read (none)", dict(company_id=CA, module="FIXED_ASSETS", required_level="read"), False, "module_access_insufficient"),
        ("CA accounting.entry_post", dict(company_id=CA, permission="accounting.entry_post"), False, "permission_not_granted"),
    ],
    "C persona_clientadmin@accslegro.com": [
        ("CA ACCOUNTING read (admin != finance)", dict(company_id=CA, module="ACCOUNTING", required_level="read"), False, "module_access_insufficient"),
        ("CA accounting.entry_post", dict(company_id=CA, permission="accounting.entry_post"), False, "module_access_insufficient"),
        ("CA company context (member)", dict(company_id=CA), True, None),
    ],
    "D persona_junior@accslegro.com": [
        ("CA ACCOUNTING contribute", dict(company_id=CA, module="ACCOUNTING", required_level="contribute"), True, None),
        ("CA ACCOUNTING manage", dict(company_id=CA, module="ACCOUNTING", required_level="manage"), False, "module_access_insufficient"),
        ("CA accounting.entry_post (GL post)", dict(company_id=CA, permission="accounting.entry_post"), False, "permission_not_granted"),
        ("CA accounting.period_close", dict(company_id=CA, permission="accounting.period_close"), False, "permission_not_granted"),
    ],
    "E persona_finance@accslegro.com": [
        ("CA ACCOUNTING manage", dict(company_id=CA, module="ACCOUNTING", required_level="manage"), True, None),
        ("CA accounting.entry_post", dict(company_id=CA, permission="accounting.entry_post"), True, None),
        ("CA accounting.period_close", dict(company_id=CA, permission="accounting.period_close"), True, None),
        ("CA accounting.period_reopen (not granted)", dict(company_id=CA, permission="accounting.period_reopen"), False, "permission_not_granted"),
        ("CA reporting.report_finalize (no reporting)", dict(company_id=CA, permission="reporting.report_finalize"), False, "module_access_insufficient"),
    ],
    "F persona_reporting@accslegro.com": [
        ("CA REPORTING manage", dict(company_id=CA, module="REPORTING", required_level="manage"), True, None),
        ("CA reporting.report_finalize", dict(company_id=CA, permission="reporting.report_finalize"), True, None),
        ("CA ACCOUNTING read (none)", dict(company_id=CA, module="ACCOUNTING", required_level="read"), False, "module_access_insufficient"),
        ("CA FIXED_ASSETS read (none)", dict(company_id=CA, module="FIXED_ASSETS", required_level="read"), False, "module_access_insufficient"),
        ("CA CONSOLIDATION read (none)", dict(company_id=CA, module="CONSOLIDATION", required_level="read"), False, "module_access_insufficient"),
    ],
    "G persona_multi@accslegro.com": [
        ("CA ACCOUNTING read", dict(company_id=CA, module="ACCOUNTING", required_level="read"), True, None),
        ("CA ACCOUNTING manage", dict(company_id=CA, module="ACCOUNTING", required_level="manage"), False, "module_access_insufficient"),
        ("CB ACCOUNTING manage", dict(company_id=CB, module="ACCOUNTING", required_level="manage"), True, None),
        ("CB accounting.entry_post", dict(company_id=CB, permission="accounting.entry_post"), True, None),
        ("CA accounting.entry_post (isolation)", dict(company_id=CA, permission="accounting.entry_post"), False, "permission_not_granted"),
    ],
    "H persona_consol@accslegro.com": [
        ("CA CONSOLIDATION read", dict(company_id=CA, module="CONSOLIDATION", required_level="read"), True, None),
        ("CA CONSOLIDATION group_alpha", dict(company_id=CA, module="CONSOLIDATION", group_id="group_alpha"), True, None),
        ("CA CONSOLIDATION group_beta (out of scope)", dict(company_id=CA, module="CONSOLIDATION", group_id="group_beta"), False, "group_not_in_scope"),
    ],
}

# Cross-workspace / manipulation negative resolver cases applied to persona B.
NEG_RESOLVER = [
    ("B cross/bogus company_id -> no leak", "persona_employe@accslegro.com", dict(company_id=BOGUS, module="ACCOUNTING"), False, "cross_workspace"),
    ("B company CB without membership", "persona_employe@accslegro.com", dict(company_id=CB, module="ACCOUNTING"), False, "no_company_membership"),
]


async def load_ctx(db, email):
    u = await db.users.find_one({"email": email})
    return {"id": str(u["_id"]), "status": u.get("status", "active"),
            "identity_status": u.get("identity_status"), "platform_role": u.get("platform_role")}


def http_login(email, pw):
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    return r.json().get("token") if r.status_code == 200 else None


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    failures = []
    print("=" * 78)
    print("P1.13E — SECURITY MATRIX (resolver on real DB)")
    print("=" * 78)
    creds = {
        "A platform@meelora.com": ("platform@meelora.com", "platform123"),
        "B persona_employe@accslegro.com": ("persona_employe@accslegro.com", "persona123"),
        "C persona_clientadmin@accslegro.com": ("persona_clientadmin@accslegro.com", "persona123"),
        "D persona_junior@accslegro.com": ("persona_junior@accslegro.com", "persona123"),
        "E persona_finance@accslegro.com": ("persona_finance@accslegro.com", "persona123"),
        "F persona_reporting@accslegro.com": ("persona_reporting@accslegro.com", "persona123"),
        "G persona_multi@accslegro.com": ("persona_multi@accslegro.com", "persona123"),
        "H persona_consol@accslegro.com": ("persona_consol@accslegro.com", "persona123"),
    }
    for persona, cases in MATRIX.items():
        email = creds[persona][0]
        ctx = await load_ctx(db, email)
        print(f"\n### {persona}  (platform_role={ctx['platform_role']})")
        for label, kw, exp_allowed, exp_reason in cases:
            res = await rea(db, ctx, workspace_id=WS, **kw)
            ok = res["allowed"] == exp_allowed and (exp_allowed or res["reason"] == exp_reason)
            status = "OK " if ok else "FAIL"
            print(f"  [{status}] {label} -> allowed={res['allowed']} reason={res['reason']} (attendu allowed={exp_allowed}, reason={exp_reason})")
            if not ok:
                failures.append(f"{persona}: {label} -> {res}")

    print("\n" + "=" * 78)
    print("NEGATIVE RESOLVER CASES (no-leak / isolation)")
    print("=" * 78)
    for label, email, kw, exp_allowed, exp_reason in NEG_RESOLVER:
        ctx = await load_ctx(db, email)
        res = await rea(db, ctx, workspace_id=WS, **kw)
        ok = res["allowed"] == exp_allowed and res["reason"] == exp_reason
        print(f"  [{'OK ' if ok else 'FAIL'}] {label} -> allowed={res['allowed']} reason={res['reason']}")
        if not ok:
            failures.append(f"NEG: {label} -> {res}")

    print("\n" + "=" * 78)
    print("LIVE HTTP NEGATIVE TESTS (fail-closed at the route level)")
    print("=" * 78)
    http_cases = []
    tok_b = http_login("persona_employe@accslegro.com", "persona123")
    tok_c = http_login("persona_clientadmin@accslegro.com", "persona123")
    tok_plat = http_login("platform@meelora.com", "platform123")

    def check(label, method, path, token, expected_status):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.request(method, f"{API}{path}", headers=h, timeout=20)
        ok = r.status_code == expected_status
        print(f"  [{'OK ' if ok else 'FAIL'}] {label} -> {r.status_code} (attendu {expected_status})")
        if not ok:
            failures.append(f"HTTP: {label} -> {r.status_code} != {expected_status}")

    # Non-platform user cannot reach the platform console.
    check("B -> /api/platform/summary (403)", "GET", "/api/platform/summary", tok_b, 403)
    # Tenant isolation: B has no access to company CB -> 403 (no leak).
    check("B -> GET /api/companies/{CB} (403)", "GET", f"/api/companies/{CB}", tok_b, 403)
    # Manipulated / cross-workspace company id -> 404 (no enumeration).
    check("B -> GET /api/companies/{BOGUS} (404)", "GET", f"/api/companies/{BOGUS}", tok_b, 404)
    # Client Admin manages ONLY its own company members.
    check("C -> GET /api/companies/{CA}/members (200)", "GET", f"/api/companies/{CA}/members", tok_c, 200)
    check("C -> GET /api/companies/{CB}/members (403)", "GET", f"/api/companies/{CB}/members", tok_c, 403)
    # Platform staff has NO workspace-admin log authority.
    check("platform -> GET /api/logs (403)", "GET", "/api/logs", tok_plat, 403)
    # Platform console reachable for platform staff.
    check("platform -> /api/platform/summary (200)", "GET", "/api/platform/summary", tok_plat, 200)

    print("\n" + "=" * 78)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S)")
        for f in failures:
            print("  -", f)
        client.close()
        sys.exit(1)
    print("RESULT: ALL PERSONA & NEGATIVE CHECKS PASSED")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
