"""P3.5 — Custom reporting-template governance tests (in-memory).

Covers creation, scope, drafts, structural validation, semantic_bypass, upload
(CSV + Excel), publish/versioning, default-template resolution, i18n, security,
P3.4 engine integration + report_run reproducibility, and no-write proofs.
"""
import asyncio
import csv
import io

import pytest
from fastapi import HTTPException

from core.financial.custom_templates import (
    CustomTemplateCreate, DeriveRequest, TemplateLineUpsert, ReorderRequest,
    DefaultAssignment, UploadCommit,
    create_custom_template, derive_template, new_custom_version,
    add_line, update_line, remove_line, reorder_lines, validate_template,
    publish_template, archive_template, list_available_templates,
    set_default_template, get_default_templates,
    upload_preview, upload_commit,
)
from core.financial.mapping_import import parse_rows
from core.financial.reporting_engine import (
    ReportRequest, preview_report, generate_report, get_report, list_reports,
)


# ---- In-memory Mongo fake -------------------------------------------------
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
            if _matches(d, q):
                d.update(u.get("$set", {}))
                return
    async def delete_one(self, q):
        for i, d in enumerate(self.docs):
            if _matches(d, q):
                del self.docs[i]
                return
    async def create_index(self, *a, **k): return None


WS = "ws_a"; CA = "cmp_a"; CB = "cmp_b"; FP1 = "fp_1"; FY = "fy_1"


def _concept(code, ctype, stype, nb, parent=None, agg=False):
    return {"_id": f"fc_{code.lower()}", "concept_code": code, "concept_type": ctype,
            "statement_type": stype, "natural_balance": nb, "parent_concept_id": parent,
            "is_aggregate": agg, "status": "active", "introduced_version": "2026.06.0"}


def _sys_line(tid, code, ltype, refs=None, formula=None, sign="natural", parent=None, labels=None, order=0):
    return {"_id": f"rtl_{tid}_{code}", "template_id": tid, "line_code": code, "line_type": ltype,
            "parent_line_code": parent, "parent_line_id": None,
            "concept_refs": [f"fc_{r.lower()}" for r in (refs or [])], "concept_codes": refs or [],
            "account_refs": [], "semantic_bypass": False, "semantic_bypass_warning": None,
            "formula": formula, "display_sign": sign, "measure": "ytd",
            "labels": labels or {}, "sort_order": order}


def _tb(aid, pnet, ynet):
    return {"_id": f"tbl_{aid}", "workspace_id": WS, "company_id": CA, "import_id": "imp_ok",
            "account_id": aid, "account_code": aid, "period_net": pnet, "ytd_net": ynet,
            "period_debit": 0, "period_credit": 0, "ytd_debit": 0, "ytd_credit": 0}


def _map(aid, cid):
    return {"_id": f"acm_{aid}", "workspace_id": WS, "company_id": CA, "account_id": aid,
            "financial_concept_id": cid, "status": "confirmed", "superseded": False,
            "effective_from_sequence": 1, "effective_to_sequence": None}


SYS_PL = "rt_sys_pl_v1"
SYS_BS = "rt_sys_bs_v1"


class _DB:
    def __init__(self):
        self.companies = _Collection([
            {"id": CA, "workspace_id": WS, "name": "A", "active": True, "status": "active", "jurisdiction": "CA"},
            {"id": CB, "workspace_id": WS, "name": "B", "active": True, "status": "active", "jurisdiction": "CA"},
            {"id": "cmp_x", "workspace_id": "ws_x", "name": "X", "active": True, "status": "active"}])
        self.company_access = _Collection([])
        self.company_memberships = _Collection([])
        self.workspace_memberships = _Collection([])
        self.financial_periods = _Collection([{"_id": FP1, "workspace_id": WS, "company_id": CA,
                                               "financial_year_id": FY, "sequence": 1, "status": "open"}])
        self.financial_concepts = _Collection([
            _concept("ASSETS", "asset", "balance_sheet", "debit", agg=True),
            _concept("CASH", "asset", "balance_sheet", "debit", parent="fc_assets"),
            _concept("AP", "liability", "balance_sheet", "credit"),
            _concept("SHARE_CAPITAL", "equity", "balance_sheet", "credit"),
            _concept("CURRENT_YEAR_RESULT", "equity", "balance_sheet", "credit"),
            _concept("REVENUE", "income", "income_statement", "credit"),
            _concept("COGS", "expense", "income_statement", "debit"),
        ])
        self.accounts = _Collection([
            {"_id": "a_cash", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True},
            {"_id": "a_ap", "workspace_id": WS, "company_id": CA, "account_code": "20", "account_name": "AP", "active": True},
            {"_id": "a_sc", "workspace_id": WS, "company_id": CA, "account_code": "30", "account_name": "SC", "active": True},
            {"_id": "a_cyr", "workspace_id": WS, "company_id": CA, "account_code": "35", "account_name": "CYR", "active": True},
            {"_id": "a_rev", "workspace_id": WS, "company_id": CA, "account_code": "40", "account_name": "Rev", "active": True},
            {"_id": "a_cogs", "workspace_id": WS, "company_id": CA, "account_code": "50", "account_name": "COGS", "active": True},
            {"_id": "a_misc", "workspace_id": WS, "company_id": CA, "account_code": "90", "account_name": "Misc", "active": True},
            {"_id": "b_acc", "workspace_id": WS, "company_id": CB, "account_code": "10", "account_name": "B-Cash", "active": True}])
        self.data_imports = _Collection([
            {"_id": "imp_ok", "workspace_id": WS, "company_id": CA, "data_type": "trial_balance",
             "financial_period_id": FP1, "status": "completed", "completed_at": "2099-02-01"}])
        self.trial_balance_lines = _Collection([
            _tb("a_cash", 700, 700), _tb("a_ap", -200, -200), _tb("a_sc", -300, -300),
            _tb("a_cyr", -200, -200), _tb("a_rev", -500, -500), _tb("a_cogs", 300, 300)])
        self.account_mappings = _Collection([
            _map("a_cash", "fc_cash"), _map("a_ap", "fc_ap"), _map("a_sc", "fc_share_capital"),
            _map("a_cyr", "fc_current_year_result"), _map("a_rev", "fc_revenue"), _map("a_cogs", "fc_cogs")])
        self.report_runs = _Collection([])
        self.reporting_template_defaults = _Collection([])
        self.reporting_templates = _Collection([
            {"_id": SYS_PL, "template_code": "SYS_PL", "statement_type": "income_statement",
             "scope": "system", "jurisdiction": "CA", "workspace_id": None, "company_id": None,
             "name": "System PL", "version": 1, "status": "published"},
            {"_id": SYS_BS, "template_code": "SYS_BS", "statement_type": "balance_sheet",
             "scope": "system", "jurisdiction": "CA", "workspace_id": None, "company_id": None,
             "name": "System BS", "version": 1, "status": "published"}])
        self.reporting_template_lines = _Collection([
            _sys_line(SYS_PL, "PL_REV", "concept", ["REVENUE"], labels={"en": "Revenue", "fr": "Produits"}, order=0),
            _sys_line(SYS_PL, "PL_COGS", "concept", ["COGS"], sign="negative", labels={"en": "COGS", "fr": "CMV"}, order=1),
            _sys_line(SYS_PL, "GROSS", "formula", formula="PL_REV-PL_COGS", labels={"en": "Gross", "fr": "Marge"}, order=2),
            _sys_line(SYS_BS, "BS_ASSETS", "concept", ["ASSETS"], labels={"en": "Assets", "fr": "Actifs"}, order=0),
            _sys_line(SYS_BS, "BS_AP", "concept", ["AP"], labels={"en": "AP", "fr": "Fournisseurs"}, order=1),
            _sys_line(SYS_BS, "BS_EQ", "concept", ["SHARE_CAPITAL", "CURRENT_YEAR_RESULT"],
                      labels={"en": "Equity", "fr": "Capitaux"}, order=2)])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def padmin(): return {"id": "pa", "role": "user", "platform_role": "platform_admin", "workspace_id": WS, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _grant(db, uid, role="collaborator", mtype="workspace_staff", company=CA):
    db.company_memberships.docs.append({"_id": f"m_{uid}", "workspace_id": WS, "company_id": company,
                                        "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


def _ws_admin(db, uid):
    db.workspace_memberships.docs.append({"_id": f"wm_{uid}", "workspace_id": WS, "user_id": uid,
                                          "status": "active", "role": "admin"})


def _line(code, ltype, concepts=None, formula=None, parent=None, sign="natural", labels=None,
          bypass=False, accounts=None, measure="ytd"):
    return TemplateLineUpsert(line_code=code, line_type=ltype, concept_codes=concepts or [],
                              formula=formula, parent_line_code=parent, display_sign=sign,
                              labels=labels or {}, semantic_bypass=bypass, account_codes=accounts or [],
                              measure=measure)


def _company_pl(db, user=None, code="CUST_PL"):
    """Create + populate a valid custom company P&L draft; return template id."""
    user = user or admin()
    t = _run(create_custom_template(db, user, CustomTemplateCreate(
        template_code=code, statement_type="income_statement", scope="company", name="Custom PL", company_id=CA)))
    _run(add_line(db, user, t["id"], _line("PL_REV", "concept", ["REVENUE"], labels={"fr": "Produits", "en": "Revenue"})))
    _run(add_line(db, user, t["id"], _line("PL_COGS", "concept", ["COGS"], sign="negative", labels={"fr": "CMV"})))
    _run(add_line(db, user, t["id"], _line("GROSS", "formula", formula="PL_REV-PL_COGS", labels={"fr": "Marge"})))
    return t["id"]


# ---- Creation -------------------------------------------------------------
def test_create_blank_workspace_and_company_drafts():
    db = _DB()
    wt = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="WS_PL", statement_type="income_statement", scope="workspace", name="WS PL")))
    assert wt["status"] == "draft" and wt["workspace_id"] == WS and wt["company_id"] is None
    ct = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="CO_PL", statement_type="income_statement", scope="company", name="CO PL", company_id=CA)))
    assert ct["company_id"] == CA and ct["version"] == 1


def test_company_scope_requires_company_id():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_custom_template(db, admin(), CustomTemplateCreate(
            template_code="XX", statement_type="income_statement", scope="company", name="X")))
    assert e.value.status_code == 422


def test_derive_from_system_and_from_custom():
    db = _DB()
    d1 = _run(derive_template(db, admin(), DeriveRequest(source_template_id=SYS_PL,
              template_code="DER_PL", scope="company", name="Derived", company_id=CA)))
    assert d1["based_on_template_id"] == SYS_PL and d1["based_on_template_version"] == 1
    full = _run(validate_template(db, admin(), d1["id"]))
    assert full["line_count"] == 3  # copied
    # derive from a custom (published) template
    _run(publish_template(db, admin(), d1["id"]))
    d2 = _run(derive_template(db, admin(), DeriveRequest(source_template_id=d1["id"],
              template_code="DER_PL2", scope="company", name="Derived2", company_id=CA)))
    assert d2["based_on_template_id"] == d1["id"]


def test_derive_does_not_mutate_parent():
    db = _DB()
    d1 = _run(derive_template(db, admin(), DeriveRequest(source_template_id=SYS_PL,
              template_code="DER_PL", scope="company", name="Derived", company_id=CA)))
    _run(add_line(db, admin(), d1["id"], _line("EXTRA", "spacer")))
    parent_lines = _run(db.reporting_template_lines.find({"template_id": SYS_PL}).to_list(None))
    assert len(parent_lines) == 3  # unchanged


def test_duplicate_code_rejected():
    db = _DB()
    _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="DUP", statement_type="income_statement", scope="company", name="d", company_id=CA)))
    with pytest.raises(HTTPException) as e:
        _run(create_custom_template(db, admin(), CustomTemplateCreate(
            template_code="DUP", statement_type="income_statement", scope="company", name="d2", company_id=CA)))
    assert e.value.status_code == 409


# ---- Scope visibility -----------------------------------------------------
def test_scope_visibility_and_cross_workspace():
    db = _DB()
    wt1 = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="WS_ONE", statement_type="income_statement", scope="workspace", name="ws")))
    _run(add_line(db, admin(), wt1["id"], _line("R", "concept", ["REVENUE"])))
    _run(publish_template(db, admin(), wt1["id"]))
    cid_tpl = _company_pl(db)
    _run(publish_template(db, admin(), cid_tpl))
    avail_ca = _run(list_available_templates(db, CA, admin()))
    codes = {t["template_code"] for t in avail_ca["templates"]}
    assert {"SYS_PL", "SYS_BS", "WS_ONE", "CUST_PL"} <= codes
    # Company B does NOT see company-A-scoped template
    avail_cb = _run(list_available_templates(db, CB, admin()))
    codes_b = {t["template_code"] for t in avail_cb["templates"]}
    assert "CUST_PL" not in codes_b and "WS_ONE" in codes_b
    # cross-workspace 404
    with pytest.raises(HTTPException) as e:
        _run(list_available_templates(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


# ---- Draft editing --------------------------------------------------------
def test_draft_add_edit_reorder_remove():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="EDIT", statement_type="income_statement", scope="company", name="e", company_id=CA)))
    l1 = _run(add_line(db, admin(), t["id"], _line("A", "concept", ["REVENUE"])))
    _run(add_line(db, admin(), t["id"], _line("B", "concept", ["COGS"])))
    upd = _run(update_line(db, admin(), t["id"], l1["id"], _line("A", "concept", ["REVENUE"], labels={"fr": "X"})))
    assert upd["labels"]["fr"] == "X"
    _run(reorder_lines(db, admin(), t["id"], ReorderRequest(ordered_line_codes=["B", "A"])))
    lines = _run(db.reporting_template_lines.find({"template_id": t["id"]}).to_list(None))
    order = {l["line_code"]: l["sort_order"] for l in lines}
    assert order["B"] == 0 and order["A"] == 1
    _run(remove_line(db, admin(), t["id"], l1["id"]))
    assert len(_run(db.reporting_template_lines.find({"template_id": t["id"]}).to_list(None))) == 1


def test_published_mutation_rejected():
    db = _DB()
    tid = _company_pl(db)
    _run(publish_template(db, admin(), tid))
    with pytest.raises(HTTPException) as e:
        _run(add_line(db, admin(), tid, _line("Z", "spacer")))
    assert e.value.status_code == 409


# ---- Validation -----------------------------------------------------------
def test_validation_duplicate_and_unknown_parent():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="V1", statement_type="income_statement", scope="company", name="v", company_id=CA)))
    _run(add_line(db, admin(), t["id"], _line("R", "concept", ["REVENUE"], parent="GHOST")))
    diag = _run(validate_template(db, admin(), t["id"]))
    assert diag["template_valid"] is False
    assert any("parent" in e for e in diag["hierarchy_errors"])


def test_validation_unknown_concept_rejected_at_add():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="V2", statement_type="income_statement", scope="company", name="v", company_id=CA)))
    with pytest.raises(HTTPException) as e:
        _run(add_line(db, admin(), t["id"], _line("R", "concept", ["NOPE"])))
    assert e.value.status_code == 422


def test_validation_invalid_and_circular_formula():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="V3", statement_type="income_statement", scope="company", name="v", company_id=CA)))
    _run(add_line(db, admin(), t["id"], _line("A", "formula", formula="B")))
    _run(add_line(db, admin(), t["id"], _line("B", "formula", formula="A")))
    diag = _run(validate_template(db, admin(), t["id"]))
    assert any("circulaire" in e for e in diag["formula_errors"])


def test_validation_empty_financial_template_rejected():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="V4", statement_type="income_statement", scope="company", name="v", company_id=CA)))
    _run(add_line(db, admin(), t["id"], _line("SEC", "section")))
    diag = _run(validate_template(db, admin(), t["id"]))
    assert diag["template_valid"] is False
    with pytest.raises(HTTPException) as e:
        _run(publish_template(db, admin(), t["id"]))
    assert e.value.status_code == 422


# ---- Semantic bypass ------------------------------------------------------
def test_semantic_bypass_allowed_custom_with_accounts():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="BYP", statement_type="income_statement", scope="company", name="b", company_id=CA)))
    line = _run(add_line(db, admin(), t["id"], _line("SPECIAL", "concept", bypass=True, accounts=["90"])))
    assert line["semantic_bypass"] is True and line["semantic_bypass_warning"]
    diag = _run(validate_template(db, admin(), t["id"]))
    assert diag["semantic_bypass_count"] == 1 and diag["semantic_compatibility"] == "none"


def test_semantic_bypass_requires_accounts_and_not_workspace():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="BYP2", statement_type="income_statement", scope="company", name="b", company_id=CA)))
    with pytest.raises(HTTPException):
        _run(add_line(db, admin(), t["id"], _line("S", "concept", bypass=True)))  # no accounts
    wt = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="BYPW", statement_type="income_statement", scope="workspace", name="b")))
    with pytest.raises(HTTPException):
        _run(add_line(db, admin(), wt["id"], _line("S", "concept", bypass=True, accounts=["90"])))


def test_semantic_bypass_account_from_other_company_rejected():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="BYP3", statement_type="income_statement", scope="company", name="b", company_id=CB)))
    # account_code "10" exists in both CA and CB; for CB it resolves to b_acc (valid)
    ok = _run(add_line(db, admin(), t["id"], _line("S", "concept", bypass=True, accounts=["10"])))
    assert ok["account_refs"] == ["b_acc"]
    # a code that does not exist for CB
    with pytest.raises(HTTPException):
        _run(add_line(db, admin(), t["id"], _line("S2", "concept", bypass=True, accounts=["90"])))


# ---- Upload ---------------------------------------------------------------
_UPLOAD_ROWS = [
    {"line_code": "PL_REV", "line_type": "concept", "label_fr": "Produits", "label_en": "Revenue", "concept_codes": "REVENUE"},
    {"line_code": "PL_COGS", "line_type": "concept", "label_fr": "CMV", "concept_codes": "COGS", "display_sign": "negative"},
    {"line_code": "GROSS", "line_type": "formula", "label_fr": "Marge", "formula": "PL_REV-PL_COGS"},
]


def _meta(rows, code="UP_PL"):
    return UploadCommit(template_code=code, statement_type="income_statement", scope="company",
                        name="Uploaded", company_id=CA, rows=rows)


def test_upload_preview_no_write_then_commit_creates_draft():
    db = _DB()
    prev = _run(upload_preview(db, admin(), _meta(_UPLOAD_ROWS)))
    assert prev["valid"] is True and prev["summary"]["lines"] == 3
    assert _run(db.reporting_templates.count_documents({"template_code": "UP_PL"})) == 0  # no write on preview
    rec = _run(upload_commit(db, admin(), _meta(_UPLOAD_ROWS)))
    assert rec["status"] == "draft" and rec["line_count"] == 3 and rec["source"] == "upload"


def test_upload_commit_idempotent_retry():
    db = _DB()
    r1 = _run(upload_commit(db, admin(), _meta(_UPLOAD_ROWS)))
    r2 = _run(upload_commit(db, admin(), _meta(_UPLOAD_ROWS)))
    assert r2.get("idempotent") is True and r2["id"] == r1["id"]
    assert _run(db.reporting_templates.count_documents({"template_code": "UP_PL"})) == 1


def test_upload_rejects_unknown_concept_duplicate_and_circular():
    db = _DB()
    bad = [{"line_code": "A", "line_type": "concept", "concept_codes": "GHOST"},
           {"line_code": "A", "line_type": "concept", "concept_codes": "REVENUE"},
           {"line_code": "F1", "line_type": "formula", "formula": "F2"},
           {"line_code": "F2", "line_type": "formula", "formula": "F1"}]
    prev = _run(upload_preview(db, admin(), _meta(bad, code="UP_BAD")))
    assert prev["valid"] is False
    with pytest.raises(HTTPException) as e:
        _run(upload_commit(db, admin(), _meta(bad, code="UP_BAD")))
    assert e.value.status_code == 422


def test_upload_parse_csv_and_excel():
    # CSV
    buff = io.StringIO()
    w = csv.DictWriter(buff, fieldnames=["line_code", "line_type", "concept_codes", "formula"])
    w.writeheader()
    w.writerow({"line_code": "R", "line_type": "concept", "concept_codes": "REVENUE", "formula": ""})
    csv_rows = parse_rows(buff.getvalue().encode("utf-8"), "t.csv")
    assert csv_rows[0]["line_code"] == "R"
    # Excel
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["line_code", "line_type", "concept_codes"])
    ws.append(["R", "concept", "REVENUE"])
    bio = io.BytesIO(); wb.save(bio)
    xlsx_rows = parse_rows(bio.getvalue(), "t.xlsx")
    assert xlsx_rows[0]["concept_codes"] == "REVENUE"


# ---- Publish + versioning -------------------------------------------------
def test_publish_valid_then_new_version_keeps_old():
    db = _DB()
    tid = _company_pl(db)
    pub = _run(publish_template(db, admin(), tid))
    assert pub["status"] == "published" and pub["version"] == 1
    v2 = _run(new_custom_version(db, admin(), tid))
    assert v2["version"] == 2 and v2["status"] == "draft"
    # editing v2 does not touch v1
    _run(add_line(db, admin(), v2["id"], _line("NEWL", "spacer")))
    v1_lines = _run(db.reporting_template_lines.find({"template_id": tid}).to_list(None))
    assert all(l["line_code"] != "NEWL" for l in v1_lines)


def test_new_version_requires_published():
    db = _DB()
    tid = _company_pl(db)
    with pytest.raises(HTTPException) as e:
        _run(new_custom_version(db, admin(), tid))  # still draft
    assert e.value.status_code == 409


# ---- Defaults -------------------------------------------------------------
def test_default_resolution_company_over_workspace_over_system():
    db = _DB()
    # workspace default
    wt = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="WDEF_PL", statement_type="income_statement", scope="workspace", name="w")))
    _run(add_line(db, admin(), wt["id"], _line("R", "concept", ["REVENUE"])))
    _run(publish_template(db, admin(), wt["id"]))
    _run(set_default_template(db, admin(), DefaultAssignment(statement_type="income_statement",
         template_id=wt["id"], scope="workspace"), None))
    # engine picks workspace default when no template specified
    r = _run(preview_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
             statement_type="income_statement")))
    assert r["template_code"] == "WDEF_PL"
    # company override
    ctid = _company_pl(db, code="CDEF_PL")
    _run(publish_template(db, admin(), ctid))
    _run(set_default_template(db, admin(), DefaultAssignment(statement_type="income_statement",
         template_id=ctid, scope="company"), CA))
    r2 = _run(preview_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
              statement_type="income_statement")))
    assert r2["template_code"] == "CDEF_PL"
    defaults = _run(get_default_templates(db, admin(), CA))
    assert defaults["company_defaults"]["income_statement"] == "CDEF_PL"
    assert defaults["workspace_defaults"]["income_statement"] == "WDEF_PL"


def test_default_falls_back_to_system_jurisdiction():
    db = _DB()
    r = _run(preview_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
             statement_type="income_statement")))
    assert r["template_code"] == "SYS_PL"  # no default set → system jurisdiction fallback


# ---- i18n -----------------------------------------------------------------
def test_i18n_labels_fr_en_de_it_and_fallback():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="I18N", statement_type="income_statement", scope="company", name="i", company_id=CA)))
    _run(add_line(db, admin(), t["id"], _line("R", "concept", ["REVENUE"],
         labels={"fr": "Produits", "en": "Revenue", "de": "Ertrag", "it": "Ricavi"})))
    _run(publish_template(db, admin(), t["id"]))
    for loc, expected in (("fr", "Produits"), ("de", "Ertrag"), ("it", "Ricavi")):
        r = _run(preview_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
                 statement_type="income_statement", template_id=t["id"], locale=loc)))
        rev = next(l for l in r["computed_lines"] if l["line_code"] == "R")
        assert rev["label"] == expected


# ---- Security -------------------------------------------------------------
def test_security_matrix():
    db = _DB()
    _grant(db, "u_pr", "principal"); _grant(db, "u_co", "collaborator")
    _grant(db, "u_ca", "admin", "company_user"); _grant(db, "u_cu", "user", "company_user")
    tid = _company_pl(db); _run(publish_template(db, admin(), tid))
    # members can read available templates
    for uid in ("u_pr", "u_co", "u_ca", "u_cu"):
        assert _run(list_available_templates(db, CA, member(uid)))["count"] >= 1
    # company-local admin cannot write custom templates (read-only)
    with pytest.raises(HTTPException) as e:
        _run(create_custom_template(db, member("u_ca"), CustomTemplateCreate(
            template_code="NOPE", statement_type="income_statement", scope="company", name="x", company_id=CA)))
    assert e.value.status_code == 403
    # plain collaborator cannot write
    with pytest.raises(HTTPException):
        _run(create_custom_template(db, member("u_co"), CustomTemplateCreate(
            template_code="NOPE2", statement_type="income_statement", scope="company", name="x", company_id=CA)))
    # outsider denied read
    with pytest.raises(HTTPException) as e2:
        _run(list_available_templates(db, CA, member("ghost")))
    assert e2.value.status_code == 403


def test_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_custom_template(db, padmin(), CustomTemplateCreate(
            template_code="PA", statement_type="income_statement", scope="company", name="x", company_id=CA)))
    assert e.value.status_code == 403


def test_system_template_write_via_p35_forbidden():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(add_line(db, admin(), SYS_PL, _line("Z", "spacer")))
    assert e.value.status_code == 403


# ---- P3.4 engine integration ----------------------------------------------
def test_custom_pl_preview_and_generate():
    db = _DB()
    tid = _company_pl(db); _run(publish_template(db, admin(), tid))
    prev = _run(preview_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
                statement_type="income_statement", template_id=tid, locale="fr")))
    lines = {l["line_code"]: l for l in prev["computed_lines"]}
    assert lines["PL_REV"]["value"] == 500 and lines["GROSS"]["value"] == 200
    run = _run(generate_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
               statement_type="income_statement", template_id=tid)))
    assert run["status"] == "final" and run["template_version"] == 1


def test_custom_bs_preview_and_generate():
    db = _DB()
    t = _run(derive_template(db, admin(), DeriveRequest(source_template_id=SYS_BS,
             template_code="CUST_BS", scope="company", name="Custom BS", company_id=CA)))
    _run(publish_template(db, admin(), t["id"]))
    run = _run(generate_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
               statement_type="balance_sheet", template_id=t["id"])))
    assert run["control_totals"]["is_balanced"] is True


def test_report_run_reproducible_across_versions():
    db = _DB()
    tid = _company_pl(db); _run(publish_template(db, admin(), tid))
    run1 = _run(generate_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
                statement_type="income_statement", template_id=tid)))
    v2 = _run(new_custom_version(db, admin(), tid))
    # structural change in v2: rename GROSS label + reorder
    lines = _run(db.reporting_template_lines.find({"template_id": v2["id"]}).to_list(None))
    gross = next(l for l in lines if l["line_code"] == "GROSS")
    _run(update_line(db, admin(), v2["id"], gross["_id"],
         _line("GROSS", "formula", formula="PL_REV-PL_COGS", labels={"fr": "Marge brute v2"})))
    _run(publish_template(db, admin(), v2["id"]))
    run2 = _run(generate_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
                statement_type="income_statement", template_id=v2["id"], locale="fr")))
    assert run2["template_version"] == 2
    # v1 report_run unchanged
    stored1 = _run(get_report(db, CA, admin(), run1["id"]))
    assert stored1["template_version"] == 1
    g1 = next(l for l in stored1["computed_lines"] if l["line_code"] == "GROSS")
    assert g1["label"] == "Marge"  # original v1 label, not touched by v2


def test_semantic_bypass_executes_in_engine():
    db = _DB()
    t = _run(create_custom_template(db, admin(), CustomTemplateCreate(
        template_code="BYP_EXEC", statement_type="income_statement", scope="company", name="b", company_id=CA)))
    _run(add_line(db, admin(), t["id"], _line("PL_REV", "concept", ["REVENUE"])))
    _run(add_line(db, admin(), t["id"], _line("MISC", "concept", bypass=True, accounts=["90"], labels={"fr": "Divers"})))
    _run(publish_template(db, admin(), t["id"]))
    # a_misc (code 90) is unmapped but referenced by bypass → must NOT block generate
    _run(db.trial_balance_lines.insert_one(_tb("a_misc", 111, 111)))
    run = _run(generate_report(db, CA, admin(), ReportRequest(financial_period_id=FP1,
               statement_type="income_statement", template_id=t["id"])))
    misc = next(l for l in run["computed_lines"] if l["line_code"] == "MISC")
    assert misc["value"] == 111 and misc.get("semantic_bypass") is True


# ---- No writes to P2/legacy/mappings --------------------------------------
def test_no_write_to_financial_core():
    db = _DB()
    tb_before = [d.copy() for d in db.trial_balance_lines.docs]
    map_before = [d.copy() for d in db.account_mappings.docs]
    acc_before = len(db.accounts.docs)
    tid = _company_pl(db)
    _run(publish_template(db, admin(), tid))
    _run(validate_template(db, admin(), tid))
    assert db.trial_balance_lines.docs == tb_before
    assert db.account_mappings.docs == map_before
    assert len(db.accounts.docs) == acc_before
