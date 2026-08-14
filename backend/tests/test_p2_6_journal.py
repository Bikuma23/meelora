"""P2.6 — Normalized journal tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.journal import (
    preview_journal_import,
    commit_journal_import,
    list_journal_entries,
    get_journal_entry,
    aggregate_journal,
    parse_journal_file,
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
    def __init__(self, period_status="open"):
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
        ])
        self.financial_periods = _Collection([
            {"_id": FP, "workspace_id": WS, "company_id": CA, "financial_year_id": FY, "period_code": "2026-07",
             "label": "Juillet 2026", "start_date": "2026-07-01", "end_date": "2026-07-31", "sequence": 7, "status": period_status},
            {"_id": "fp_2", "workspace_id": WS, "company_id": CA, "financial_year_id": "fy_2", "period_code": "2027-01",
             "label": "Janvier 2027", "start_date": "2027-01-01", "end_date": "2027-01-31", "sequence": 1, "status": "open"},
        ])
        self.accounts = _Collection([
            _acc("0010", "acc_cash"), _acc("3200", "acc_sales"), _acc("A100-01", "acc_rent"),
        ])
        self.data_imports = _Collection([])
        self.journal_entries = _Collection([])
        self.journal_entry_lines = _Collection([])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def platform_admin(ws=WS): return {"id": "u_plat", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _grant(db, uid, mtype, role, cid=CA, ws=WS):
    db.company_memberships.docs.append({
        "_id": f"cpm_{uid}", "workspace_id": ws, "company_id": cid,
        "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


HEADER = "entry_id,entry_date,reference,description,account_code,line_description,debit,credit,external_entry_id,external_line_id"


def _csv(*lines) -> bytes:
    return ("\n".join([HEADER, *lines])).encode("utf-8")


# One balanced entry E1 (cash debit 100 / sales credit 100), date in July 2026.
E1 = _csv(
    "E1,2026-07-15,INV-1001,Invoice,0010,Cash,100,0,,",
    "E1,2026-07-15,INV-1001,Invoice,3200,Sales,0,100,,",
)


def _preview(db, content=E1, company=CA, user=None, fy=FY, fp=FP, name="j.csv", stype="import"):
    return _run(preview_journal_import(db, company, user or admin(), content, name, fy, fp, stype))


# ---- Parsing / preview ----------------------------------------------------
def test_parse_preserves_codes():
    rows = parse_journal_file(E1, "j.csv")
    assert {r["account_code"] for r in rows} == {"0010", "3200"}


def test_valid_balanced_entry():
    db = _DB()
    res = _preview(db)
    assert res["status"] == "valid"
    assert res["controls"]["entry_count"] == 1 and res["controls"]["line_count"] == 2
    assert res["controls"]["difference"] == 0.0


def test_preview_writes_nothing():
    db = _DB()
    _preview(db)
    assert len(db.journal_entries.docs) == 0 and len(db.journal_entry_lines.docs) == 0
    assert len(db.data_imports.docs) == 1


def test_multi_line_and_multiple_entries():
    db = _DB()
    content = _csv(
        "E1,2026-07-05,R1,d,0010,,60,0,,",
        "E1,2026-07-05,R1,d,A100-01,,40,0,,",
        "E1,2026-07-05,R1,d,3200,,0,100,,",
        "E2,2026-07-20,R2,d,0010,,0,50,,",
        "E2,2026-07-20,R2,d,3200,,50,0,,",
    )
    res = _preview(db, content)
    assert res["status"] == "valid"
    assert res["controls"]["entry_count"] == 2 and res["controls"]["line_count"] == 5


def test_unbalanced_entry_rejected():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,0010,,100,0,,", "E1,2026-07-15,R,d,3200,,0,50,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_missing_account_rejected():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,9999,,100,0,,", "E1,2026-07-15,R,d,3200,,0,100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"
    assert "9999" in res["controls"]["unresolved_codes"]


def test_leading_zero_and_punctuation_resolution():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,0010,,100,0,,", "E1,2026-07-15,R,d,A100-01,,0,100,,")
    res = _preview(db, content)
    e = res["entries_preview"][0]
    ids = {l["account_code"]: l["account_id"] for l in e["lines"]}
    assert ids["0010"] == "acc_cash" and ids["A100-01"] == "acc_rent"


def test_both_debit_credit_positive_rejected():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,0010,,100,100,,", "E1,2026-07-15,R,d,3200,,0,100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_zero_amount_line_rejected():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,0010,,0,0,,", "E1,2026-07-15,R,d,3200,,0,100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_negative_debit_rejected():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,0010,,-100,0,,", "E1,2026-07-15,R,d,3200,,0,100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_negative_credit_rejected():
    db = _DB()
    content = _csv("E1,2026-07-15,R,d,0010,,100,0,,", "E1,2026-07-15,R,d,3200,,0,-100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_date_inside_period_ok():
    db = _DB()
    res = _preview(db)  # 2026-07-15 within July
    assert res["status"] == "valid"


def test_date_before_period_rejected():
    db = _DB()
    content = _csv("E1,2026-06-30,R,d,0010,,100,0,,", "E1,2026-06-30,R,d,3200,,0,100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_date_after_period_rejected():
    db = _DB()
    content = _csv("E1,2026-08-01,R,d,0010,,100,0,,", "E1,2026-08-01,R,d,3200,,0,100,,")
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_period_year_mismatch_422():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _preview(db, fp="fp_2")  # fp_2 belongs to fy_2, not FY
    assert e.value.status_code == 422


def test_duplicate_conflicting_line_rejected():
    db = _DB()
    content = _csv(
        "E1,2026-07-15,R,d,0010,,100,0,L1,",
        "E1,2026-07-15,R,d,0010,,200,0,L1,",   # same external_line_id L1, different amount
        "E1,2026-07-15,R,d,3200,,0,100,,",
    )
    # Note: external_line_id goes in col 9; adjust — rebuild explicitly.
    content = ("\n".join([HEADER,
        "E1,2026-07-15,R,d,0010,,100,0,,L1",
        "E1,2026-07-15,R,d,0010,,200,0,,L1",
        "E1,2026-07-15,R,d,3200,,0,100,,"])).encode()
    res = _preview(db, content)
    assert res["status"] == "failed"


def test_exact_duplicate_line_deduped():
    db = _DB()
    content = ("\n".join([HEADER,
        "E1,2026-07-15,R,d,0010,,100,0,,",
        "E1,2026-07-15,R,d,0010,,100,0,,",   # exact duplicate → deduped
        "E1,2026-07-15,R,d,3200,,0,100,,"])).encode()
    res = _preview(db, content)
    assert res["status"] == "valid"
    e = res["entries_preview"][0]
    assert e["line_count"] == 2  # deduped to 2 lines
    assert any(w for w in e["warnings"])


# ---- Period status --------------------------------------------------------
def test_locked_period_rejects_import():
    db = _DB(period_status="locked")
    with pytest.raises(HTTPException) as e:
        _preview(db)
    assert e.value.status_code == 409


def test_closed_period_rejects_import():
    db = _DB(period_status="closed")
    with pytest.raises(HTTPException) as e:
        _preview(db)
    assert e.value.status_code == 409


def test_reopened_period_accepts():
    db = _DB(period_status="locked")
    with pytest.raises(HTTPException):
        _preview(db)
    # admin reopens
    for p in db.financial_periods.docs:
        if p["_id"] == FP:
            p["status"] = "open"
    res = _preview(db)
    assert res["status"] == "valid"


def test_locked_period_rejects_commit():
    db = _DB()  # open at preview
    res = _preview(db)
    for p in db.financial_periods.docs:
        if p["_id"] == FP:
            p["status"] = "locked"
    with pytest.raises(HTTPException) as e:
        _run(commit_journal_import(db, CA, admin(), res["id"]))
    assert e.value.status_code == 409


# ---- Commit ---------------------------------------------------------------
def test_commit_creates_entries_and_lines():
    db = _DB()
    res = _preview(db)
    out = _run(commit_journal_import(db, CA, admin(), res["id"]))
    assert out["status"] == "completed"
    assert out["entry_count"] == 1 and out["line_count"] == 2
    assert len(db.journal_entries.docs) == 1 and len(db.journal_entry_lines.docs) == 2
    line_numbers = sorted(l["line_number"] for l in db.journal_entry_lines.docs)
    assert line_numbers == [1, 2]


def test_commit_blocking_rejected():
    db = _DB()
    res = _preview(db, _csv("E1,2026-07-15,R,d,0010,,100,0,,", "E1,2026-07-15,R,d,3200,,0,50,,"))
    with pytest.raises(HTTPException) as e:
        _run(commit_journal_import(db, CA, admin(), res["id"]))
    assert e.value.status_code == 409
    assert len(db.journal_entries.docs) == 0


def test_commit_twice_idempotent():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    again = _run(commit_journal_import(db, CA, admin(), res["id"]))
    assert again.get("already_committed") is True
    assert len(db.journal_entries.docs) == 1 and len(db.journal_entry_lines.docs) == 2


def test_multiple_import_versions_allowed():
    db = _DB()
    r1 = _preview(db)
    _run(commit_journal_import(db, CA, admin(), r1["id"]))
    r2 = _preview(db)
    _run(commit_journal_import(db, CA, admin(), r2["id"]))
    assert len(db.journal_entries.docs) == 2
    ids = {e["import_id"] for e in db.journal_entries.docs}
    assert ids == {r1["id"], r2["id"]}


def test_import_lineage_preserved():
    db = _DB()
    r1 = _preview(db)
    _run(commit_journal_import(db, CA, admin(), r1["id"]))
    entries = _run(list_journal_entries(db, CA, admin(), import_id=r1["id"]))
    assert len(entries) == 1 and entries[0]["import_id"] == r1["id"]


def test_external_entry_id_preserved():
    db = _DB()
    content = ("\n".join([HEADER,
        "E1,2026-07-15,INV,Invoice,0010,,100,0,XE-1,",
        "E1,2026-07-15,INV,Invoice,3200,,0,100,XE-1,"])).encode()
    res = _preview(db, content)
    out = _run(commit_journal_import(db, CA, admin(), res["id"]))
    e = db.journal_entries.docs[0]
    assert e["external_id"] == "XE-1"


# ---- Read / aggregate -----------------------------------------------------
def test_read_entry_and_list():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    je = db.journal_entries.docs[0]["_id"]
    detail = _run(get_journal_entry(db, CA, je, admin()))
    assert len(detail["lines"]) == 2 and detail["entry_debit"] == 100.0
    lst = _run(list_journal_entries(db, CA, admin(), financial_period_id=FP))
    assert len(lst) == 1


def test_list_by_import_and_account_filter():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    assert len(_run(list_journal_entries(db, CA, admin(), import_id=res["id"]))) == 1
    ent = _run(list_journal_entries(db, CA, admin(), account_id="acc_cash"))
    assert len(ent) == 1
    assert len(_run(list_journal_entries(db, CA, admin(), account_id="acc_nope"))) == 0


def test_date_and_reference_filters():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    assert len(_run(list_journal_entries(db, CA, admin(), date_from="2026-07-01", date_to="2026-07-31"))) == 1
    assert len(_run(list_journal_entries(db, CA, admin(), date_from="2026-08-01"))) == 0
    assert len(_run(list_journal_entries(db, CA, admin(), reference="inv-1001"))) == 1
    assert len(_run(list_journal_entries(db, CA, admin(), reference="zzz"))) == 0


def test_aggregate_totals_and_by_account():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    agg = _run(aggregate_journal(db, CA, admin(), financial_period_id=FP))
    assert agg["total_debit"] == 100.0 and agg["total_credit"] == 100.0 and agg["difference"] == 0.0
    codes = {a["account_code"]: a for a in agg["by_account"]}
    assert codes["0010"]["net"] == 100.0 and codes["3200"]["net"] == -100.0


# ---- Security matrix ------------------------------------------------------
def test_workspace_admin_import():
    db = _DB()
    assert _preview(db)["status"] == "valid"


def test_principal_and_collaborator_read():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    _grant(db, "u_princ", "workspace_staff", "principal")
    _grant(db, "u_collab", "workspace_staff", "collaborator")
    assert len(_run(list_journal_entries(db, CA, member("u_princ")))) == 1
    assert len(_run(list_journal_entries(db, CA, member("u_collab")))) == 1


def test_company_admin_and_user_read_but_not_import():
    db = _DB()
    res = _preview(db)
    _run(commit_journal_import(db, CA, admin(), res["id"]))
    _grant(db, "u_ca", "company_user", "admin")
    _grant(db, "u_cu", "company_user", "user")
    assert len(_run(list_journal_entries(db, CA, member("u_ca")))) == 1
    assert len(_run(list_journal_entries(db, CA, member("u_cu")))) == 1
    with pytest.raises(HTTPException) as e:
        _run(preview_journal_import(db, CA, member("u_ca"), E1, "j.csv", FY, FP, "import"))
    assert e.value.status_code == 403


def test_unauthorized_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_journal_entries(db, CA, member("u_nobody")))
    assert e.value.status_code == 403


def test_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_journal_entries(db, CA, platform_admin()))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e2:
        _run(preview_journal_import(db, CA, platform_admin(), E1, "j.csv", FY, FP, "import"))
    assert e2.value.status_code == 403


def test_cross_workspace_isolation_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(preview_journal_import(db, "cmp_x", admin(ws=WS), E1, "j.csv", FY, FP, "import"))
    assert e.value.status_code == 404
