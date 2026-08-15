"""P1.13A migration — derive conservative access from P1.12 memberships.

DRY-RUN by default (reports only; writes nothing). Pass --commit to apply.

Strategy (equal-or-less; NO privilege escalation):
* Ensure the Meelora workspace has all four module entitlements (availability).
* For every ACTIVE company_membership, derive ``user_module_access = read`` on
  the modules the company already USES (has data for). ``manage`` is only granted
  when an explicit signal exists (none is derivable from legacy data, so none is
  granted). Sensitive permissions are NEVER auto-granted.
* Any membership whose role cannot be safely translated is REPORTED, not granted.

The company_access / users.workspace_id legacy structures are preserved untouched.
No financial data is read for mutation — only for a used/not-used signal.
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.access.modules import MODULE_CODES


async def _company_used_modules(db, company) -> set[str]:
    """Conservative 'module is in use by this company' detector (read-only)."""
    used: set[str] = set()
    cid = company.get("id")
    legacy = company.get("legacy_prefix")
    # ACCOUNTING — legacy acct/qc9434 engines or Financial-Core trial balance.
    acct_signals = 0
    if legacy == "acct":
        acct_signals += await db.acct_periods.count_documents({})
        acct_signals += await db.acct_bv.count_documents({})
    elif legacy == "qc9434":
        acct_signals += await db.qc9434_periods.count_documents({}) if "qc9434_periods" in await db.list_collection_names() else 0
    acct_signals += await db.trial_balance_lines.count_documents({"company_id": cid})
    acct_signals += await db.journal_entries.count_documents({"company_id": cid})
    if acct_signals:
        used.add("ACCOUNTING")
    # REPORTING — mappings or generated report runs.
    rep_signals = await db.account_mappings.count_documents({"company_id": cid})
    rep_signals += await db.report_runs.count_documents({"company_id": cid})
    if rep_signals:
        used.add("REPORTING")
    return used


async def run(commit: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    mode = "COMMIT" if commit else "DRY-RUN"
    print(f"[{mode}] P1.13A access migration on {os.environ['DB_NAME']}\n")

    report = {"entitlements": [], "module_access": [], "reported": []}

    # 1) Entitlements — Meelora workspace (identified via legacy 'acct' company).
    meelora = await db.companies.find_one({"legacy_prefix": "acct"})
    if meelora and meelora.get("workspace_id"):
        wsid = meelora["workspace_id"]
        for code in sorted(MODULE_CODES):
            existing = await db.workspace_module_entitlements.find_one(
                {"workspace_id": wsid, "module_code": code})
            active = bool(existing) and existing.get("status") in ("active", "trial")
            if active:
                print(f"  = entitlement present : {code} (workspace {wsid})")
                continue
            report["entitlements"].append({"workspace_id": wsid, "module_code": code})
            print(f"  + entitlement (active) : {code} (workspace {wsid})")
            if commit:
                await db.workspace_module_entitlements.update_one(
                    {"workspace_id": wsid, "module_code": code},
                    {"$set": {"status": "active", "activated_at": now, "deactivated_at": None,
                              "source": "migration_p1_13a", "updated_at": now, "updated_by": "migration_p1_13a"},
                     "$setOnInsert": {"_id": f"wme_{uuid.uuid4().hex}", "workspace_id": wsid,
                                      "module_code": code, "created_at": now, "created_by": "migration_p1_13a"}},
                    upsert=True)

    # 2) Conservative user_module_access from active company memberships.
    company_cache: dict[str, dict] = {}
    used_cache: dict[str, set[str]] = {}
    async for m in db.company_memberships.find({"status": "active"}):
        cid = m.get("company_id")
        wsid = m.get("workspace_id")
        uid = m.get("user_id")
        role = m.get("role")
        if cid not in company_cache:
            company_cache[cid] = await db.companies.find_one({"id": cid}) or {}
        company = company_cache[cid]
        if not company:
            report["reported"].append({"reason": "company_missing", "membership": m.get("_id")})
            print(f"  ! reported: membership {m.get('_id')} -> company {cid} introuvable (skip)")
            continue
        if role not in ("admin", "user", "principal", "collaborator"):
            report["reported"].append({"reason": "ambiguous_role", "membership": m.get("_id"), "role": role})
            print(f"  ! reported: rôle ambigu '{role}' pour {uid}@{cid} — aucun accès dérivé")
            continue
        if cid not in used_cache:
            used_cache[cid] = await _company_used_modules(db, company)
        used = used_cache[cid]
        for code in sorted(used):
            existing = await db.user_module_access.find_one(
                {"workspace_id": wsid, "company_id": cid, "user_id": uid, "module_code": code})
            if existing:
                continue  # never widen an existing grant
            report["module_access"].append({"user_id": uid, "company_id": cid, "module_code": code, "level": "read"})
            print(f"  + module_access read : user={uid} company={cid} module={code}")
            if commit:
                await db.user_module_access.insert_one(
                    {"_id": f"uma_{uuid.uuid4().hex}", "workspace_id": wsid, "company_id": cid,
                     "user_id": uid, "module_code": code, "access_level": "read",
                     "created_at": now, "created_by": "migration_p1_13a", "updated_at": now})

    print("\n--- SUMMARY ---")
    print(f"entitlements to activate : {len(report['entitlements'])}")
    print(f"user module_access (read): {len(report['module_access'])}")
    print(f"reported (no auto-grant) : {len(report['reported'])}")
    print("Sensitive permissions: NONE auto-granted. 'manage': NONE derived (no explicit signal).")
    print("Legacy company_access / users.workspace_id preserved untouched.")
    if not commit:
        print("\nDRY-RUN terminé — relancer avec --commit pour écrire.")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--commit", action="store_true")
    asyncio.run(run(p.parse_args().commit))
