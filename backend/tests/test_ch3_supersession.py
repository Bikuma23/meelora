import asyncio, os, uuid
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.compliance import company_tax_profile as svc

WS = "test_ws_ch3"
CO = "test_co_" + uuid.uuid4().hex[:8]
USER = {"id": "u1", "email": "tester@x.com"}


async def pub(db, payload):
    d = await svc.create_draft(db, WS, CO, USER, payload)
    return await svc.publish(db, WS, CO, USER, d["_id"])


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = c[os.environ["DB_NAME"]]
    ok = 0; fail = 0
    def check(name, cond):
        nonlocal ok, fail
        if cond: ok += 1; print("PASS", name)
        else: fail += 1; print("FAIL", name)

    # 1. Initial publish: needs_attention (vat unknown), 2026-01-01
    v1 = await pub(db, {"country": "CH", "canton": "GE", "vat_status": "unknown", "effective_from": "2026-01-01"})
    check("v1 needs_attention", v1["completeness"] == "needs_attention")
    active = await svc.get_active_profile(db, WS, CO, "2026-06-01")
    check("resolution picks v1", active["_id"] == v1["_id"])

    # 2. Rectification SAME date -> supersedes v1, becomes complete
    v2 = await pub(db, {"country": "CH", "canton": "GE", "vat_status": "taxable",
                        "vat_number": "CHE-116.281.710", "vat_method": "effective",
                        "effective_from": "2026-01-01", "supersedes_version_id": v1["_id"],
                        "supersession_reason": "rectification"})
    check("v2 complete", v2["completeness"] == "complete")
    check("v2 supersedes v1", v2["supersedes_version_id"] == v1["_id"])
    active = await svc.get_active_profile(db, WS, CO, "2026-06-01")
    check("resolution now picks v2", active["_id"] == v2["_id"])

    # 3. Old doc physically unchanged (still published, no supersedes field on it)
    raw_v1 = await db.company_tax_profiles.find_one({"_id": v1["_id"]})
    check("v1 doc unchanged status", raw_v1["status"] == "published")
    check("v1 doc not mutated (no superseded_at)", raw_v1.get("superseded_at") is None)

    # 4. History marks v1 as superseded (derived), v2 as current
    versions = await svc.list_versions(db, WS, CO)
    byid = {v["_id"]: v for v in versions}
    check("history v1 is_superseded", byid[v1["_id"]]["is_superseded"] is True)
    check("history v2 not superseded", byid[v2["_id"]]["is_superseded"] is False)

    # 5. Overlap WITHOUT supersession relation -> 409 fail-closed
    d3 = await svc.create_draft(db, WS, CO, USER, {"country": "CH", "vat_status": "taxable",
                                                   "vat_number": "CHE-116.281.710", "vat_method": "effective",
                                                   "effective_from": "2026-01-01"})
    try:
        await svc.publish(db, WS, CO, USER, d3["_id"]); check("overlap no-supersede 409", False)
    except Exception as e:
        check("overlap no-supersede 409", getattr(e, "status_code", None) == 409)

    # 6. Cannot supersede a NON-tip (v1 already superseded by v2)
    d4 = await svc.create_draft(db, WS, CO, USER, {"country": "CH", "vat_status": "taxable",
                                                   "vat_number": "CHE-116.281.710", "vat_method": "effective",
                                                   "effective_from": "2026-01-01", "supersedes_version_id": v1["_id"]})
    try:
        await svc.publish(db, WS, CO, USER, d4["_id"]); check("no branching (supersede non-tip)", False)
    except Exception as e:
        check("no branching (supersede non-tip)", getattr(e, "status_code", None) == 409)

    # 7. Chain: rectify again superseding the current tip v2
    v5 = await pub(db, {"country": "CH", "canton": "VD", "vat_status": "taxable",
                        "vat_number": "CHE-116.281.710", "vat_method": "net_tax_rate",
                        "effective_from": "2026-01-01", "supersedes_version_id": v2["_id"]})
    active = await svc.get_active_profile(db, WS, CO, "2026-06-01")
    check("chain resolution picks v5", active["_id"] == v5["_id"])
    check("v5 method tdfn", active["vat_method"] == "net_tax_rate")

    # 8. Real change (new date) does NOT need supersession
    v6 = await pub(db, {"country": "CH", "canton": "VD", "vat_status": "not_taxable",
                        "effective_from": "2027-07-01"})
    check("new-period publish ok", v6["status"] == "published")
    active_now = await svc.get_active_profile(db, WS, CO, "2026-06-01")
    check("as-of 2026 still v5", active_now["_id"] == v5["_id"])
    active_2027 = await svc.get_active_profile(db, WS, CO, "2027-08-01")
    check("as-of 2027 picks v6", active_2027["_id"] == v6["_id"])

    # cleanup
    await db.company_tax_profiles.delete_many({"company_id": CO})
    await db.tax_profile_audit.delete_many({"company_id": CO})
    print(f"\n== {ok} passed, {fail} failed ==")
    return fail

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
