"""P3.1 — Reporting semantic layer tests (in-memory, zero Phase-2 side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.concepts import (
    ConceptCreate, ConceptUpdate, create_concept, update_concept, deprecate_concept,
    list_concepts, get_concept, ACTIVE, DEPRECATED,
)
from core.financial.i18n import LabelUpsert, set_label, resolve
from core.financial.mappings import (
    MappingCreate, create_mapping, confirm_mapping, reject_mapping, list_mappings, mapping_coverage,
    CONFIRMED, SUGGESTED, REJECTED,
)
from core.financial.reporting_templates import (
    TemplateCreate, TemplateLineCreate, JurisdictionProfileCreate,
    create_template, add_template_line, publish_template, new_template_version, get_template,
    list_system_templates, create_jurisdiction_profile, DRAFT, PUBLISHED,
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
    def __init__(self, docs=None, name=""):
        self.docs = [d.copy() for d in (docs or [])]; self.name = name
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))
    async def insert_one(self, doc):
        self.docs.append(doc.copy())
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query): d.update(update.get("$set", {})); return
    async def create_index(self, *a, **k): return None


WS = "ws_a"; CA = "cmp_a"; FP1 = "fp_1"; FP2 = "fp_2"


class _DB:
    def __init__(self):
        self.companies = _Collection([{"id": CA, "workspace_id": WS, "name": "A", "active": True, "status": "active"},
                                      {"id": "cmp_x", "workspace_id": "ws_x", "name": "X", "active": True, "status": "active"}])
        self.company_access = _Collection([])
        self.company_memberships = _Collection([])
        self.workspace_memberships = _Collection([])
        self.financial_periods = _Collection([
            {"_id": FP1, "workspace_id": WS, "company_id": CA, "sequence": 1, "status": "open"},
            {"_id": FP2, "workspace_id": WS, "company_id": CA, "sequence": 2, "status": "open"}])
        self.accounts = _Collection([
            {"_id": "acc10", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True},
            {"_id": "acc32", "workspace_id": WS, "company_id": CA, "account_code": "3200", "account_name": "Sales", "active": True},
            {"_id": "acc40", "workspace_id": WS, "company_id": CA, "account_code": "4000", "account_name": "Rent", "active": True}])
        self.financial_concepts = _Collection([])
        self.financial_i18n_labels = _Collection([])
        self.account_mappings = _Collection([])
        self.reporting_templates = _Collection([])
        self.reporting_template_lines = _Collection([])
        self.jurisdiction_profiles = _Collection([])


def padmin(ws=WS): return {"id": "pa", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)
def _grant(db, uid, mtype="workspace_staff", role="collaborator"):
    db.company_memberships.docs.append({"_id": f"m_{uid}", "workspace_id": WS, "company_id": CA, "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


def _seed_concept(db, code, ctype="asset", stype="balance_sheet", nb="debit", is_agg=False, status=ACTIVE, cid=None):
    cid = cid or f"fc_{code.lower()}"
    db.financial_concepts.docs.append({"_id": cid, "concept_code": code, "concept_type": ctype,
        "statement_type": stype, "natural_balance": nb, "parent_concept_id": None, "cash_flow_category": "none",
        "is_aggregate": is_agg, "level": 0, "sort_order": 0, "tags": [], "scope": "system", "version": 1,
        "status": status, "replaced_by_concept_id": None})
    return cid


# ---- Concepts -------------------------------------------------------------
def test_platform_admin_creates_concept():
    db = _DB()
    r = _run(create_concept(db, padmin(), ConceptCreate(concept_code="CASH_AND_CASH_EQUIVALENTS",
             concept_type="asset", statement_type="balance_sheet", natural_balance="debit")))
    assert r["status"] == ACTIVE and r["scope"] == "system" and r["concept_code"] == "CASH_AND_CASH_EQUIVALENTS"


def test_workspace_admin_cannot_create_concept():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_concept(db, admin(), ConceptCreate(concept_code="REVENUE", concept_type="income",
             statement_type="income_statement", natural_balance="credit")))
    assert e.value.status_code == 403


def test_duplicate_concept_code_rejected():
    db = _DB(); _seed_concept(db, "REVENUE", "income", "income_statement", "credit")
    with pytest.raises(HTTPException) as e:
        _run(create_concept(db, padmin(), ConceptCreate(concept_code="REVENUE", concept_type="income",
             statement_type="income_statement", natural_balance="credit")))
    assert e.value.status_code == 409


def test_child_concept_level():
    db = _DB()
    parent = _run(create_concept(db, padmin(), ConceptCreate(concept_code="EXPENSES", concept_type="expense",
             statement_type="income_statement", natural_balance="debit", is_aggregate=True)))
    child = _run(create_concept(db, padmin(), ConceptCreate(concept_code="PERSONNEL_EXPENSE", concept_type="expense",
             statement_type="income_statement", natural_balance="debit", parent_concept_id=parent["id"])))
    assert child["level"] == 1


def test_concept_cosmetic_update_bumps_version():
    db = _DB(); cid = _seed_concept(db, "INVENTORY")
    r = _run(update_concept(db, padmin(), cid, ConceptUpdate(sort_order=5, tags=["x"])))
    assert r["sort_order"] == 5 and r["version"] == 2


def test_concept_deprecate_and_replace():
    db = _DB(); old = _seed_concept(db, "OLD_CASH"); new = _seed_concept(db, "NEW_CASH")
    r = _run(deprecate_concept(db, padmin(), old, replaced_by_concept_id=new))
    assert r["status"] == DEPRECATED and r["replaced_by_concept_id"] == new


def test_list_excludes_deprecated_by_default():
    db = _DB(); _seed_concept(db, "A_ACTIVE"); _seed_concept(db, "B_DEAD", status=DEPRECATED)
    r = _run(list_concepts(db, member("u1")))
    codes = {c["concept_code"] for c in r["concepts"]}
    assert "A_ACTIVE" in codes and "B_DEAD" not in codes


# ---- i18n -----------------------------------------------------------------
def test_i18n_upsert_and_resolve_fallback():
    db = _DB(); cid = _seed_concept(db, "CASH")
    _run(set_label(db, padmin(), LabelUpsert(entity_type="concept", entity_id=cid, locale="fr", label="Trésorerie")))
    _run(set_label(db, padmin(), LabelUpsert(entity_type="concept", entity_id=cid, locale="en", label="Cash")))
    assert _run(resolve(db, "concept", cid, "fr")) == "Trésorerie"
    # requested de missing → default fr? here default_locale default en → en
    assert _run(resolve(db, "concept", cid, "de")) == "Cash"
    assert _run(resolve(db, "concept", cid, "de", default_locale="fr")) == "Trésorerie"


def test_i18n_non_platform_denied():
    db = _DB(); cid = _seed_concept(db, "CASH")
    with pytest.raises(HTTPException) as e:
        _run(set_label(db, admin(), LabelUpsert(entity_type="concept", entity_id=cid, locale="fr", label="X")))
    assert e.value.status_code == 403


# ---- Mappings -------------------------------------------------------------
def test_create_suggested_then_confirm():
    db = _DB(); cid = _seed_concept(db, "CASH")
    m = _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=cid,
             effective_from_period_id=FP1, status="suggested")))
    assert m["status"] == SUGGESTED
    c = _run(confirm_mapping(db, CA, admin(), m["id"]))
    assert c["status"] == CONFIRMED and c["confirmed_by"] == "admin"


def test_cardinality_second_confirmed_supersedes_first():
    db = _DB(); c1 = _seed_concept(db, "CASH"); c2 = _seed_concept(db, "CASH_ALT")
    first = _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=c1,
             effective_from_period_id=FP1, status="confirmed")))
    second = _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=c2,
             effective_from_period_id=FP2, status="confirmed")))
    assert second["supersedes_mapping_id"] == first["id"]
    stored_first = next(d for d in db.account_mappings.docs if d["_id"] == first["id"])
    assert stored_first["superseded"] is True and stored_first["effective_to_sequence"] == 2


def test_backdating_confirmed_rejected():
    db = _DB(); c1 = _seed_concept(db, "CASH"); c2 = _seed_concept(db, "CASH2")
    _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=c1,
         effective_from_period_id=FP2, status="confirmed")))
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=c2,
             effective_from_period_id=FP1, status="confirmed")))
    assert e.value.status_code == 409


def test_reject_mapping():
    db = _DB(); cid = _seed_concept(db, "CASH")
    m = _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=cid,
             effective_from_period_id=FP1, status="suggested")))
    r = _run(reject_mapping(db, CA, admin(), m["id"], notes="mauvais compte"))
    assert r["status"] == REJECTED


def test_aggregate_concept_not_mappable():
    db = _DB(); cid = _seed_concept(db, "ASSETS", is_agg=True)
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=cid,
             effective_from_period_id=FP1, status="confirmed")))
    assert e.value.status_code == 422


def test_account_outside_company_rejected():
    db = _DB(); cid = _seed_concept(db, "CASH")
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, admin(), MappingCreate(account_id="ghost", financial_concept_id=cid,
             effective_from_period_id=FP1, status="confirmed")))
    assert e.value.status_code == 422


def test_coverage_derives_unmapped():
    db = _DB(); c1 = _seed_concept(db, "CASH"); c2 = _seed_concept(db, "REVENUE", "income", "income_statement", "credit")
    _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc10", financial_concept_id=c1,
         effective_from_period_id=FP1, status="confirmed")))
    _run(create_mapping(db, CA, admin(), MappingCreate(account_id="acc32", financial_concept_id=c2,
         effective_from_period_id=FP1, status="suggested")))
    cov = _run(mapping_coverage(db, CA, admin()))
    assert cov["counts"] == {"mapped": 1, "suggested_only": 1, "unmapped": 1}
    assert cov["fully_mapped"] is False


def test_mapping_security_non_admin_denied_member_reads():
    db = _DB(); cid = _seed_concept(db, "CASH"); _grant(db, "u_read")
    with pytest.raises(HTTPException) as e:
        _run(create_mapping(db, CA, member("u_read"), MappingCreate(account_id="acc10", financial_concept_id=cid,
             effective_from_period_id=FP1, status="confirmed")))
    assert e.value.status_code == 403
    assert _run(list_mappings(db, CA, member("u_read")))["count"] == 0


def test_mapping_cross_workspace_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_mappings(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


# ---- Templates ------------------------------------------------------------
def test_system_template_build_publish_and_version():
    db = _DB(); cid = _seed_concept(db, "OPERATING_REVENUE", "income", "income_statement", "credit")
    t = _run(create_template(db, padmin(), TemplateCreate(template_code="CA_IS_SME", statement_type="income_statement",
             scope="system", jurisdiction="CA", name="Revenu CA")))
    assert t["status"] == DRAFT
    _run(add_template_line(db, padmin(), t["id"], TemplateLineCreate(line_code="REVENUE", line_type="concept",
         concept_refs=[cid], measure="ytd")))
    pub = _run(publish_template(db, padmin(), t["id"]))
    assert pub["status"] == PUBLISHED
    v2 = _run(new_template_version(db, padmin(), t["id"]))
    assert v2["version"] == 2 and v2["status"] == DRAFT and v2["based_on_template_id"] == t["id"]
    full = _run(get_template(db, member("u1"), v2["id"]))
    assert len(full["lines"]) == 1


def test_system_template_semantic_bypass_forbidden():
    db = _DB()
    t = _run(create_template(db, padmin(), TemplateCreate(template_code="CA_BS", statement_type="balance_sheet",
             scope="system", name="Bilan")))
    with pytest.raises(HTTPException) as e:
        _run(add_template_line(db, padmin(), t["id"], TemplateLineCreate(line_code="X", line_type="concept",
             account_refs=["acc10"], semantic_bypass=True)))
    assert e.value.status_code == 422


def test_publish_empty_template_rejected():
    db = _DB()
    t = _run(create_template(db, padmin(), TemplateCreate(template_code="EMPTY", statement_type="balance_sheet",
             scope="system", name="Vide")))
    with pytest.raises(HTTPException) as e:
        _run(publish_template(db, padmin(), t["id"]))
    assert e.value.status_code == 422


def test_custom_template_allows_semantic_bypass():
    db = _DB()
    t = _run(create_template(db, admin(), TemplateCreate(template_code="CUSTOM_PL", statement_type="income_statement",
             scope="company", name="P&L client"), company_id=CA))
    line = _run(add_template_line(db, admin(), t["id"], TemplateLineCreate(line_code="SPECIAL", line_type="concept",
         account_refs=["acc40"], semantic_bypass=True)))
    assert line["semantic_bypass"] is True and line["semantic_bypass_warning"]


def test_add_line_to_published_rejected():
    db = _DB(); cid = _seed_concept(db, "REVENUE", "income", "income_statement", "credit")
    t = _run(create_template(db, padmin(), TemplateCreate(template_code="T1", statement_type="income_statement",
             scope="system", name="T1")))
    _run(add_template_line(db, padmin(), t["id"], TemplateLineCreate(line_code="R", line_type="concept", concept_refs=[cid])))
    _run(publish_template(db, padmin(), t["id"]))
    with pytest.raises(HTTPException) as e:
        _run(add_template_line(db, padmin(), t["id"], TemplateLineCreate(line_code="R2", line_type="concept", concept_refs=[cid])))
    assert e.value.status_code == 409


def test_system_template_create_denied_for_non_platform():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_template(db, admin(), TemplateCreate(template_code="ZZ", statement_type="balance_sheet",
             scope="system", name="Z")))
    assert e.value.status_code == 403


def test_custom_template_create_denied_for_non_admin():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_template(db, member("nobody"), TemplateCreate(template_code="Z2", statement_type="balance_sheet",
             scope="company", name="Z2"), company_id=CA))
    assert e.value.status_code == 403


def test_list_system_templates_tenant_read():
    db = _DB()
    t = _run(create_template(db, padmin(), TemplateCreate(template_code="SYS1", statement_type="balance_sheet",
             scope="system", jurisdiction="CH", name="CH")))
    r = _run(list_system_templates(db, member("u1"), jurisdiction="CH"))
    assert r["count"] == 1


# ---- Jurisdiction profiles ------------------------------------------------
def test_jurisdiction_profile_create_and_read():
    db = _DB()
    p = _run(create_jurisdiction_profile(db, padmin(), JurisdictionProfileCreate(jurisdiction_code="CA",
             supported_frameworks=["CA_ASPE_SME"], default_locales=["fr", "en"])))
    assert p["jurisdiction_code"] == "CA"
    with pytest.raises(HTTPException) as e:
        _run(create_jurisdiction_profile(db, admin(), JurisdictionProfileCreate(jurisdiction_code="CH")))
    assert e.value.status_code == 403
