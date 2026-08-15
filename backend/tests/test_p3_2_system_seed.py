"""P3.2 — System seed tests (in-memory): idempotency, integrity, i18n, security."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.system_seed import (
    run_system_seed, run_system_seed_as, CONCEPTS, TEMPLATES, BS_SPEC, PL_SPEC,
    _validate_template_spec, _fc_id, SEED_VERSION,
)
from core.financial.i18n import resolve
from core.financial.concepts import list_concepts
from core.financial.reporting_templates import list_system_templates, get_template


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
    def __init__(self): self.docs = []
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))
    async def insert_one(self, doc): self.docs.append(doc.copy())
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query): d.update(update.get("$set", {})); return
    async def create_index(self, *a, **k): return None


class _DB:
    def __init__(self):
        for n in ("financial_concepts", "financial_i18n_labels", "jurisdiction_profiles",
                  "reporting_templates", "reporting_template_lines", "account_mappings"):
            setattr(self, n, _Collection())


def padmin(): return {"id": "pa", "role": "user", "platform_role": "platform_admin", "workspace_id": "ws", "tenant_migrated": True}
def admin(): return {"id": "a", "role": "admin", "workspace_id": "ws", "tenant_migrated": True}
def member(): return {"id": "m", "role": "user", "workspace_id": "ws", "tenant_migrated": True}
def _run(c): return asyncio.run(c)


# ---- Idempotency ----------------------------------------------------------
def test_seed_creates_then_idempotent():
    db = _DB()
    r1 = _run(run_system_seed(db))
    c1 = r1["counts"]
    assert c1["concepts"] == len(CONCEPTS)
    assert c1["templates"] == 4
    assert c1["jurisdiction_profiles"] == 2
    assert len(r1["errors"]) == 0
    r2 = _run(run_system_seed(db))
    assert r2["counts"] == c1  # stable
    assert r2["totals"]["created"] == 0  # nothing new on rerun
    assert len(r2["errors"]) == 0


# ---- Concept integrity ----------------------------------------------------
def test_concept_codes_unique():
    codes = [c[0] for c in CONCEPTS]
    assert len(codes) == len(set(codes))


def test_concept_parents_exist():
    codes = {c[0] for c in CONCEPTS}
    for (code, parent, *_r) in CONCEPTS:
        assert parent is None or parent in codes


def test_aggregates_and_contra_present():
    by_code = {c[0]: c for c in CONCEPTS}
    for agg in ("ASSETS", "CURRENT_ASSETS", "NON_CURRENT_ASSETS", "LIABILITIES",
                "CURRENT_LIABILITIES", "NON_CURRENT_LIABILITIES", "EQUITY", "INCOME", "EXPENSES"):
        assert by_code[agg][5] is True  # is_aggregate
    assert by_code["ACCUMULATED_DEPRECIATION"][2] == "contra_asset"
    assert by_code["ACCUMULATED_AMORTIZATION"][2] == "contra_asset"


def test_required_structural_concepts_present():
    codes = {c[0] for c in CONCEPTS}
    for req in ("RELATED_PARTY_RECEIVABLES", "RELATED_PARTY_PAYABLES", "RIGHT_OF_USE_ASSETS",
                "LEASE_LIABILITIES_CURRENT", "LEASE_LIABILITIES_NON_CURRENT", "PROVISIONS",
                "FOREIGN_EXCHANGE_GAIN", "FOREIGN_EXCHANGE_LOSS", "NON_RECURRING_ITEMS",
                "LEGAL_RESERVES", "DEFERRED_TAX_ASSET", "DEFERRED_TAX_LIABILITY"):
        assert req in codes, f"concept manquant: {req}"


def test_kpi_supporting_concepts_present():
    codes = {c[0] for c in CONCEPTS}
    # current ratio / working capital / debt ratio / margins need these
    for c in ("CURRENT_ASSETS", "CURRENT_LIABILITIES", "OPERATING_REVENUE",
              "COST_OF_GOODS_SOLD", "LONG_TERM_DEBT", "SHORT_TERM_DEBT", "INVENTORY"):
        assert c in codes


def test_seed_blocks_semantic_drift():
    db = _DB()
    _run(run_system_seed(db))
    # mutate a published concept's semantic field, reseed → error, no overwrite
    for d in db.financial_concepts.docs:
        if d["concept_code"] == "INVENTORY":
            d["concept_type"] = "expense"
    r = _run(run_system_seed(db))
    assert any(e.get("concept") == "INVENTORY" for e in r["errors"])
    inv = next(d for d in db.financial_concepts.docs if d["concept_code"] == "INVENTORY")
    assert inv["concept_type"] == "expense"  # NOT silently overwritten back


# ---- i18n -----------------------------------------------------------------
def test_i18n_en_fr_coverage_and_fallback():
    db = _DB(); _run(run_system_seed(db))
    cid = _fc_id("CASH_AND_CASH_EQUIVALENTS")
    assert _run(resolve(db, "concept", cid, "fr")) == "Trésorerie et équivalents"
    assert _run(resolve(db, "concept", cid, "en")) == "Cash and cash equivalents"
    # de/it seeded for all concepts too
    assert _run(resolve(db, "concept", cid, "de")) == "Flüssige Mittel"
    assert _run(resolve(db, "concept", cid, "it")) == "Liquidità"
    # fallback: unknown locale → default en
    assert _run(resolve(db, "concept", cid, "es")) == "Cash and cash equivalents"


# ---- Templates ------------------------------------------------------------
def test_four_system_templates_published_versioned():
    db = _DB(); _run(run_system_seed(db))
    r = _run(list_system_templates(db, member()))
    assert r["count"] == 4
    for t in r["templates"]:
        assert t["scope"] == "system" and t["status"] == "published" and t["version"] == 1


def test_template_lines_no_semantic_bypass_valid_refs():
    db = _DB(); _run(run_system_seed(db))
    concept_ids = {d["_id"] for d in db.financial_concepts.docs}
    for tpl in db.reporting_templates.docs:
        full = _run(get_template(db, member(), tpl["_id"]))
        line_codes = [l["line_code"] for l in full["lines"]]
        assert len(line_codes) == len(set(line_codes))  # unique per template
        for l in full["lines"]:
            assert l["semantic_bypass"] is False and l["account_refs"] == []
            for cid in l["concept_refs"]:
                assert cid in concept_ids  # all concept refs valid
            if l["parent_line_code"]:
                assert l["parent_line_code"] in line_codes


def test_template_spec_validation_catches_bad_formula():
    bad = [dict(BS_SPEC[0]), {"line_code": "X", "line_type": "formula", "concepts": [],
           "formula": "NON_EXISTENT+1", "display_sign": "natural", "parent": None, "labels": {}}]
    with pytest.raises(ValueError):
        _validate_template_spec(bad)


def test_ca_and_ch_templates_share_concepts():
    ca_bs = next(t for t in TEMPLATES if t["template_code"] == "CA_PRIVATE_ENTERPRISE_STANDARD_BS")
    ch_bs = next(t for t in TEMPLATES if t["template_code"] == "CH_CO_SME_STANDARD_BS")
    assert ca_bs["spec"] is ch_bs["spec"]  # same canonical structure, different locales


def test_bs_and_pl_specs_validate():
    _validate_template_spec(BS_SPEC)
    _validate_template_spec(PL_SPEC)


# ---- Jurisdiction ---------------------------------------------------------
def test_jurisdiction_profiles_and_default_templates_valid():
    db = _DB(); _run(run_system_seed(db))
    tpl_codes = {t["template_code"] for t in db.reporting_templates.docs}
    for jp in db.jurisdiction_profiles.docs:
        for st, code in jp["default_template_codes"].items():
            assert code in tpl_codes, f"template par défaut manquant: {code}"
    ca = next(d for d in db.jurisdiction_profiles.docs if d["jurisdiction_code"] == "CA")
    ch = next(d for d in db.jurisdiction_profiles.docs if d["jurisdiction_code"] == "CH")
    assert "de" in ch["default_locales"] and "it" in ch["default_locales"]
    assert ca["supported_frameworks"] == ["CA_PRIVATE_ENTERPRISE"]


# ---- Security & no client side-effects ------------------------------------
def test_seed_requires_platform_manager():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(run_system_seed_as(db, admin()))
    assert e.value.status_code == 403


def test_platform_manager_can_seed():
    db = _DB()
    r = _run(run_system_seed_as(db, padmin()))
    assert r["counts"]["concepts"] == len(CONCEPTS)


def test_seed_creates_no_client_data():
    db = _DB(); _run(run_system_seed(db))
    assert db.account_mappings.docs == []
    # every template is system scope, none workspace/company
    assert all(t["scope"] == "system" for t in db.reporting_templates.docs)


def test_tenant_can_read_reference():
    db = _DB(); _run(run_system_seed(db))
    r = _run(list_concepts(db, member()))
    assert r["count"] == len([c for c in CONCEPTS])  # all active
