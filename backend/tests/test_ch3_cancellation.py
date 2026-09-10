import asyncio, os, uuid
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.compliance import company_tax_profile as svc

WS = "test_ws_ch3c"
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

    # base current + rectified (supersession) at 2026-01-01
    v1 = await pub(db, {"country": "CH", "canton": "GE", "vat_status": "unknown", "effective_from": "2026-01-01"})
    v2 = await pub(db, {"country": "CH", "canton": "GE", "vat_status": "taxable", "vat_number": "CHE-116.281.710",
                        "vat_method": "effective", "effective_from": "2026-01-01", "supersedes_version_id": v1["_id"]})
    # future version 2027
    vf = await pub(db, {"country": "CH", "canton": "VD", "vat_status": "not_taxable", "effective_from": "2027-07-01"})

    # 1. Delete a DRAFT (never published) works
    draft = await svc.create_draft(db, WS, CO, USER, {"country": "CH", "vat_status": "taxable", "effective_from": "2030-01-01"})
    res = await svc.delete_draft(db, WS, CO, USER, draft["_id"])
    check("delete draft ok", res["deleted"] is True)
    check("draft physically gone", await db.company_tax_profiles.find_one({"_id": draft["_id"]}) is None)

    # 2. Cannot DELETE a published version
    try:
        await svc.delete_draft(db, WS, CO, USER, v2["_id"]); check("delete published blocked", False)
    except Exception as e:
        check("delete published blocked", getattr(e, "status_code", None) == 409)

    # 3. Cancel requires a reason
    try:
        await svc.cancel_version(db, WS, CO, USER, vf["_id"], ""); check("cancel needs reason", False)
    except Exception as e:
        check("cancel needs reason", getattr(e, "status_code", None) == 422)

    # 4. Cancel the FUTURE version -> no longer active in 2027, doc unchanged
    await svc.cancel_version(db, WS, CO, USER, vf["_id"], "Créée par erreur")
    raw_vf = await db.company_tax_profiles.find_one({"_id": vf["_id"]})
    check("future doc not mutated", raw_vf.get("cancelled_at") is None and raw_vf["status"] == "published")
    active_2027 = await svc.get_active_profile(db, WS, CO, "2027-08-01")
    check("cancelled future not active", (active_2027 or {}).get("_id") != vf["_id"])

    # 5. History reflects cancellation (derived) + reason; tombstone not a row
    versions = await svc.list_versions(db, WS, CO)
    byid = {v["_id"]: v for v in versions}
    check("no tombstone rows", all(v.get("entry_type", "profile") == "profile" for v in versions))
    check("future is_cancelled", byid[vf["_id"]]["is_cancelled"] is True)
    check("future cancel reason", byid[vf["_id"]]["cancellation_reason"] == "Créée par erreur")

    # 6. Cannot cancel twice
    try:
        await svc.cancel_version(db, WS, CO, USER, vf["_id"], "encore"); check("double cancel blocked", False)
    except Exception as e:
        check("double cancel blocked", getattr(e, "status_code", None) == 409)

    # 7. Cancel the CURRENT version v2 (which superseded v1) -> v1 revives as active
    active_before = await svc.get_active_profile(db, WS, CO, "2026-06-01")
    check("before cancel active==v2", active_before["_id"] == v2["_id"])
    await svc.cancel_version(db, WS, CO, USER, v2["_id"], "Rectification erronée")
    active_after = await svc.get_active_profile(db, WS, CO, "2026-06-01")
    check("after cancel v2 -> v1 revives", active_after["_id"] == v1["_id"])
    raw_v2 = await db.company_tax_profiles.find_one({"_id": v2["_id"]})
    check("v2 doc not mutated", raw_v2.get("cancelled_at") is None and raw_v2["status"] == "published")

    # 8. Isolation: other company sees nothing
    other = await svc.get_active_profile(db, WS, "other_co", "2026-06-01")
    check("isolation other company", other is None)

    await db.company_tax_profiles.delete_many({"company_id": CO})
    await db.tax_profile_audit.delete_many({"company_id": CO})
    print(f"\n== {ok} passed, {fail} failed ==")
    return fail

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
