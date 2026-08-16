"""ACCOUNTING A2 — GL business-rule matrix (lifecycle, periods, maker-checker,
balanced entries, sequential posting, reversal). Uses the isolated gl_service on
a throwaway company scope; no legacy data touched. Exit 0 = all pass."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.accounting import gl

WS = "ws_a2_test"
CO = "co_a2_test"
_fail = []


def ok(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _fail.append(name)


async def expect_http(name, coro, code):
    try:
        await coro
        ok(name + f" (expected HTTP {code})", False)
    except HTTPException as e:
        ok(name + f" → {e.status_code}", e.status_code == code)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.gl_periods.delete_many({"workspace_id": WS})
    await db.gl_entries.delete_many({"workspace_id": WS})
    maker = {"id": "u_maker", "email": "maker@test"}
    checker = {"id": "u_checker", "email": "checker@test"}

    print("== Periods ==")
    p1 = await gl.create_period(db, WS, CO, maker, code="2026-01")
    p2 = await gl.create_period(db, WS, CO, maker, code="2026-02")
    ok("two periods created, sequenced", p1["sequence"] == 0 and p2["sequence"] == 1)
    await expect_http("duplicate period code", gl.create_period(db, WS, CO, maker, code="2026-01"), 409)

    print("== Balanced entry + lifecycle + maker-checker ==")
    good = {"period_id": p1["id"], "memo": "test", "reference": "JE1",
            "lines": [{"account": "1000", "debit": 100}, {"account": "4000", "credit": 100}]}
    e = await gl.create_entry(db, WS, CO, maker, good)
    ok("entry created draft, balanced", e["status"] == "draft" and e["total_debit"] == 100 and e["total_credit"] == 100)
    await expect_http("unbalanced rejected", gl.create_entry(db, WS, CO, maker,
        {"period_id": p1["id"], "lines": [{"account": "1", "debit": 100}, {"account": "2", "credit": 90}]}), 422)
    await expect_http("single-line rejected", gl.create_entry(db, WS, CO, maker,
        {"period_id": p1["id"], "lines": [{"account": "1", "debit": 100}]}), 422)
    e = await gl.submit_entry(db, WS, CO, maker, e["id"])
    ok("submitted", e["status"] == "submitted")
    await expect_http("maker cannot approve own entry (maker-checker)", gl.approve_entry(db, WS, CO, maker, e["id"]), 403)
    e = await gl.approve_entry(db, WS, CO, checker, e["id"])
    ok("approved by a different user", e["status"] == "approved" and e["approved_by"] == "u_checker")
    e = await gl.post_entry(db, WS, CO, checker, e["id"])
    ok("posted (P1 open, no earlier period)", e["status"] == "posted")

    print("== Sequential posting: later period blocked until previous closed ==")
    e2 = await gl.create_entry(db, WS, CO, maker, {"period_id": p2["id"],
        "lines": [{"account": "1000", "debit": 50}, {"account": "4000", "credit": 50}]})
    e2 = await gl.submit_entry(db, WS, CO, maker, e2["id"])
    e2 = await gl.approve_entry(db, WS, CO, checker, e2["id"])
    await expect_http("post in P2 blocked while P1 open", gl.post_entry(db, WS, CO, checker, e2["id"]), 409)

    print("== Locked blocks posting; closed is terminal ==")
    e3 = await gl.create_entry(db, WS, CO, maker, {"period_id": p1["id"],
        "lines": [{"account": "1000", "debit": 10}, {"account": "4000", "credit": 10}]})
    e3 = await gl.submit_entry(db, WS, CO, maker, e3["id"])
    e3 = await gl.approve_entry(db, WS, CO, checker, e3["id"])
    await gl.transition_period(db, WS, CO, checker, p1["id"], "locked")
    await expect_http("post blocked when period locked", gl.post_entry(db, WS, CO, checker, e3["id"]), 409)
    await gl.transition_period(db, WS, CO, checker, p1["id"], "open")   # unlock allowed
    e3 = await gl.post_entry(db, WS, CO, checker, e3["id"])
    ok("post ok after unlock", e3["status"] == "posted")
    await gl.transition_period(db, WS, CO, checker, p1["id"], "closed")
    await expect_http("closed → open forbidden (everyone)", gl.transition_period(db, WS, CO, checker, p1["id"], "open"), 409)
    await expect_http("closed → locked forbidden", gl.transition_period(db, WS, CO, checker, p1["id"], "locked"), 409)
    # Now P2 postable (P1 closed).
    e2 = await gl.post_entry(db, WS, CO, checker, e2["id"])
    ok("post in P2 ok after P1 closed", e2["status"] == "posted")

    print("== Reversal (extourne) ==")
    rev = await gl.reverse_entry(db, WS, CO, checker, e2["id"])
    orig = await gl.get_entry(db, WS, CO, e2["id"])
    ok("reversal mirrors debits/credits", rev["lines"][0]["credit"] == 50 and rev["status"] == "posted")
    ok("original marked reversed + linked", orig["status"] == "reversed" and orig["reversed_by_entry"] == rev["id"])
    draft4 = await gl.create_entry(db, WS, CO, maker, {"period_id": p2["id"],
        "lines": [{"account": "1000", "debit": 5}, {"account": "4000", "credit": 5}]})
    await expect_http("cannot reverse a non-posted entry", gl.reverse_entry(db, WS, CO, checker, draft4["id"]), 409)

    print("== Audit trail present ==")
    full = await gl.get_entry(db, WS, CO, e3["id"])
    actions = [a["action"] for a in full.get("audit", [])]
    ok("audit records create/submit/approve/post", set(["create", "submit", "approve", "post"]).issubset(set(actions)))

    await db.gl_periods.delete_many({"workspace_id": WS})
    await db.gl_entries.delete_many({"workspace_id": WS})
    print(f"\n{'ALL PASS' if not _fail else 'FAILURES: ' + ', '.join(_fail)}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
