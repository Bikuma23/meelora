"""P2.4 — Data imports registry & lifecycle tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.data_imports import (
    preview_accounts_import,
    commit_accounts_import,
    list_imports,
    get_import,
    parse_accounts_file,
)


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in value):
                return False
            continue
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
        self.accounts = _Collection([])
        self.data_imports = _Collection([])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def platform_admin(ws=WS): return {"id": "u_plat", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _grant(db, uid, mtype, role, cid=CA, ws=WS):
    db.company_memberships.docs.append({
        "_id": f"cpm_{uid}", "workspace_id": ws, "company_id": cid,
        "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


HEADER = "account_code,account_name,account_type,normal_balance,currency,external_id"


def _csv(*lines) -> bytes:
    return ("\n".join([HEADER, *lines])).encode("utf-8")


GOOD = _csv(
    "0010,Cash,asset,debit,,EXT-1",
    "3200,Sales,revenue,credit,EUR,",
    "4.100,Other,other,debit,,",
    "A100-01,Rent,expense,debit,,",
)


def _preview(db, content=GOOD, company=CA, user=None, name="chart.csv", stype="csv"):
    return _run(preview_accounts_import(db, company, user or admin(), content, name, stype))


# ---- Parsing / preview ----------------------------------------------------
def test_parse_preserves_code_string():
    rows = parse_accounts_file(GOOD, "chart.csv")
    codes = [r["account_code"] for r in rows]
    assert codes == ["0010", "3200", "4.100", "A100-01"]


def test_preview_creates_import_record_and_does_not_write_accounts():
    db = _DB()
    res = _preview(db)
    assert res["id"].startswith("imp_")
    assert res["status"] == "valid"
    assert res["records_received"] == 4
    assert res["records_created"] == 0 and res["records_updated"] == 0
    # Preview must NOT touch accounts.
    assert len(db.accounts.docs) == 0
    assert len(db.data_imports.docs) == 1


def test_preview_leading_zero_and_punctuation_preserved():
    db = _DB()
    res = _preview(db)
    codes = [p["account_code"] for p in res["preview_rows"]]
    assert "0010" in codes and "4.100" in codes and "A100-01" in codes


def test_preview_currency_inheritance_warning_and_explicit():
    db = _DB()
    res = _preview(db)
    rows = {p["account_code"]: p for p in res["preview_rows"]}
    assert any("héritée" in w for w in rows["0010"]["warnings"])  # inherited CHF
    # explicit EUR row: no inheritance warning
    assert not any("héritée" in w for w in rows["3200"]["warnings"])


def test_preview_external_id_missing_warning():
    db = _DB()
    res = _preview(db)
    rows = {p["account_code"]: p for p in res["preview_rows"]}
    assert any("external_id absent" in w for w in rows["3200"]["warnings"])


def test_preview_missing_required_fields_blocking():
    db = _DB()
    content = _csv(",No code,asset,debit,,", "5000,,expense,debit,,")
    res = _preview(db, content)
    assert res["status"] == "failed"
    assert res["records_rejected"] == 2


def test_preview_invalid_account_type_blocking():
    db = _DB()
    res = _preview(db, _csv("1000,Bad,bogus,debit,,"))
    assert res["status"] == "failed" and res["records_rejected"] == 1


def test_preview_invalid_normal_balance_blocking():
    db = _DB()
    res = _preview(db, _csv("1000,Bad,asset,sideways,,"))
    assert res["status"] == "failed" and res["records_rejected"] == 1


def test_preview_duplicate_conflicting_rows_blocking():
    db = _DB()
    res = _preview(db, _csv("1000,Cash,asset,debit,,", "1000,Different,revenue,credit,,"))
    assert res["status"] == "failed"


def test_preview_duplicate_identical_rows_deduped_warning():
    db = _DB()
    res = _preview(db, _csv("1000,Cash,asset,debit,CHF,", "1000,Cash,asset,debit,CHF,"))
    assert res["status"] == "valid"
    actions = [p["action"] for p in res["preview_rows"]]
    assert "skip" in actions


def test_preview_existing_account_update_warning():
    db = _DB()
    db.accounts.docs.append({"_id": "acc_1", "workspace_id": WS, "company_id": CA,
                             "account_code": "3200", "account_name": "Old", "account_type": "revenue",
                             "normal_balance": "credit", "currency": "CHF", "active": True, "source_system": "csv"})
    res = _preview(db)
    rows = {p["account_code"]: p for p in res["preview_rows"]}
    assert rows["3200"]["action"] == "update"


# ---- Commit ---------------------------------------------------------------
def test_commit_creates_accounts_and_counters():
    db = _DB()
    res = _preview(db)
    out = _run(commit_accounts_import(db, CA, admin(), res["id"]))
    assert out["status"] == "completed_with_warnings"  # inheritance/external warnings present
    assert out["records_created"] == 4 and out["records_updated"] == 0
    assert len(db.accounts.docs) == 4
    # code preserved on persisted accounts
    assert {a["account_code"] for a in db.accounts.docs} == {"0010", "3200", "4.100", "A100-01"}


def test_commit_updates_existing_accounts():
    db = _DB()
    db.accounts.docs.append({"_id": "acc_1", "workspace_id": WS, "company_id": CA,
                             "account_code": "3200", "account_name": "Old", "account_type": "revenue",
                             "normal_balance": "credit", "currency": "EUR", "active": True, "source_system": "csv"})
    res = _preview(db)
    out = _run(commit_accounts_import(db, CA, admin(), res["id"]))
    assert out["records_created"] == 3 and out["records_updated"] == 1
    updated = next(a for a in db.accounts.docs if a["account_code"] == "3200")
    assert updated["account_name"] == "Sales"


def test_commit_currency_inheritance_persisted():
    db = _DB()
    res = _preview(db)
    _run(commit_accounts_import(db, CA, admin(), res["id"]))
    cash = next(a for a in db.accounts.docs if a["account_code"] == "0010")
    assert cash["currency"] == "CHF"  # inherited from company
    sales = next(a for a in db.accounts.docs if a["account_code"] == "3200")
    assert sales["currency"] == "EUR"  # explicit


def test_commit_external_id_preserved():
    db = _DB()
    res = _preview(db)
    _run(commit_accounts_import(db, CA, admin(), res["id"]))
    cash = next(a for a in db.accounts.docs if a["account_code"] == "0010")
    assert cash["external_id"] == "EXT-1" and cash["source_system"] == "csv"


def test_commit_blocking_errors_rejected():
    db = _DB()
    res = _preview(db, _csv("1000,Bad,bogus,debit,,"))
    with pytest.raises(HTTPException) as e:
        _run(commit_accounts_import(db, CA, admin(), res["id"]))
    assert e.value.status_code == 409
    assert len(db.accounts.docs) == 0


def test_commit_twice_is_idempotent_noop():
    db = _DB()
    res = _preview(db)
    first = _run(commit_accounts_import(db, CA, admin(), res["id"]))
    again = _run(commit_accounts_import(db, CA, admin(), res["id"]))
    assert again.get("already_committed") is True
    assert first["records_created"] == 4
    assert len(db.accounts.docs) == 4  # not doubled


def test_same_source_retry_is_safe():
    db = _DB()
    r1 = _preview(db)
    _run(commit_accounts_import(db, CA, admin(), r1["id"]))
    # Re-upload the exact same file → new preview, but commit must no-op (same checksum).
    r2 = _preview(db)
    out2 = _run(commit_accounts_import(db, CA, admin(), r2["id"]))
    assert out2["status"] == "completed_with_warnings"
    assert out2["records_created"] == 0 and out2["records_updated"] == 0
    assert len(db.accounts.docs) == 4  # no duplicate normalized accounts


def test_changed_source_reimport_allowed():
    db = _DB()
    r1 = _preview(db)
    _run(commit_accounts_import(db, CA, admin(), r1["id"]))
    # Different content (adds a row) → different checksum → real commit applies.
    changed = GOOD + b"\n6000,Wages,expense,debit,,"
    r2 = _preview(db, changed)
    out2 = _run(commit_accounts_import(db, CA, admin(), r2["id"]))
    assert out2["records_created"] == 1 and out2["records_updated"] == 4
    assert len(db.accounts.docs) == 5


def test_upsert_matches_external_id_over_code():
    db = _DB()
    db.accounts.docs.append({"_id": "acc_ext", "workspace_id": WS, "company_id": CA,
                             "account_code": "OLD", "account_name": "Legacy", "account_type": "asset",
                             "normal_balance": "debit", "currency": "CHF", "active": True,
                             "source_system": "csv", "external_id": "EXT-1"})
    res = _preview(db)  # row 0010 has external_id EXT-1
    out = _run(commit_accounts_import(db, CA, admin(), res["id"]))
    # matched by external_id → code updated to 0010, no new account for it
    matched = next(a for a in db.accounts.docs if a["external_id"] == "EXT-1")
    assert matched["account_code"] == "0010"
    assert out["records_updated"] >= 1


# ---- History --------------------------------------------------------------
def test_import_history_list_and_detail():
    db = _DB()
    res = _preview(db)
    lst = _run(list_imports(db, CA, admin()))
    assert len(lst) == 1 and lst[0]["id"] == res["id"]
    detail = _run(get_import(db, CA, res["id"], admin()))
    assert detail["id"] == res["id"]


def test_history_filter_by_data_type_and_status():
    db = _DB()
    _preview(db)
    assert len(_run(list_imports(db, CA, admin(), data_type="accounts"))) == 1
    assert len(_run(list_imports(db, CA, admin(), data_type="transactions"))) == 0
    assert len(_run(list_imports(db, CA, admin(), status="valid"))) == 1
    assert len(_run(list_imports(db, CA, admin(), status="failed"))) == 0


def test_history_filter_by_source_type():
    db = _DB()
    _preview(db)
    assert len(_run(list_imports(db, CA, admin(), source_type="csv"))) == 1
    assert len(_run(list_imports(db, CA, admin(), source_type="excel"))) == 0


# ---- Security matrix (P1.12) ----------------------------------------------
def test_reader_via_legacy_bridge_can_read_history():
    db = _DB()
    _preview(db)
    assert len(_run(list_imports(db, CA, reader()))) == 1


def test_company_user_can_read_history_but_not_import():
    db = _DB()
    _grant(db, "u_local", "company_user", "user")
    _preview(db)  # created by admin
    assert len(_run(list_imports(db, CA, member("u_local")))) == 1
    with pytest.raises(HTTPException) as e:
        _run(preview_accounts_import(db, CA, member("u_local"), GOOD, "c.csv", "csv"))
    assert e.value.status_code == 403


def test_company_local_admin_cannot_structurally_import():
    db = _DB()
    _grant(db, "u_ladmin", "company_user", "admin")
    with pytest.raises(HTTPException) as e:
        _run(preview_accounts_import(db, CA, member("u_ladmin"), GOOD, "c.csv", "csv"))
    assert e.value.status_code == 403


def test_workspace_staff_principal_can_read_history():
    db = _DB()
    _grant(db, "u_princ", "workspace_staff", "principal")
    _preview(db)
    assert len(_run(list_imports(db, CA, member("u_princ")))) == 1


def test_unauthorized_user_denied_history():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_imports(db, CA, member("u_nobody")))
    assert e.value.status_code == 403


def test_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_imports(db, CA, platform_admin()))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e2:
        _run(preview_accounts_import(db, CA, platform_admin(), GOOD, "c.csv", "csv"))
    assert e2.value.status_code == 403


def test_cross_workspace_isolation_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(preview_accounts_import(db, "cmp_x", admin(ws=WS), GOOD, "c.csv", "csv"))
    assert e.value.status_code == 404


def test_company_mismatch_import_detail_404():
    db = _DB()
    res = _preview(db)  # belongs to CA
    with pytest.raises(HTTPException) as e:
        _run(get_import(db, CB, res["id"], admin()))
    assert e.value.status_code == 404


def test_commit_wrong_company_404():
    db = _DB()
    res = _preview(db)
    with pytest.raises(HTTPException) as e:
        _run(commit_accounts_import(db, CB, admin(), res["id"]))
    assert e.value.status_code == 404
