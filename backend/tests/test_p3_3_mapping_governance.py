"""P3.3 — Mapping governance tests (in-memory)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.mappings import (
    MappingCreate, MappingUpdate, BulkConfirm, BulkConfirmItem,
    create_mapping, confirm_mapping, reject_mapping, update_mapping, bulk_confirm,
    list_mappings, mapping_coverage, mapping_readiness, resolve_confirmed_mapping,
    CONFIRMED, SUGGESTED, REJECTED,
)
from core.financial.mapping_import import import_preview, import_commit


def _matches(doc, query):
    for k, v in query.items():
        a = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and a == v["$ne"]:
                return False
            if "$in" in v and a not in v["$in"]:
                return False
        elif a != v:
            return False
    return True


class _Cursor:
    def __init__(self, d): self.d = list(d)
    async def to_list(self, _n=None): return [x.copy() for x in self.d]


class _Collection:
    def __init__(self, docs=None): self.docs = [d.copy() for d in (docs or [])]
    async def find_one(self, q): return next((d.copy() for d in self.docs if _matches(d, q)), None)
    def find(self, q): return _Cursor([d for d in self.docs if _matches(d, q)])
    async def count_documents(self, q): return sum(1 for d in self.docs if _matches(d, q))
    async def insert_one(self, d): self.docs.append(d.copy())
    async def update_one(self, q, u, upsert=False):
        for d in self.docs:
            if _matches(d, q): d.update(u.get("$set", {})); return
    async def create_index(self, *a, **k): return None
    async def drop_index(self, *a, **k): return None


WS = "ws_a"; CA = "cmp_a"
FP1, FP2, FP3 = "fp_1", "fp_2", "fp_3"


class _DB:
    def __init__(self):
        self.companies = _Collection([{"id": CA, "workspace_id": WS, "name": "A", "active": True, "status": "active"},
                                      {"id": "cmp_x", "workspace_id": "ws_x", "name": "X", "active": True, "status": "active"}])
        self.company_access = _Collection([])
        self.company_memberships = _Collection([])
        self.workspace_memberships = _Collection([])
        self.financial_periods = _Collection([
            {"_id": FP1, "workspace_id": WS, "company_id": CA, "sequence": 1, "period_code": "2099-01", "status": "open"},
            {"_id": FP2, "workspace_id": WS, "company_id": CA, "sequence": 2, "period_code": "2099-02", "status": "open"},
            {"_id": FP3, "workspace_id": WS, "company_id": CA, "sequence": 3, "period_code": "2099-03", "status": "open"},
            {"_id": "fpx", "workspace_id": "ws_x", "company_id": "cmp_x", "sequence": 1, "period_code": "X", "status": "open"}])
        self.accounts = _Collection([
            {"_id": "acc10", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True},
            {"_id": "acc32", "workspace_id": WS, "company_id": CA, "account_code": "3200", "account_name": "Sales", "active": True},
            {"_id": "acc40", "workspace_id": WS, "company_id": CA, "account_code": "4000", "account_name": "Rent", "active": True},
            {"_id": "accOFF", "workspace_id": WS, "company_id": CA, "account_code": "9999", "account_name": "Old", "active": False}])
        self.financial_concepts = _Collection([
            {"_id": "fc_cash", "concept_code": "CASH", "status": "active", "is_aggregate": False},
            {"_id": "fc_rev", "concept_code": "REVENUE", "status": "active", "is_aggregate": False},
            {"_id": "fc_rent", "concept_code": "RENT", "status": "active", "is_aggregate": False},
            {"_id": "fc_assets", "concept_code": "ASSETS", "status": "active", "is_aggregate": True}])
        self.account_mappings = _Collection([])
        self.data_imports = _Collection([])
        self.trial_balance_lines = _Collection([])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def padmin(ws=WS): return {"id": "pa", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)
def _grant(db, uid, mtype="workspace_staff", role="collaborator"):
    db.company_memberships.docs.append({"_id": f"m_{uid}", "workspace_id": WS, "company_id": CA,
                                        "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


def _mc(**kw):
    base = dict(account_id="acc10", financial_concept_id="fc_cash", effective_from_period_id=FP1)
    base.update(kw)
    return MappingCreate(**base)


# ---- Manual mapping -------------------------------------------------------
def test_manual_confirmed_creation():
    db = _DB()
    r = _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))
    assert r["status"] == CONFIRMED and r["confirmed_by"] == "admin"


def test_aggregate_concept_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), _mc(financial_concept_id="fc_assets", status="confirmed")))
    assert e.value.status_code == 422


def test_unknown_account_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), _mc(account_id="ghost")))
    assert e.value.status_code == 422


def test_unknown_concept_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), _mc(financial_concept_id="fc_ghost")))
    assert e.value.status_code == 422


# ---- Cardinality & periods ------------------------------------------------
def test_one_confirmed_per_account_period_resolution():
    db = _DB()
    r = _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))
    resolved = _run(resolve_confirmed_mapping(db, WS, CA, "acc10", FP1))
    assert resolved["id"] == r["id"]
    assert _run(resolve_confirmed_mapping(db, WS, CA, "acc32", FP1)) is None


def test_non_overlapping_confirmed_windows_accepted():
    db = _DB()
    _run(create_mapping(db, CA, admin(), _mc(effective_from_period_id=FP1, effective_to_period_id=FP1, status="confirmed")))
    _run(create_mapping(db, CA, admin(), _mc(financial_concept_id="fc_rev", effective_from_period_id=FP2, status="confirmed")))
    r1 = _run(resolve_confirmed_mapping(db, WS, CA, "acc10", FP1))
    r3 = _run(resolve_confirmed_mapping(db, WS, CA, "acc10", FP3))
    assert r1["financial_concept_id"] == "fc_cash" and r3["financial_concept_id"] == "fc_rev"


def test_overlapping_confirmed_rejected():
    db = _DB()
    _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), _mc(financial_concept_id="fc_rev", status="confirmed")))
    assert e.value.status_code == 409


def test_suggestions_may_overlap():
    db = _DB()
    _run(create_mapping(db, CA, admin(), _mc(status="suggested")))
    r2 = _run(create_mapping(db, CA, admin(), _mc(financial_concept_id="fc_rev", status="suggested")))
    assert r2["status"] == SUGGESTED
    assert _run(list_mappings(db, CA, admin(), account_id="acc10"))["count"] == 2


def test_invalid_sequence_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), _mc(effective_from_period_id=FP2, effective_to_period_id=FP1, status="confirmed")))
    assert e.value.status_code == 422


def test_period_from_other_company_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), _mc(effective_from_period_id="fpx", status="confirmed")))
    assert e.value.status_code == 422


# ---- Governance workflow --------------------------------------------------
def test_suggested_to_confirmed():
    db = _DB()
    s = _run(create_mapping(db, CA, admin(), _mc(status="suggested")))
    c = _run(confirm_mapping(db, CA, admin(), s["id"]))
    assert c["status"] == CONFIRMED


def test_suggested_to_rejected_preserves_history():
    db = _DB()
    s = _run(create_mapping(db, CA, admin(), _mc(status="suggested")))
    _run(reject_mapping(db, CA, admin(), s["id"], notes="non"))
    doc = next(d for d in db.account_mappings.docs if d["_id"] == s["id"])
    assert doc["status"] == REJECTED  # preserved, not deleted


def test_confirmed_supersession_preserves_history():
    db = _DB()
    first = _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))  # FP1 open
    second = _run(create_mapping(db, CA, admin(), _mc(financial_concept_id="fc_rev", effective_from_period_id=FP2, status="confirmed")))
    assert second["superseded_ids"] == [first["id"]]
    old = next(d for d in db.account_mappings.docs if d["_id"] == first["id"])
    assert old["superseded"] is True and old["effective_to_sequence"] == 1  # closed at predecessor of FP2
    assert len(db.account_mappings.docs) == 2  # history kept
    # resolution: FP1 -> first, FP3 -> second
    assert _run(resolve_confirmed_mapping(db, WS, CA, "acc10", FP1))["id"] == first["id"]
    assert _run(resolve_confirmed_mapping(db, WS, CA, "acc10", FP3))["id"] == second["id"]


def test_cannot_reject_confirmed():
    db = _DB()
    c = _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))
    with pytest.raises(HTTPException) as e:
        _run(reject_mapping(db, CA, admin(), c["id"]))
    assert e.value.status_code == 409


def test_resolve_integrity_error_on_double_confirmed():
    db = _DB()
    for i in (1, 2):
        db.account_mappings.docs.append({"_id": f"acm_{i}", "workspace_id": WS, "company_id": CA,
            "account_id": "acc10", "financial_concept_id": "fc_cash", "status": CONFIRMED,
            "superseded": False, "effective_from_sequence": 1, "effective_to_sequence": None})
    with pytest.raises(HTTPException) as e:
        _run(resolve_confirmed_mapping(db, WS, CA, "acc10", FP1))
    assert e.value.status_code == 500


# ---- Coverage -------------------------------------------------------------
def test_coverage_zero_accounts():
    db = _DB()
    db.accounts.docs = []
    cov = _run(mapping_coverage(db, CA, admin()))
    assert cov["total_active_accounts"] == 0 and cov["coverage_percentage"] == 0.0


def test_coverage_partial_and_inactive_excluded():
    db = _DB()
    _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))  # acc10 mapped
    _run(create_mapping(db, CA, admin(), _mc(account_id="acc32", financial_concept_id="fc_rev", status="suggested")))
    cov = _run(mapping_coverage(db, CA, admin(), financial_period_id=FP1))
    assert cov["total_active_accounts"] == 3  # accOFF inactive excluded
    assert cov["confirmed_accounts"] == 1
    assert cov["suggested_only_accounts"] == 1
    assert cov["unmapped_accounts"] == 2  # acc32 (suggested) + acc40
    assert cov["coverage_percentage"] == round(100 / 3, 2)


def test_coverage_all_mapped():
    db = _DB()
    for aid, cid in (("acc10", "fc_cash"), ("acc32", "fc_rev"), ("acc40", "fc_rent")):
        _run(create_mapping(db, CA, admin(), _mc(account_id=aid, financial_concept_id=cid, status="confirmed")))
    cov = _run(mapping_coverage(db, CA, admin(), financial_period_id=FP1))
    assert cov["fully_mapped"] is True and cov["coverage_percentage"] == 100.0


def _seed_tb(db, period=FP1):
    db.data_imports.docs.append({"_id": "imp", "workspace_id": WS, "company_id": CA,
        "data_type": "trial_balance", "financial_period_id": period, "status": "completed", "completed_at": "2099-02-01"})
    for i, (aid, net) in enumerate([("acc10", 800), ("acc32", 150), ("acc40", 50)]):
        db.trial_balance_lines.docs.append({"_id": f"tbl{i}", "workspace_id": WS, "company_id": CA,
            "import_id": "imp", "account_id": aid, "account_code": aid, "ytd_net": net})


def test_coverage_materiality():
    db = _DB(); _seed_tb(db)
    _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))  # acc10 mapped (800 of 1000)
    cov = _run(mapping_coverage(db, CA, admin(), financial_period_id=FP1))
    assert cov["materiality"]["materiality_coverage_percentage"] == 80.0
    assert cov["critical_unmapped_count"] == 2  # acc32, acc40 have balance
    assert cov["coverage_percentage"] == round(100 / 3, 2)


def test_coverage_without_tb_has_no_materiality():
    db = _DB()
    _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))
    cov = _run(mapping_coverage(db, CA, admin(), financial_period_id=FP1))
    assert "materiality" not in cov


def test_readiness_flag():
    db = _DB()
    for aid, cid in (("acc10", "fc_cash"), ("acc32", "fc_rev"), ("acc40", "fc_rent")):
        _run(create_mapping(db, CA, admin(), _mc(account_id=aid, financial_concept_id=cid, status="confirmed")))
    rd = _run(mapping_readiness(db, CA, admin(), FP1))
    assert rd["reporting_mapping_ready"] is True


# ---- Bulk -----------------------------------------------------------------
def test_bulk_all_valid():
    db = _DB()
    s1 = _run(create_mapping(db, CA, admin(), _mc(status="suggested")))
    s2 = _run(create_mapping(db, CA, admin(), _mc(account_id="acc32", financial_concept_id="fc_rev", status="suggested")))
    res = _run(bulk_confirm(db, CA, admin(), BulkConfirm(items=[BulkConfirmItem(mapping_id=s1["id"]), BulkConfirmItem(mapping_id=s2["id"])])))
    assert res["summary"] == {"confirmed": 2, "errors": 0}


def test_bulk_mixed_and_conflict_reported():
    db = _DB()
    s1 = _run(create_mapping(db, CA, admin(), _mc(status="suggested")))
    res = _run(bulk_confirm(db, CA, admin(), BulkConfirm(items=[
        BulkConfirmItem(mapping_id=s1["id"]),
        BulkConfirmItem(account_id="ghost", financial_concept_id="fc_rev", effective_from_period_id=FP1),
        BulkConfirmItem(account_id="acc32", financial_concept_id="fc_assets", effective_from_period_id=FP1)])))
    assert res["summary"]["confirmed"] == 1 and res["summary"]["errors"] == 2
    assert any(r["result"] == "error" for r in res["results"])  # no hidden partial success


def test_bulk_intra_batch_conflict():
    db = _DB()
    res = _run(bulk_confirm(db, CA, admin(), BulkConfirm(items=[
        BulkConfirmItem(account_id="acc10", financial_concept_id="fc_cash", effective_from_period_id=FP1),
        BulkConfirmItem(account_id="acc10", financial_concept_id="fc_rev", effective_from_period_id=FP1)])))
    assert res["summary"]["confirmed"] == 1 and res["summary"]["errors"] == 1


def test_bulk_dry_run_no_writes():
    db = _DB()
    s1 = _run(create_mapping(db, CA, admin(), _mc(status="suggested")))
    _run(bulk_confirm(db, CA, admin(), BulkConfirm(items=[BulkConfirmItem(mapping_id=s1["id"])], dry_run=True)))
    doc = next(d for d in db.account_mappings.docs if d["_id"] == s1["id"])
    assert doc["status"] == SUGGESTED  # untouched


# ---- Excel/CSV import -----------------------------------------------------
def test_import_preview_no_write_and_validations():
    db = _DB()
    rows = [
        {"account_code": "10", "concept_code": "CASH"},
        {"account_code": "3200", "concept_code": "REVENUE", "effective_from_period": "2099-01"},
        {"account_code": "9999", "concept_code": "CASH"},          # inactive/unknown active account
        {"account_code": "10", "concept_code": "ASSETS"},          # aggregate + duplicate/conflict
        {"account_code": "4000", "concept_code": "GHOST"},         # unknown concept
    ]
    pv = _run(import_preview(db, CA, admin(), rows))
    assert pv["summary"]["valid"] == 2
    assert pv["summary"]["errors"] >= 3
    assert db.account_mappings.docs == []  # preview writes nothing


def test_import_commit_default_suggested_and_idempotent():
    db = _DB()
    rows = [{"account_code": "10", "concept_code": "CASH"},
            {"account_code": "3200", "concept_code": "REVENUE"}]
    r1 = _run(import_commit(db, CA, admin(), rows))
    assert r1["imported_status"] == SUGGESTED and r1["summary"]["created"] == 2
    r2 = _run(import_commit(db, CA, admin(), rows))
    assert r2["summary"]["created"] == 0 and r2["summary"]["skipped"] == 2  # idempotent


def test_import_commit_confirmed_explicit():
    db = _DB()
    rows = [{"account_code": "10", "concept_code": "CASH"}]
    r = _run(import_commit(db, CA, admin(), rows, as_confirmed=True))
    assert r["imported_status"] == CONFIRMED and r["summary"]["created"] == 1


def test_import_commit_blocks_on_errors():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(import_commit(db, CA, admin(), [{"account_code": "GHOST", "concept_code": "CASH"}]))
    assert e.value.status_code == 422


# ---- Security -------------------------------------------------------------
def test_workspace_admin_write_ok():
    db = _DB()
    assert _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))["status"] == CONFIRMED


def test_members_can_read_write_denied():
    db = _DB()
    _run(create_mapping(db, CA, admin(), _mc(status="confirmed")))
    _grant(db, "u_pr", "workspace_staff", "principal")
    _grant(db, "u_co", "workspace_staff", "collaborator")
    _grant(db, "u_ca", "company_user", "admin")   # company-local admin
    _grant(db, "u_cu", "company_user", "user")
    for uid in ("u_pr", "u_co", "u_ca", "u_cu"):
        assert _run(list_mappings(db, CA, member(uid)))["count"] == 1  # read ok
    for uid in ("u_pr", "u_co", "u_ca", "u_cu"):
        with pytest.raises(HTTPException) as e:
            _run(create_mapping(db, CA, member(uid), _mc(account_id="acc32", financial_concept_id="fc_rev")))
        assert e.value.status_code == 403  # structural write denied


def test_unauthorized_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_mappings(db, CA, member("nobody")))
    assert e.value.status_code == 403


def test_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, padmin(), _mc(status="confirmed")))
    assert e.value.status_code == 403


def test_cross_workspace_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_mappings(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404
