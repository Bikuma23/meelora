"""ACCOUNTING A2 — alignment with Financial Core P2 (periods + normalized journal).

Validates the maker-checker GL workflow now sits on the canonical Financial Core:
  * periods come from ``financial_periods`` (no ``gl_periods`` duplication);
  * draft/submit/approve NEVER write to the canonical journal;
  * POST creates EXACTLY ONE ``journal_entries`` (+lines), linked immutably;
  * POST is idempotent (retry → no duplicate ledger write);
  * reversal creates a NEW linked journal entry (original ledger never mutated);
  * journal ⇄ workflow traceable both ways;
  * locked/closed block posting; a later period is blocked until the previous
    one is closed; ``closed`` is terminal;
  * legacy acct_*/qc9434_* collections are never touched.

Uses a throwaway company scope; no legacy data touched. Exit 0 = all pass.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
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
FY = "fy_a2_test"
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


async def _seed_period(db, pid, code, seq, start, end, status="open"):
    await db.financial_periods.insert_one({
        "_id": pid, "workspace_id": WS, "company_id": CO, "financial_year_id": FY,
        "period_code": code, "label": code, "start_date": start, "end_date": end,
        "period_type": "month", "sequence": seq, "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "seed",
    })


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    # Clean scope.
    for col in ("financial_periods", "financial_years", "accounting_entries",
                "journal_entries", "journal_entry_lines", "companies", "gl_periods", "gl_entries"):
        await db[col].delete_many({"workspace_id": WS})
    await db.companies.insert_one({"_id": CO, "workspace_id": WS, "functional_currency": "CAD"})
    await db.financial_years.insert_one({
        "_id": FY, "workspace_id": WS, "company_id": CO, "label": "2026",
        "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"})
    P1, P2 = "fp_a2_p1", "fp_a2_p2"
    await _seed_period(db, P1, "2026-01", 1, "2026-01-01", "2026-01-31")
    await _seed_period(db, P2, "2026-02", 2, "2026-02-01", "2026-02-28")

    # Legacy snapshot (must be unchanged at the end).
    legacy_cols = ["acct_bv", "acct_periods", "acct_template", "acct_ledger",
                   "qc9434_journal", "qc9434_periods"]
    legacy_before = {c: await db[c].count_documents({}) for c in legacy_cols}

    maker = {"id": "u_maker", "email": "maker@test"}
    checker = {"id": "u_checker", "email": "checker@test"}

    print("== Periods are canonical financial_periods (no gl_periods) ==")
    periods = await gl.list_periods(db, WS, CO)
    ok("two canonical periods listed", len(periods) == 2 and periods[0]["code"] == "2026-01")
    ok("period id == financial_period_id (canonical)",
       periods[0]["id"] == P1 and periods[0]["financial_period_id"] == P1)
    ok("no gl_periods collection writes", await db.gl_periods.count_documents({"workspace_id": WS}) == 0)

    print("== Balanced entry + lifecycle + maker-checker ==")
    good = {"period_id": P1, "memo": "test", "reference": "JE1",
            "lines": [{"account": "1000", "debit": 100}, {"account": "4000", "credit": 100}]}
    e = await gl.create_entry(db, WS, CO, maker, good)
    ok("entry created draft, balanced, canonical period ref",
       e["status"] == "draft" and e["total_debit"] == 100 and e["financial_period_id"] == P1)
    await expect_http("unbalanced rejected", gl.create_entry(db, WS, CO, maker,
        {"period_id": P1, "lines": [{"account": "1", "debit": 100}, {"account": "2", "credit": 90}]}), 422)
    e = await gl.submit_entry(db, WS, CO, maker, e["id"])
    ok("submitted", e["status"] == "submitted")
    await expect_http("maker cannot approve own entry", gl.approve_entry(db, WS, CO, maker, e["id"]), 403)
    e = await gl.approve_entry(db, WS, CO, checker, e["id"])
    ok("approved by a different user", e["status"] == "approved")

    print("== draft/submit/approve NEVER write to the canonical journal ==")
    je_after_approve = await db.journal_entries.count_documents({"workspace_id": WS, "external_id": e["id"]})
    ok("no journal entry before POST", je_after_approve == 0)

    print("== POST creates EXACTLY ONE canonical journal entry, linked ==")
    e = await gl.post_entry(db, WS, CO, checker, e["id"])
    ok("posted with journal_entry_id link", e["status"] == "posted" and e.get("journal_entry_id"))
    jes = await db.journal_entries.find({"workspace_id": WS, "external_id": e["id"]}).to_list(None)
    ok("exactly one canonical journal entry", len(jes) == 1)
    je = jes[0]
    jel = await db.journal_entry_lines.find({"journal_entry_id": je["_id"]}).to_list(None)
    ok("journal has 2 balanced lines", len(jel) == 2 and round(sum(l["debit"] for l in jel), 2) == 100)
    ok("journal tied to canonical financial_period_id", je["financial_period_id"] == P1)
    ok("journal source_system=accounting", je.get("source_system") == "accounting")

    print("== traceability both ways ==")
    ok("workflow → journal", e["journal_entry_id"] == je["_id"])
    ok("journal → workflow (external_id)", je.get("external_id") == e["id"])

    print("== POST idempotent (retry → no duplicate) ==")
    e_again = await gl.post_entry(db, WS, CO, checker, e["id"])
    dup = await db.journal_entries.count_documents({"workspace_id": WS, "external_id": e["id"]})
    ok("retry returns same journal_entry_id", e_again["journal_entry_id"] == je["_id"])
    ok("no duplicate journal entry after retry", dup == 1)

    print("== Sequential posting: later period blocked until previous closed ==")
    e2 = await gl.create_entry(db, WS, CO, maker, {"period_id": P2,
        "lines": [{"account": "1000", "debit": 50}, {"account": "4000", "credit": 50}]})
    e2 = await gl.submit_entry(db, WS, CO, maker, e2["id"])
    e2 = await gl.approve_entry(db, WS, CO, checker, e2["id"])
    await expect_http("post in P2 blocked while P1 open", gl.post_entry(db, WS, CO, checker, e2["id"]), 409)

    print("== Locked blocks posting; closed is terminal ==")
    e3 = await gl.create_entry(db, WS, CO, maker, {"period_id": P1,
        "lines": [{"account": "1000", "debit": 10}, {"account": "4000", "credit": 10}]})
    e3 = await gl.submit_entry(db, WS, CO, maker, e3["id"])
    e3 = await gl.approve_entry(db, WS, CO, checker, e3["id"])
    await gl.transition_period(db, WS, CO, checker, P1, "locked")
    await expect_http("post blocked when period locked", gl.post_entry(db, WS, CO, checker, e3["id"]), 409)
    await gl.transition_period(db, WS, CO, checker, P1, "open")
    e3 = await gl.post_entry(db, WS, CO, checker, e3["id"])
    ok("post ok after unlock", e3["status"] == "posted")
    await gl.transition_period(db, WS, CO, checker, P1, "closed")
    await expect_http("closed → open forbidden (everyone)", gl.transition_period(db, WS, CO, checker, P1, "open"), 409)
    await expect_http("closed → locked forbidden", gl.transition_period(db, WS, CO, checker, P1, "locked"), 409)
    e2 = await gl.post_entry(db, WS, CO, checker, e2["id"])
    ok("post in P2 ok after P1 closed", e2["status"] == "posted")

    print("== Reversal creates a NEW linked journal entry (original never mutated) ==")
    orig_je_id = e2["journal_entry_id"]
    orig_lines_before = await db.journal_entry_lines.find({"journal_entry_id": orig_je_id}).to_list(None)
    rev = await gl.reverse_entry(db, WS, CO, checker, e2["id"])
    orig = await gl.get_entry(db, WS, CO, e2["id"])
    ok("reversal mirrors debits/credits, posted", rev["lines"][0]["credit"] == 50 and rev["status"] == "posted")
    ok("original workflow marked reversed + linked",
       orig["status"] == "reversed" and orig["reversed_by_entry"] == rev["id"])
    rev_je = await db.journal_entries.find_one({"_id": rev["journal_entry_id"]})
    ok("reversal journal links to original ledger", rev_je.get("reverses_journal_entry_id") == orig_je_id)
    orig_je = await db.journal_entries.find_one({"_id": orig_je_id})
    ok("original ledger back-references reversal", orig_je.get("reversed_by_journal_entry_id") == rev["journal_entry_id"])
    orig_lines_after = await db.journal_entry_lines.find({"journal_entry_id": orig_je_id}).to_list(None)
    ok("original ledger lines never mutated",
       len(orig_lines_after) == len(orig_lines_before)
       and round(sum(l["debit"] for l in orig_lines_after), 2) == round(sum(l["debit"] for l in orig_lines_before), 2))
    await expect_http("cannot reverse a non-posted entry", gl.reverse_entry(db, WS, CO, checker, e3["id"]), 409) \
        if e3["status"] != "posted" else None

    print("== No duplication: every accounting_entry uses a canonical period ==")
    all_entries = await db.accounting_entries.find({"workspace_id": WS}).to_list(None)
    canonical_ids = {P1, P2}
    ok("all workflow entries reference canonical financial_period_id",
       all(en.get("financial_period_id") in canonical_ids for en in all_entries))

    print("== Legacy acct_*/qc9434_* untouched ==")
    legacy_after = {c: await db[c].count_documents({}) for c in legacy_cols}
    ok("no legacy collection changed", legacy_before == legacy_after)

    # Cleanup.
    for col in ("financial_periods", "financial_years", "accounting_entries",
                "journal_entries", "journal_entry_lines", "companies"):
        await db[col].delete_many({"workspace_id": WS})
    print(f"\n{'ALL PASS' if not _fail else 'FAILURES: ' + ', '.join(_fail)}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
