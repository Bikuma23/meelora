"""P1.13A migration — derive conservative access from REAL legacy business access.

DRY-RUN by default (reports only; writes nothing). Pass --commit to apply.

Strategy (equal-or-less; NO privilege escalation):
* Ensure the Meelora workspace has all module entitlements (availability).
* Derive ``user_module_access = read`` ONLY from a **real legacy business-access
  artifact**: a P1.10 ``company_access`` grant on the company, AND the company
  operationally USES the module (has data). Membership alone (P1.12
  ``company_memberships``) is NEVER sufficient — membership != module access.
* Platform/support staff (``platform_role`` set) NEVER receive an automatic
  business module (a right they need is granted explicitly via access management).
* ``manage`` is never derived; sensitive permissions are NEVER auto-granted.
* Ambiguous cases stay ``none`` (reported, not granted).

The company_access / company_memberships / users.workspace_id structures are
preserved untouched. No financial data is read for mutation — only for a
used/not-used signal.
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

SCRIPT_NAME = "migrate_p1_13a_access.py"
SCRIPT_VERSION = "v2-legacy-company_access"


async def _find_user(db, uid):
    """Resolve a user whose id may be an ObjectId hex string or a uuid."""
    u = await db.users.find_one({"id": uid}) or await db.users.find_one({"_id": uid})
    if u is None:
        try:
            from bson import ObjectId
            u = await db.users.find_one({"_id": ObjectId(uid)})
        except Exception:
            u = None
    return u


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


async def run(commit: bool, actor_email: str = "platform@meelora.com"):
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

    # 2) Conservative user_module_access derived from REAL legacy business access
    #    (P1.10 company_access) — NOT from company_memberships. Membership alone is
    #    never a proof of module access. A grant requires: (a) a legacy company_access
    #    artifact on the company, (b) the company operationally USES the module, and
    #    (c) the user is NOT platform/support staff. Ambiguous -> none (reported).
    company_cache: dict[str, dict] = {}
    used_cache: dict[str, set[str]] = {}
    user_cache: dict[str, dict] = {}
    async for a in db.company_access.find({}):
        cid = a.get("company_id")
        wsid = a.get("workspace_id")
        uid = a.get("user_id")
        legacy_role = a.get("access_role") or a.get("role")
        if uid not in user_cache:
            user_cache[uid] = await _find_user(db, uid) or {}
        u = user_cache[uid]
        email = u.get("email", uid)
        # RULE: platform/support staff never receive an automatic business module.
        if u.get("platform_role"):
            report["reported"].append({"reason": "platform_staff_no_auto_module", "user_id": uid, "company_id": cid})
            print(f"  ! reported: {email} a platform_role='{u.get('platform_role')}' → aucun module métier automatique (none)")
            continue
        if cid not in company_cache:
            company_cache[cid] = await db.companies.find_one({"id": cid}) or {}
        company = company_cache[cid]
        if not company:
            report["reported"].append({"reason": "company_missing", "user_id": uid, "company_id": cid})
            print(f"  ! reported: company_access {email} -> company {cid} introuvable (skip)")
            continue
        if cid not in used_cache:
            used_cache[cid] = await _company_used_modules(db, company)
        used = used_cache[cid]
        if not used:
            # No operational data → no real business module access to migrate.
            report["reported"].append({"reason": "company_uses_no_module", "user_id": uid, "company_id": cid})
            print(f"  ! reported: {email} @ {company.get('name')} — société n'utilise aucun module → none")
            continue
        for code in sorted(used):
            existing = await db.user_module_access.find_one(
                {"workspace_id": wsid, "company_id": cid, "user_id": uid, "module_code": code})
            if existing:
                continue  # never widen an existing grant
            report["module_access"].append({"user_id": uid, "email": email, "workspace_id": wsid,
                                             "company_id": cid, "module_code": code, "level": "read",
                                             "legacy_role": legacy_role})
            print(f"  + module_access read : user={uid} ({email}) company={cid} module={code} [legacy company_access role={legacy_role}]")

    # 2b) SAFETY GUARD (commit only) — apply ONLY the explicitly validated grants.
    #     Julie + Marc -> ACCOUNTING/read on Meelora. Abort if the computed set
    #     diverges (never write an unvalidated grant).
    if commit:
        meelora_id = meelora.get("id") if meelora else None
        validated = set()
        for em in ("julie@accslegro.com", "marc@accslegro.com"):
            vu = await db.users.find_one({"email": em})
            if vu:
                validated.add((str(vu.get("id") or vu.get("_id")), meelora_id, "ACCOUNTING"))
        computed = {(g["user_id"], g["company_id"], g["module_code"]) for g in report["module_access"]}
        if computed != validated:
            print("\n[ABORT] Le jeu de grants calculé ne correspond PAS aux 2 grants validés.")
            print(f"        validés  : {sorted(validated)}")
            print(f"        calculés : {sorted(computed)}")
            print("        Aucune écriture d'accès effectuée.")
            client.close()
            raise SystemExit(2)
        for g in report["module_access"]:
            await db.user_module_access.insert_one(
                {"_id": f"uma_{uuid.uuid4().hex}", "workspace_id": g["workspace_id"], "company_id": g["company_id"],
                 "user_id": g["user_id"], "module_code": g["module_code"], "access_level": "read",
                 "created_at": now, "created_by": "migration_p1_13a", "updated_at": now})
        # 2c) Journalise the migration into Platform Logs (audit trail).
        try:
            from core.access import log_scope
            actor = await db.users.find_one({"email": actor_email}) or {}
            actor_dict = {"id": str(actor.get("id") or actor.get("_id") or "system"),
                          "email": actor.get("email", actor_email),
                          "platform_role": actor.get("platform_role", "platform_admin")}
            await log_scope.write_platform_log(
                db, actor_dict,
                event_type="platform.migration",
                label=f"Migration P1.13A appliquée ({SCRIPT_VERSION}) — {len(report['module_access'])} grant(s) d'accès module",
                target_workspace_id=(meelora.get("workspace_id") if meelora else None),
                details=f"script={SCRIPT_NAME} version={SCRIPT_VERSION}",
                metadata={"category": "platform", "result": "success", "action": "access_migration",
                          "script": SCRIPT_NAME, "version": SCRIPT_VERSION,
                          "applied_at": now, "actor_email": actor_dict["email"],
                          "grants_applied": [{"user_id": g["user_id"], "email": g["email"],
                                              "company_id": g["company_id"], "module": g["module_code"],
                                              "level": g["level"]} for g in report["module_access"]],
                          "entitlements_activated": report["entitlements"],
                          "reported_none": report["reported"],
                          "invariants": {"manage_auto": 0, "sensitive_auto": 0, "via_platform_role": 0,
                                         "by_membership_only": 0, "cross_workspace": 0, "budgets_implicit": 0}})
            print(f"  = platform log écrit (event=platform.migration, acteur={actor_dict['email']})")
        except Exception as e:
            print(f"  ! WARN: échec écriture platform log: {e}")

    print("\n--- SUMMARY ---")
    print(f"entitlements to activate : {len(report['entitlements'])}")
    print(f"user module_access (read): {len(report['module_access'])}")
    print(f"reported (no auto-grant) : {len(report['reported'])}")
    print("Rule: grants derive from LEGACY company_access + module used; membership alone = NEVER; platform_role = NEVER auto.")
    print("Sensitive permissions: NONE auto-granted. 'manage': NONE derived (no explicit signal).")
    print("Legacy company_access / company_memberships / users.workspace_id preserved untouched.")
    if not commit:
        print("\nDRY-RUN terminé — relancer avec --commit pour écrire.")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--commit", action="store_true")
    p.add_argument("--actor-email", default="platform@meelora.com",
                   help="Compte platform_admin enregistré comme acteur dans les Logs plateforme.")
    args = p.parse_args()
    asyncio.run(run(args.commit, args.actor_email))
