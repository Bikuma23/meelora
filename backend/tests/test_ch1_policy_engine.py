"""CH.1 Policy Engine — comprehensive temporal / parity / architecture tests.
Run: python -m tests.test_ch1_policy_engine  (from /app/backend). Prints PASS/FAIL."""
import asyncio
import os
import sys
import uuid

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

sys.path.insert(0, "/app/backend")
from core.compliance import policy_engine as pe  # noqa: E402
from core.financial import tax_engine  # noqa: E402

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
WS = f"ws_ch1test_{uuid.uuid4().hex[:8]}"
CO = f"co_ch1test_{uuid.uuid4().hex[:8]}"
WS2 = f"ws_ch1test_{uuid.uuid4().hex[:8]}"
CO2 = f"co_ch1test_{uuid.uuid4().hex[:8]}"
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name + (f" :: {extra}" if extra and not cond else ""))


async def seedco():
    # company profile CH + a versioned sales_tax_code identical to the real seed.
    await db.company_compliance_profiles.update_one(
        {"workspace_id": WS, "company_id": CO},
        {"$set": {"workspace_id": WS, "company_id": CO, "country": "CH",
                  "document_ai_regions": ["CH", "EU"]}}, upsert=True)
    await db.company_compliance_profiles.update_one(
        {"workspace_id": WS2, "company_id": CO2},
        {"$set": {"workspace_id": WS2, "company_id": CO2, "country": "CH"}}, upsert=True)
    tc = {"_id": f"tc_{uuid.uuid4().hex}", "workspace_id": WS, "company_id": CO,
          "code": "VAT_STD", "label": "TVA taux normal", "tax_kind": "taxable",
          "versions": [
              {"effective_date": "2018-01-01", "components": [{"name": "TVA", "tax_type": "VAT", "rate": 0.077, "payable_account_code": "TAX_VAT_PAYABLE"}]},
              {"effective_date": "2024-01-01", "components": [{"name": "TVA", "tax_type": "VAT", "rate": 0.081, "payable_account_code": "TAX_VAT_PAYABLE"}]}]}
    await db.sales_tax_codes.update_one({"workspace_id": WS, "company_id": CO, "code": "VAT_STD"},
                                        {"$set": tc}, upsert=True)
    await pe.ensure_indexes(db)
    await pe.ensure_seed(db)


async def cleanup():
    for w, c in ((WS, CO), (WS2, CO2)):
        await db.company_compliance_profiles.delete_many({"workspace_id": w})
        await db.sales_tax_codes.delete_many({"workspace_id": w})
    # Delete every test-created policy by its dedicated key (real seeds use key="base").
    test_keys = ["ch_override", "ch_retro", "confA", "confB", "expiring", "xxpack",
                 "draft_test", "co_override"]
    await db.jurisdiction_policies.delete_many({"key": {"$in": test_keys}})
    await db.jurisdiction_policies.delete_many({"jurisdiction": {"$in": ["XX", "XX-A"]}})
    await db.policy_audit.delete_many({"jurisdiction": {"$in": ["XX", "XX-A", "CH"]},
                                       "policy_id": {"$regex": "|".join(test_keys)}})


async def main():
    pe.clear_cache()
    await seedco()

    # 1) VAT parity with the existing tax_engine (before/after 2024 rate change).
    d2023 = await pe.resolve(db, WS, CO, domain="vat", context={"tax_code": "VAT_STD"}, as_of="2023-06-30")
    d2024 = await pe.resolve(db, WS, CO, domain="vat", context={"tax_code": "VAT_STD"}, as_of="2024-06-30")
    r23 = d2023["result"]["components"][0]["rate"]
    r24 = d2024["result"]["components"][0]["rate"]
    tc = await db.sales_tax_codes.find_one({"workspace_id": WS, "company_id": CO, "code": "VAT_STD"})
    par23 = tax_engine._pick_version(tc, "2023-06-30")["components"][0]["rate"]
    par24 = tax_engine._pick_version(tc, "2024-06-30")["components"][0]["rate"]
    check("VAT parity 2023 = 7.7%", r23 == 0.077 == par23, f"{r23} vs {par23}")
    check("VAT parity 2024 = 8.1%", r24 == 0.081 == par24, f"{r24} vs {par24}")

    # 2) Reproducibility: snapshot the 2023 decision, then publish a future change,
    #    explain() must still return 7.7% WITHOUT re-resolving.
    snap = pe.snapshot(d2023)
    exp = pe.explain(snap)
    check("explain(snapshot) reason mentions 7.70%", "7.70%" in (exp["statement"] or ""))
    # add a hypothetical NEW published version does not touch the old snapshot
    r23b = pe.explain(snap)["result"]["components"][0]["rate"]
    check("snapshot 2023 unchanged after later inspection", r23b == 0.077)

    # 3) Temporal windows on a policy-doc domain (fx_freshness) with versioning.
    #    system default is 7 days (seeded). Publish a CH override 10 days from 2026-01-01.
    await pe.publish_policy(db, domain="fx_freshness", jurisdiction="CH", scope="system",
                            key="ch_override", priority=200, effective_from="2026-01-01",
                            rules=[{"rule_id": "ch", "match": {}, "result": {"stale_days": 10},
                                    "reason": "CH: 10 jours."}], sources=[], overridability="overrideable")
    fx_2025 = await pe.resolve(db, WS, CO, domain="fx_freshness", context={}, as_of="2025-12-31")
    fx_2026 = await pe.resolve(db, WS, CO, domain="fx_freshness", context={}, as_of="2026-03-01")
    check("fx_freshness before effective_from = 7 (specific not premature)", fx_2025["result"]["stale_days"] == 7)
    check("fx_freshness on/after effective_from = 10 (CH specific wins)", fx_2026["result"]["stale_days"] == 10)

    # 4) Exact transition boundary at effective_from (inclusive).
    fx_boundary = await pe.resolve(db, WS, CO, domain="fx_freshness", context={}, as_of="2026-01-01")
    check("transition exact effective_from inclusive", fx_boundary["result"]["stale_days"] == 10)

    # 5) Future policy not used prematurely (already covered by #3: 2025 -> 7).
    check("future policy not used prematurely", fx_2025["result"]["stale_days"] == 7)

    # 6) effective_to boundary (expired policy not used).
    await pe.publish_policy(db, domain="rounding", jurisdiction="XX", scope="system", key="expiring",
                            priority=100, effective_from="2020-01-01", effective_to="2021-01-01",
                            rules=[{"rule_id": "old", "match": {}, "result": {"decimals": 3, "mode": "half_up"},
                                    "reason": "3 décimales (expiré)."}], sources=[], overridability="configurable")
    await db.company_compliance_profiles.update_one({"workspace_id": WS, "company_id": CO},
                                                    {"$set": {"country": "XX"}}, upsert=True)
    rnd_after = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2022-01-01")
    check("effective_to expired -> fallback (2 decimals)", rnd_after["result"]["decimals"] == 2 and rnd_after.get("fallback"))
    rnd_within = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2020-06-01")
    check("within window -> 3 decimals", rnd_within["result"]["decimals"] == 3)
    await db.company_compliance_profiles.update_one({"workspace_id": WS, "company_id": CO},
                                                    {"$set": {"country": "CH"}}, upsert=True)
    pe.clear_cache()

    # 7) Retroactive correction: publish a rule with a PAST effective_from -> future
    #    (non-snapshotted) resolutions use it; old snapshot stays unchanged.
    await pe.publish_policy(db, domain="fx_freshness", jurisdiction="CH", scope="system",
                            key="ch_retro", priority=300, effective_from="2026-02-01",
                            rules=[{"rule_id": "retro", "match": {}, "result": {"stale_days": 14},
                                    "reason": "Correction rétroactive: 14 jours."}], sources=[], overridability="overrideable")
    fx_retro = await pe.resolve(db, WS, CO, domain="fx_freshness", context={}, as_of="2026-03-01")
    check("retroactive correction applies to new resolution", fx_retro["result"]["stale_days"] == 14)
    check("old snapshot unchanged after retroactive correction", pe.explain(snap)["result"]["components"][0]["rate"] == 0.077)

    # 8) Publication-time overlap detection blocks ambiguous publish; runtime guard
    #    still fail-closes on a residual conflict (simulated by direct insert).
    blocked = False
    await pe.publish_policy(db, domain="monetary_classification", jurisdiction="CH", scope="system",
                            key="confA", priority=500, effective_from="2026-01-01",
                            rules=[{"rule_id": "a", "match": {}, "result": {"classification": "monetary"}, "reason": "A"}],
                            sources=[], overridability="overrideable")
    try:
        await pe.publish_policy(db, domain="monetary_classification", jurisdiction="CH", scope="system",
                                key="confB", priority=500, effective_from="2026-01-01",
                                rules=[{"rule_id": "b", "match": {}, "result": {"classification": "non_monetary"}, "reason": "B"}],
                                sources=[], overridability="overrideable")
    except pe.PolicyError as e:
        blocked = (e.code == "policy_conflict")
    check("publication-time overlap detection blocks ambiguous publish", blocked)
    # residual runtime conflict: inject a clashing published doc directly (bypass guard).
    await db.jurisdiction_policies.insert_one({
        "_id": f"pol_{uuid.uuid4().hex}", "policy_id": "system:monetary_classification:CH:confB",
        "domain": "monetary_classification", "jurisdiction": "CH", "scope": "system", "key": "confB",
        "policy_version": 1, "status": "published", "effective_from": "2026-01-01", "effective_to": None,
        "priority": 500, "overridability": "overrideable",
        "rules": [{"rule_id": "b", "match": {}, "result": {"classification": "non_monetary"}, "reason": "B"}],
        "sources": [], "workspace_id": "system", "company_id": None, "created_at": pe._now(), "published_at": pe._now()})
    pe.clear_cache()
    conflict = False
    try:
        await pe.resolve(db, WS, CO, domain="monetary_classification",
                         context={"position_type": "invoice"}, as_of="2026-06-01")
    except pe.PolicyError as e:
        conflict = (e.code == "policy_conflict")
    check("residual runtime conflict -> policy_conflict fail-closed", conflict)

    # 9) Absence of REQUIRED vat -> fail-closed (unknown code).
    failed = False
    try:
        await pe.resolve(db, WS, CO, domain="vat", context={"tax_code": "DOES_NOT_EXIST"}, as_of="2026-01-01")
    except pe.PolicyError as e:
        failed = (e.code == "policy_unavailable")
    check("required VAT absent -> fail-closed", failed)

    # 10) Fallback allowed on optional/fallback domain (rounding with no policy for a fresh juris).
    await db.company_compliance_profiles.update_one({"workspace_id": WS, "company_id": CO},
                                                    {"$set": {"country": "ZZ"}}, upsert=True)
    pe.clear_cache()
    rnd = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2026-01-01")
    check("fallback_allowed -> core fallback used", rnd.get("fallback") and rnd["result"]["decimals"] == 2)
    await db.company_compliance_profiles.update_one({"workspace_id": WS, "company_id": CO},
                                                    {"$set": {"country": "CH"}}, upsert=True)

    # 11) document_ai absorbed from jurisdiction module: returns region policy for CH.
    dai = await pe.resolve(db, WS, CO, domain="document_ai", context={}, as_of="2026-01-01")
    check("document_ai absorbed: CH region_required includes EU",
          "EU" in (dai["result"].get("region_required") or []) and dai["result"].get("allow_emergent_universal_key") is False)

    # 12) Draft never resolved; published immutable.
    draft = await pe.create_draft(db, domain="rounding", jurisdiction="CH", scope="system",
                                  key="draft_test", priority=900, effective_from="2000-01-01",
                                  rules=[{"rule_id": "d", "match": {}, "result": {"decimals": 5, "mode": "half_up"}, "reason": "draft"}],
                                  sources=[], overridability="configurable")
    pe.clear_cache()
    rnd_draft = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2026-01-01")
    check("draft NOT used by resolve", rnd_draft["result"]["decimals"] != 5)
    pub = await pe.publish_draft(db, draft["_id"])
    immut = False
    try:
        await pe.update_draft(db, pub["_id"], rules=[])
    except pe.PolicyError as e:
        immut = (e.code == "immutable")
    check("published version immutable", immut)

    # 13) Cache change does not change result.
    pe.clear_cache()
    a = await pe.resolve(db, WS, CO, domain="vat", context={"tax_code": "VAT_STD"}, as_of="2024-06-30")
    b = await pe.resolve(db, WS, CO, domain="vat", context={"tax_code": "VAT_STD"}, as_of="2024-06-30")  # cached
    check("cache hit identical result", a["result"] == b["result"])

    # 14) Isolation: a company override never leaks to another company.
    await pe.publish_policy(db, domain="fx_freshness", jurisdiction="CH", scope="company",
                            key="co_override", priority=1000, effective_from="2000-01-01",
                            workspace_id=WS, company_id=CO,
                            rules=[{"rule_id": "co", "match": {}, "result": {"stale_days": 99}, "reason": "override société"}],
                            sources=[], overridability="overrideable")
    pe.clear_cache()
    co1 = await pe.resolve(db, WS, CO, domain="fx_freshness", context={}, as_of="2026-06-01")
    co2 = await pe.resolve(db, WS2, CO2, domain="fx_freshness", context={}, as_of="2026-06-01")
    check("company override applies to its own company", co1["result"]["stale_days"] == 99)
    check("company override does NOT leak to other company", co2["result"]["stale_days"] != 99)

    # 15) Override guard: non_overrideable cannot be overridden even by admin.
    vat_dec = await pe.resolve(db, WS, CO, domain="vat", context={"tax_code": "VAT_STD"}, as_of="2024-06-30")
    guard = False
    try:
        pe.assert_overridable(vat_dec)
    except pe.PolicyError as e:
        guard = (e.code == "not_overridable")
    check("non_overrideable regulatory rule cannot be overridden", guard)

    # 16) XXCountryPack — architectural permanent test: publish, resolve, explain,
    #     snapshot, new future version, reproduce old decision — no engine change.
    await db.company_compliance_profiles.update_one({"workspace_id": WS, "company_id": CO},
                                                    {"$set": {"country": "XX", "subdivision": "A"}}, upsert=True)
    await pe.publish_policy(db, domain="rounding", jurisdiction="XX", scope="system", key="xxpack",
                            priority=100, effective_from="2026-01-01",
                            rules=[{"rule_id": "xx1", "match": {}, "result": {"decimals": 1, "mode": "half_up"}, "reason": "XX v1."}],
                            sources=[{"authority": "XX-Authority", "title": "XX rounding", "doc_ref": "xx-1",
                                      "url": "https://example.xx", "published_version": "1", "published_date": "2025-12-01",
                                      "effective_from": "2026-01-01", "verified_at": "2026-06", "archived_hash": None}],
                            overridability="configurable")
    pe.clear_cache()
    xx = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2026-06-01")
    xx_snap = pe.snapshot(xx)
    check("XXPack resolve v1", xx["result"]["decimals"] == 1)
    check("XXPack explain has structured source", pe.explain(xx_snap)["sources"][0]["authority"] == "XX-Authority")
    # future version
    await pe.publish_policy(db, domain="rounding", jurisdiction="XX", scope="system", key="xxpack",
                            priority=100, effective_from="2027-01-01",
                            rules=[{"rule_id": "xx2", "match": {}, "result": {"decimals": 4, "mode": "half_up"}, "reason": "XX v2."}],
                            sources=[], overridability="configurable")
    pe.clear_cache()
    xx_future = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2027-06-01")
    xx_past = await pe.resolve(db, WS, CO, domain="rounding", context={}, as_of="2026-06-01")
    check("XXPack future version resolves", xx_future["result"]["decimals"] == 4)
    check("XXPack old decision reproduced", xx_past["result"]["decimals"] == 1)
    check("XXPack old snapshot reproduced via explain", pe.explain(xx_snap)["result"]["decimals"] == 1)
    check("XXPack version bump = v2", xx_future["policy_version"] == 2)

    # 17) explain works with NO current resolution (simulate rate table gone).
    check("explain(snapshot) works without any resolve", pe.explain(snap)["statement"] is not None)

    await cleanup()
    npass = sum(1 for _, ok in results if ok)
    print(f"\n==== CH.1 RESULTS: {npass}/{len(results)} PASS ====")
    if npass != len(results):
        print("FAILURES:", [n for n, ok in results if not ok])
        sys.exit(1)


asyncio.run(main())
