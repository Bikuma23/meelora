"""P2.5 — Normalized Trial Balance tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.trial_balance import (
    preview_trial_balance_import,
    commit_trial_balance_import,
    list_trial_balance,
    parse_trial_balance_file,
)


def _matches(doc, query):
    for key, value in query.items():
        actual = doc.get(key)
        if isinstance(value, dict):
            if "$ne" in value and actual == value["$ne"]:
                return False
            if "$in" in value and actual not in value["$in"]:
                return False
        elif actual != value:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self.docs = list(docs)
    async def to_list(self, _n=None): return [d.copy() for d in self.docs]


class _Collection:
    def __init__(self, docs=None): self.docs = [d.copy() for d in (docs or [])]
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def insert_one(self, doc): self.docs.append(doc.copy())
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return


WS = "ws_a"
CA = "cmp_a"
CB = "cmp_b"
FY = "fy_1"
FP = "fp_1"


def _acc(code, aid, ws=WS, cid=CA):
    return {"_id": aid, "workspace_id": ws, "company_id": cid, "account_code": code,
            "account_name": code, "account_type": "asset", "normal_balance": "debit",
            "currency": "CHF", "active": True, "source_system": "manual"}


class _DB:
    def __init__(self):
        self.companies = _Collection([
            {"id": CA, "workspace_id": WS, "name": "Alpha", "active": True, "status": "active", "functional_currency": "CHF"},
            {"id": CB, "workspace_id": WS, "name": "Beta", "active": True, "status": "active", "functional_currency": "CAD"},
            {"id": "cmp_x", "workspace_id": "ws_x", "name": "Other", "active": True, "status": "active", "functional_currency": "USD"},
        ])
        self.company_access = _Collection([
            {"workspace_id": WS, "company_id": CA, "user_id": "u_read", "access_role": "collaborator", "active": True},
        ])
        self.company_memberships = _Collection([])
        self.financial_years = _Collection([
            {"_id": FY, "workspace_id": WS, "company_id": CA, "label": "2026", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"},
            {"_id": "fy_2", "workspace_id": WS, "company_id": CA, "label": "2027", "start_date": "2027-01-01", "end_date": "2027-12-31", "status": "open"},
            {"_id": "fy_other", "workspace_id": WS, "company_id": CB, "label": "2026B", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"},
        ])
        self.financial_periods = _Collection([
            {"_id": FP, "workspace_id": WS, "company_id": CA, "financial_year_id": FY, "period_code": "2026-01",
             "label": "Janvier 2026", "start_date": "2026-01-01", "end_date": "2026-01-31", "sequence": 1, "status": "open"},
            {"_id": "fp_2", "workspace_id": WS, "company_id": CA, "financial_year_id": "fy_2", "period_code": "2027-01",
             "label": "Janvier 2027", "start_date": "2027-01-01", "end_date": "2027-01-31", "sequence": 1, "status": "open"},
            {"_id": "fp_other", "workspace_id": WS, "company_id": CB, "financial_year_id": "fy_other", "period_code": "2026-01",
             "label": "Jan", "start_date": "2026-01-01", "end_date": "2026-01-31", "sequence": 1, "status": "open"},
        ])
        # Normalized accounts referenced by TB rows (leading zero + punctuation codes).
        self.accounts = _Collection([
            _acc("0010", "acc_cash"), _acc("3200", "acc_sales"),
            _acc("4.100", "acc_other"), _acc("A100-01", "acc_rent"),
        ])
        self.data_imports = _Collection([])
        self.trial_balance_lines = _Collection([])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def platform_admin(ws=WS): return {"id": "u_plat", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _grant(db, uid, mtype, role, cid=CA, ws=WS):
    db.company_memberships.docs.append({
        "_id": f"cpm_{uid}", "workspace_id": ws, "company_id": cid,
        "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


HEADER = "account_code,account_name,period_debit,period_credit,ytd_debit,ytd_credit"


def _csv(*lines) -> bytes:
    return ("\n".join([HEADER, *lines])).encode("utf-8")


# Balanced: period debit 300 / credit 300 ; ytd debit 600 / credit 600.
BALANCED = _csv(
    "0010,Cash,100,0,250,0",
    "3200,Sales,0,300,0,600",
    "4.100,Other,200,0,350,0",
)


def _preview(db, content=BALANCED, company=CA, user=None, fy=FY, fp=FP, name="tb.csv"):
    return _run(preview_trial_balance_import(db, company, user or admin(), content, name, fy, fp, "csv"))


# ---- Parsing / preview ----------------------------------------------------
def test_parse_preserves_codes():
    rows = parse_trial_balance_file(BALANCED, "tb.csv")
    assert [r["account_code"] for r in rows] == ["0010", "3200", "4.100"]


def test_preview_valid_balanced():
    db = _DB()
    res = _preview(db)
    assert res["status"] == "valid"
    assert res["controls"]["period_balanced"] and res["controls"]["ytd_balanced"]
    assert res["controls"]["period_total_debit"] == 300.0
    assert res["controls"]["period_total_credit"] == 300.0


def test_preview_does_not_write_lines():
    db = _DB()
    _preview(db)
    assert len(db.trial_balance_lines.docs) == 0
    assert len(db.data_imports.docs) == 1


def test_period_and_ytd_net_computed():
    db = _DB()
    res = _preview(db)
    rows = {p["account_code"]: p["normalized"] for p in res["preview_rows"]}
    assert rows["0010"]["period_net"] == 100.0 and rows["0010"]["ytd_net"] == 250.0
    assert rows["3200"]["period_net"] == -300.0 and rows["3200"]["ytd_net"] == -600.0


def test_supplied_net_consistency_ok():
    db = _DB()
    content = ("account_code,period_debit,period_credit,period_net,ytd_debit,ytd_credit,ytd_net\n"
               "0010,100,0,100,250,0,250\n3200,0,100,-100,0,250,-250\n").encode()
    res = _preview(db, content)
    assert res["status"] == "valid"


def test_invalid_supplied_net_blocking():
    db = _DB()
    content = ("account_code,period_debit,period_credit,period_net,ytd_debit,ytd_credit\n"
               "0010,100,0,999,250,0\n3200,0,100,-100,0,250\n").encode()
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_missing_account_blocking_and_reported():
    db = _DB()
    content = _csv("0010,Cash,100,0,250,0", "9999,Ghost,0,100,0,250")
    res = _preview(db, content)
    assert res["status"] == "failed"
    assert "9999" in res["controls"]["unresolved_codes"]


def test_leading_zero_and_punctuation_resolution():
    db = _DB()
    content = _csv("0010,Cash,100,0,250,0", "A100-01,Rent,0,100,0,250")
    res = _preview(db, content)
    rows = {p["account_code"]: p for p in res["preview_rows"]}
    assert rows["0010"]["normalized"]["account_id"] == "acc_cash"
    assert rows["A100-01"]["normalized"]["account_id"] == "acc_rent"


def test_non_numeric_value_blocking():
    db = _DB()
    content = _csv("0010,Cash,abc,0,250,0", "3200,Sales,0,300,0,600")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_negative_values_accepted():
    db = _DB()
    # period debit -100 on cash, credit -100 on sales → still balanced (debit sum == credit sum).
    content = _csv("0010,Cash,-100,0,-250,0", "3200,Sales,0,-100,0,-250")
    res = _preview(db, content)
    assert res["status"] == "valid"


def test_period_unbalanced_rejected():
    db = _DB()
    content = _csv("0010,Cash,100,0,250,0", "3200,Sales,0,50,0,600")
    res = _preview(db, content)
    assert res["status"] == "failed"
    assert not res["controls"]["period_balanced"]


def test_ytd_unbalanced_rejected():
    db = _DB()
    content = _csv("0010,Cash,100,0,250,0", "3200,Sales,0,100,0,999")
    res = _preview(db, content)
    assert res["status"] == "failed"
    assert not res["controls"]["ytd_balanced"]


def test_tolerance_rounding_balanced():
    db = _DB()
    # 100.005 vs 100.00 within 0.01 tolerance
    content = _csv("0010,Cash,100.005,0,250,0", "3200,Sales,0,100,0,250")
    res = _preview(db, content)
    assert res["controls"]["period_balanced"]


def test_duplicate_exact_deduped_warning():
    db = _DB()
    content = _csv("0010,Cash,100,0,250,0", "0010,Cash,100,0,250,0", "3200,Sales,0,100,0,250")
    res = _preview(db, content)
    assert res["status"] == "valid"
    assert any(p["action"] == "skip" for p in res["preview_rows"])


def test_duplicate_conflicting_blocking():
    db = _DB()
    content = _csv("0010,Cash,100,0,250,0", "0010,Cash,200,0,250,0", "3200,Sales,0,300,0,500")
    res = _preview(db, content)
    assert res["status"] == "failed"


# ---- Financial context ----------------------------------------------------
def test_invalid_financial_year_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _preview(db, fy="fy_missing")
    assert e.value.status_code == 404


def test_invalid_financial_period_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _preview(db, fp="fp_missing")
    assert e.value.status_code == 404


def test_period_year_mismatch_422():
    db = _DB()
    # fp_2 belongs to CA but to fy_2, not FY → mismatch within the same company.
    with pytest.raises(HTTPException) as e:
        _preview(db, fp="fp_2")
    assert e.value.status_code == 422


def test_company_mismatch_404():
    db = _DB()
    # FY/FP belong to CA; importing under CB must not resolve them
    with pytest.raises(HTTPException) as e:
        _run(preview_trial_balance_import(db, CB, admin(), BALANCED, "tb.csv", FY, FP, "csv"))
    assert e.value.status_code == 404


# ---- Commit ---------------------------------------------------------------
def test_commit_writes_lines_and_counters():
    db = _DB()
    res = _preview(db)
    out = _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    assert out["status"] == "completed"
    assert out["records_created"] == 3
    assert len(db.trial_balance_lines.docs) == 3
    for l in db.trial_balance_lines.docs:
        assert l["import_id"] == res["id"] and l["financial_period_id"] == FP


def test_commit_blocking_rejected():
    db = _DB()
    res = _preview(db, _csv("0010,Cash,100,0,250,0", "3200,Sales,0,50,0,600"))
    with pytest.raises(HTTPException) as e:
        _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    assert e.value.status_code == 409
    assert len(db.trial_balance_lines.docs) == 0


def test_commit_twice_idempotent():
    db = _DB()
    res = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    again = _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    assert again.get("already_committed") is True
    assert len(db.trial_balance_lines.docs) == 3


def test_multiple_versions_same_period_allowed():
    db = _DB()
    r1 = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), r1["id"]))
    r2 = _preview(db)  # same period, new import → new version
    out2 = _run(commit_trial_balance_import(db, CA, admin(), r2["id"]))
    assert out2["records_created"] == 3
    assert len(db.trial_balance_lines.docs) == 6  # both versions preserved
    ids = {l["import_id"] for l in db.trial_balance_lines.docs}
    assert ids == {r1["id"], r2["id"]}


def test_import_lineage_preserved():
    db = _DB()
    r1 = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), r1["id"]))
    r2 = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), r2["id"]))
    v1 = _run(list_trial_balance(db, CA, admin(), import_id=r1["id"]))
    v2 = _run(list_trial_balance(db, CA, admin(), import_id=r2["id"]))
    assert v1["controls"]["line_count"] == 3 and v2["controls"]["line_count"] == 3


# ---- Read -----------------------------------------------------------------
def test_read_by_period_with_controls():
    db = _DB()
    res = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    out = _run(list_trial_balance(db, CA, admin(), financial_period_id=FP, import_id=res["id"]))
    assert out["controls"]["period_total_debit"] == 300.0
    assert out["controls"]["period_difference"] == 0.0
    assert len(out["lines"]) == 3


def test_read_by_import():
    db = _DB()
    res = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    out = _run(list_trial_balance(db, CA, admin(), import_id=res["id"]))
    assert len(out["lines"]) == 3


def test_read_account_filter():
    db = _DB()
    res = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    out = _run(list_trial_balance(db, CA, admin(), account_id="acc_cash"))
    assert len(out["lines"]) == 1 and out["lines"][0]["account_id"] == "acc_cash"


# ---- Security matrix (P1.12) ----------------------------------------------
def test_workspace_admin_can_import():
    db = _DB()
    res = _preview(db)
    assert res["status"] == "valid"


def test_authorized_user_can_read_tb():
    db = _DB()
    res = _preview(db)
    _run(commit_trial_balance_import(db, CA, admin(), res["id"]))
    out = _run(list_trial_balance(db, CA, reader(), import_id=res["id"]))
    assert len(out["lines"]) == 3


def test_company_user_can_read_but_not_import():
    db = _DB()
    _grant(db, "u_local", "company_user", "user")
    with pytest.raises(HTTPException) as e:
        _run(preview_trial_balance_import(db, CA, member("u_local"), BALANCED, "tb.csv", FY, FP, "csv"))
    assert e.value.status_code == 403


def test_company_local_admin_cannot_structurally_import():
    db = _DB()
    _grant(db, "u_ladmin", "company_user", "admin")
    with pytest.raises(HTTPException) as e:
        _run(preview_trial_balance_import(db, CA, member("u_ladmin"), BALANCED, "tb.csv", FY, FP, "csv"))
    assert e.value.status_code == 403


def test_unauthorized_user_denied_read():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_trial_balance(db, CA, member("u_nobody")))
    assert e.value.status_code == 403


def test_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_trial_balance(db, CA, platform_admin()))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e2:
        _run(preview_trial_balance_import(db, CA, platform_admin(), BALANCED, "tb.csv", FY, FP, "csv"))
    assert e2.value.status_code == 403


def test_cross_workspace_isolation_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(preview_trial_balance_import(db, "cmp_x", admin(ws=WS), BALANCED, "tb.csv", FY, FP, "csv"))
    assert e.value.status_code == 404
