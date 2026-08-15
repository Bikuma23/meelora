"""P3.5 — Custom reporting-template governance (P&L + Balance Sheet).

Custom client templates REUSE the exact P3.1/P3.4 data model
(``reporting_templates`` + ``reporting_template_lines``) and the P3.4 safe
formula grammar (imported, never re-implemented). There is NO second template
model and NO second calculation engine: published custom templates are executed
by the generic P3.4 engine.

Lifecycle: draft (editable) → published (immutable) → archived (historical read
only). Evolving a published template creates a NEW version; a published version
is never mutated. Scope is ``workspace`` (all companies of the workspace) or
``company`` (that company only). System templates stay platform-managed and are
read-only references that may be DERIVED from.

Semantic-first: a line maps to financial concept(s). ``semantic_bypass=true``
(custom only) lets a line reference accounts directly; it requires account_refs,
forbids concept-driving on the same line, stores an explicit warning and reduces
semantic compatibility. System templates never allow bypass.

This module performs ONLY structural/governance validation. It never computes
statement values, never writes Phase 2 / legacy collections and treats mappings
as read-only. The only new collection is ``reporting_template_defaults``.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import (require_company_access, require_company_admin,
                           require_workspace_admin, require_tenant_context)
from .concepts import ACTIVE as CONCEPT_ACTIVE
from .reporting_engine import _tokenize, _IDENT  # reuse P3.4 safe grammar (no eval)
from .mapping_import import parse_rows  # reuse CSV/XLSX row reader

DRAFT, PUBLISHED, ARCHIVED = "draft", "published", "archived"
LINE_TYPES = {"section", "concept", "subtotal", "formula", "spacer"}
VALUE_LINE_TYPES = {"concept", "subtotal", "formula"}
FORMULA_LINE_TYPES = {"subtotal", "formula"}
DISPLAY_SIGNS = {"natural", "positive", "negative", "inverted"}
MEASURES = {"period", "ytd"}
STATEMENTS = {"income_statement", "balance_sheet"}
LOCALES = ("fr", "en", "de", "it")
_BYPASS_WARNING = ("Contournement sémantique : cette ligne référence directement des comptes et "
                   "n'alimente pas les concepts (impacte KPI / Cash Flow / comparaisons futures).")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CustomTemplateCreate(BaseModel):
    template_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    statement_type: Literal["income_statement", "balance_sheet"]
    scope: Literal["workspace", "company"]
    name: str = Field(min_length=1, max_length=160)
    jurisdiction: Optional[str] = Field(default=None, max_length=8)
    company_id: Optional[str] = None


class DeriveRequest(BaseModel):
    source_template_id: str
    template_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    scope: Literal["workspace", "company"]
    name: str = Field(min_length=1, max_length=160)
    company_id: Optional[str] = None


class TemplateLineUpsert(BaseModel):
    line_code: str = Field(min_length=1, max_length=80)
    line_type: Literal["section", "concept", "subtotal", "formula", "spacer"]
    parent_line_code: Optional[str] = None
    concept_codes: list[str] = Field(default_factory=list)
    account_codes: list[str] = Field(default_factory=list)
    semantic_bypass: bool = False
    formula: Optional[str] = None
    display_sign: Literal["natural", "positive", "negative", "inverted"] = "natural"
    measure: Literal["period", "ytd"] = "ytd"
    sort_order: Optional[int] = None
    labels: dict = Field(default_factory=dict)


class ReorderRequest(BaseModel):
    ordered_line_codes: list[str]


class DefaultAssignment(BaseModel):
    statement_type: Literal["income_statement", "balance_sheet"]
    template_id: str
    scope: Literal["workspace", "company"] = "company"


class UploadCommit(BaseModel):
    template_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    statement_type: Literal["income_statement", "balance_sheet"]
    scope: Literal["workspace", "company"]
    name: str = Field(min_length=1, max_length=160)
    jurisdiction: Optional[str] = Field(default=None, max_length=8)
    company_id: Optional[str] = None
    rows: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).isoformat()


def _public(doc):
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


def _clean_labels(labels):
    return {k: str(v) for k, v in (labels or {}).items() if k in LOCALES and v not in (None, "")}


async def _authorize_scope_write(db, user, scope, company_id):
    """Return (workspace_id, company_id) after authorizing a custom-template write."""
    ws = require_tenant_context(user)
    if scope == "workspace":
        await require_workspace_admin(db, user)
        return ws, None
    if not company_id:
        raise HTTPException(status_code=422, detail="company_id requis pour un template de portée société")
    await require_company_admin(db, company_id, user)  # workspace admin only
    return ws, company_id


async def _load_writable(db, user, template_id):
    doc = await db.reporting_templates.find_one({"_id": template_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Template introuvable")
    scope = doc.get("scope")
    if scope == "system":
        raise HTTPException(status_code=403, detail="Les templates système sont gérés par la plateforme")
    ws = require_tenant_context(user)
    if doc.get("workspace_id") != ws:
        raise HTTPException(status_code=404, detail="Template introuvable")
    await _authorize_scope_write(db, user, scope, doc.get("company_id"))
    return doc


async def _load_readable(db, user, template_id):
    doc = await db.reporting_templates.find_one({"_id": template_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Template introuvable")
    if doc.get("scope") == "system":
        require_tenant_context(user)
        return doc
    ws = require_tenant_context(user)
    if doc.get("workspace_id") != ws:
        raise HTTPException(status_code=404, detail="Template introuvable")
    if doc.get("scope") == "company":
        await require_company_access(db, doc.get("company_id"), user)
    else:  # workspace scope → any workspace member may read
        from ..permissions import require_workspace_membership
        await require_workspace_membership(db, user)
    return doc


def _require_draft(tpl):
    if tpl.get("status") != DRAFT:
        raise HTTPException(status_code=409, detail="Seuls les brouillons sont modifiables")


async def _ensure_code_free(db, ws, template_code):
    existing = await db.reporting_templates.find({"template_code": template_code}).to_list(None)
    for e in existing:
        # System codes are global; custom codes must be free within the workspace.
        if e.get("scope") == "system" or e.get("workspace_id") == ws:
            raise HTTPException(status_code=409, detail=f"template_code déjà utilisé: {template_code}")


async def _resolve_concepts(db, concept_codes):
    """Return (concept_ref_ids, errors). Codes must be active concepts."""
    ids, errors = [], []
    for code in concept_codes:
        c = await db.financial_concepts.find_one({"concept_code": code})
        if not c:
            errors.append(f"concept inconnu: {code}")
        elif c.get("status") != CONCEPT_ACTIVE:
            errors.append(f"concept inactif: {code}")
        else:
            ids.append(c["_id"])
    return ids, errors


async def _resolve_accounts(db, ws, company_id, account_codes):
    """Return (account_ref_ids, errors). Accounts must belong to the company."""
    ids, errors = [], []
    if not company_id:
        return ids, ["semantic_bypass avec comptes exige un template de portée société"]
    for code in account_codes:
        a = await db.accounts.find_one({"workspace_id": ws, "company_id": company_id, "account_code": code})
        if not a:
            errors.append(f"compte inconnu pour cette société: {code}")
        elif a.get("active") is False:
            errors.append(f"compte inactif: {code}")
        else:
            ids.append(a["_id"])
    return ids, errors


def _next_sort_order(lines):
    return (max((l.get("sort_order") or 0) for l in lines) + 1) if lines else 0


# ---------------------------------------------------------------------------
# Line materialization (rich, P3.4-engine ready)
# ---------------------------------------------------------------------------
def _line_doc(template_id, line_code, line_type, *, parent_line_code, concept_refs, concept_codes,
              account_refs, semantic_bypass, formula, display_sign, measure, sort_order, labels, now):
    return {
        "_id": f"rtl_{uuid.uuid4().hex}", "template_id": template_id,
        "line_code": line_code, "line_type": line_type,
        "parent_line_id": None, "parent_line_code": parent_line_code,
        "concept_refs": list(concept_refs), "concept_codes": list(concept_codes),
        "account_refs": list(account_refs), "semantic_bypass": bool(semantic_bypass),
        "semantic_bypass_warning": _BYPASS_WARNING if semantic_bypass else None,
        "formula": formula, "display_sign": display_sign, "measure": measure,
        "labels": _clean_labels(labels), "sort_order": sort_order, "created_at": now,
    }


def _validate_line_shape(tpl, payload, concept_refs, account_refs, concept_errors, account_errors):
    """Per-line write-time shape validation (cross-line checks happen at publish)."""
    errs = list(concept_errors) + list(account_errors)
    if payload.line_type in FORMULA_LINE_TYPES and not (payload.formula and payload.formula.strip()):
        errs.append("line_type=subtotal/formula exige une formule")
    if payload.semantic_bypass:
        if payload.concept_codes:
            errs.append("semantic_bypass et concept_codes sont mutuellement exclusifs sur une ligne")
        if not payload.account_codes:
            errs.append("semantic_bypass exige account_codes")
        if tpl.get("scope") != "company":
            errs.append("semantic_bypass avec comptes exige un template de portée société")
    else:
        if payload.account_codes:
            errs.append("account_codes exige semantic_bypass=true")
        if payload.line_type == "concept" and not payload.concept_codes:
            errs.append("line_type=concept exige concept_codes (ou semantic_bypass)")
    if errs:
        raise HTTPException(status_code=422, detail={"line_code": payload.line_code, "errors": errs})


# ---------------------------------------------------------------------------
# Create / derive
# ---------------------------------------------------------------------------
async def create_custom_template(db, user, payload: CustomTemplateCreate) -> dict:
    ws, cid = await _authorize_scope_write(db, user, payload.scope, payload.company_id)
    await _ensure_code_free(db, ws, payload.template_code)
    now = _now()
    doc = {
        "_id": f"rt_{uuid.uuid4().hex}", "template_code": payload.template_code,
        "statement_type": payload.statement_type, "scope": payload.scope,
        "jurisdiction": payload.jurisdiction, "workspace_id": ws, "company_id": cid,
        "name": payload.name, "based_on_template_id": None, "based_on_template_version": None,
        "version": 1, "status": DRAFT, "source": "manual",
        "created_by": user.get("id"), "created_at": now, "published_at": None,
    }
    await db.reporting_templates.insert_one(doc)
    return _public(doc)


async def _copy_lines(db, source_template_id, new_template_id, now):
    src = await db.reporting_template_lines.find({"template_id": source_template_id}).to_list(None)
    src.sort(key=lambda d: (d.get("sort_order") or 0, d.get("line_code") or ""))
    for i, l in enumerate(src):
        doc = _line_doc(
            new_template_id, l["line_code"], l["line_type"],
            parent_line_code=l.get("parent_line_code"),
            concept_refs=l.get("concept_refs") or [], concept_codes=l.get("concept_codes") or [],
            account_refs=l.get("account_refs") or [], semantic_bypass=bool(l.get("semantic_bypass")),
            formula=l.get("formula"), display_sign=l.get("display_sign", "natural"),
            measure=l.get("measure", "ytd"), sort_order=i, labels=l.get("labels") or {}, now=now)
        await db.reporting_template_lines.insert_one(doc)


async def derive_template(db, user, payload: DeriveRequest) -> dict:
    ws, cid = await _authorize_scope_write(db, user, payload.scope, payload.company_id)
    source = await _load_readable(db, user, payload.source_template_id)
    await _ensure_code_free(db, ws, payload.template_code)
    now = _now()
    new_id = f"rt_{uuid.uuid4().hex}"
    doc = {
        "_id": new_id, "template_code": payload.template_code,
        "statement_type": source["statement_type"], "scope": payload.scope,
        "jurisdiction": source.get("jurisdiction"), "workspace_id": ws, "company_id": cid,
        "name": payload.name, "based_on_template_id": source["_id"],
        "based_on_template_version": source.get("version"), "version": 1, "status": DRAFT,
        "source": "derived", "created_by": user.get("id"), "created_at": now, "published_at": None,
    }
    await db.reporting_templates.insert_one(doc)
    await _copy_lines(db, source["_id"], new_id, now)
    return _public(doc)


async def new_custom_version(db, user, template_id: str) -> dict:
    tpl = await _load_writable(db, user, template_id)
    if tpl.get("status") != PUBLISHED:
        raise HTTPException(status_code=409, detail="Seul un template publié peut être versionné")
    now = _now()
    new_id = f"rt_{uuid.uuid4().hex}"
    clone = {**{k: v for k, v in tpl.items() if k != "_id"}, "_id": new_id,
             "version": (tpl.get("version") or 1) + 1, "status": DRAFT,
             "based_on_template_id": template_id, "based_on_template_version": tpl.get("version"),
             "source": "version", "created_by": user.get("id"), "created_at": now, "published_at": None}
    await db.reporting_templates.insert_one(clone)
    await _copy_lines(db, template_id, new_id, now)
    return _public(clone)


# ---------------------------------------------------------------------------
# Line editing (draft only)
# ---------------------------------------------------------------------------
async def add_line(db, user, template_id: str, payload: TemplateLineUpsert) -> dict:
    tpl = await _load_writable(db, user, template_id)
    _require_draft(tpl)
    ws = tpl.get("workspace_id")
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    if any(l.get("line_code") == payload.line_code for l in lines):
        raise HTTPException(status_code=409, detail=f"line_code déjà présent: {payload.line_code}")
    concept_refs, cerr = await _resolve_concepts(db, payload.concept_codes)
    account_refs, aerr = (await _resolve_accounts(db, ws, tpl.get("company_id"), payload.account_codes)
                          if payload.semantic_bypass or payload.account_codes else ([], []))
    _validate_line_shape(tpl, payload, concept_refs, account_refs, cerr, aerr)
    now = _now()
    order = payload.sort_order if payload.sort_order is not None else _next_sort_order(lines)
    doc = _line_doc(template_id, payload.line_code, payload.line_type,
                    parent_line_code=payload.parent_line_code, concept_refs=concept_refs,
                    concept_codes=list(payload.concept_codes), account_refs=account_refs,
                    semantic_bypass=payload.semantic_bypass, formula=payload.formula,
                    display_sign=payload.display_sign, measure=payload.measure,
                    sort_order=order, labels=payload.labels, now=now)
    await db.reporting_template_lines.insert_one(doc)
    return _public(doc)


async def update_line(db, user, template_id: str, line_id: str, payload: TemplateLineUpsert) -> dict:
    tpl = await _load_writable(db, user, template_id)
    _require_draft(tpl)
    ws = tpl.get("workspace_id")
    line = await db.reporting_template_lines.find_one({"_id": line_id, "template_id": template_id})
    if not line:
        raise HTTPException(status_code=404, detail="Ligne introuvable")
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    if any(l.get("line_code") == payload.line_code and l.get("_id") != line_id for l in lines):
        raise HTTPException(status_code=409, detail=f"line_code déjà présent: {payload.line_code}")
    concept_refs, cerr = await _resolve_concepts(db, payload.concept_codes)
    account_refs, aerr = (await _resolve_accounts(db, ws, tpl.get("company_id"), payload.account_codes)
                          if payload.semantic_bypass or payload.account_codes else ([], []))
    _validate_line_shape(tpl, payload, concept_refs, account_refs, cerr, aerr)
    order = payload.sort_order if payload.sort_order is not None else line.get("sort_order", 0)
    upd = {
        "line_code": payload.line_code, "line_type": payload.line_type,
        "parent_line_code": payload.parent_line_code, "concept_refs": concept_refs,
        "concept_codes": list(payload.concept_codes), "account_refs": account_refs,
        "semantic_bypass": payload.semantic_bypass,
        "semantic_bypass_warning": _BYPASS_WARNING if payload.semantic_bypass else None,
        "formula": payload.formula, "display_sign": payload.display_sign, "measure": payload.measure,
        "sort_order": order, "labels": _clean_labels(payload.labels),
    }
    await db.reporting_template_lines.update_one({"_id": line_id}, {"$set": upd})
    line.update(upd)
    return _public(line)


async def remove_line(db, user, template_id: str, line_id: str) -> dict:
    tpl = await _load_writable(db, user, template_id)
    _require_draft(tpl)
    line = await db.reporting_template_lines.find_one({"_id": line_id, "template_id": template_id})
    if not line:
        raise HTTPException(status_code=404, detail="Ligne introuvable")
    await db.reporting_template_lines.delete_one({"_id": line_id})
    return {"deleted": True, "line_id": line_id}


async def reorder_lines(db, user, template_id: str, payload: ReorderRequest) -> dict:
    tpl = await _load_writable(db, user, template_id)
    _require_draft(tpl)
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    by_code = {l["line_code"]: l for l in lines}
    if set(payload.ordered_line_codes) != set(by_code.keys()):
        raise HTTPException(status_code=422, detail="La réorganisation doit lister exactement toutes les lignes")
    for i, code in enumerate(payload.ordered_line_codes):
        await db.reporting_template_lines.update_one({"_id": by_code[code]["_id"]},
                                                     {"$set": {"sort_order": i}})
    return {"reordered": len(payload.ordered_line_codes)}


# ---------------------------------------------------------------------------
# Validation (structural only — never computes statement values)
# ---------------------------------------------------------------------------
async def _collect_validation(db, tpl, lines) -> dict:
    formula_errors, hierarchy_errors, concept_errors, bypass_errors, general = [], [], [], [], []
    codes = [l.get("line_code") for l in lines]
    code_set = set(codes)
    if len(codes) != len(code_set):
        seen, dups = set(), set()
        for c in codes:
            (dups if c in seen else seen).add(c)
        hierarchy_errors.append(f"line_code dupliqué(s): {sorted(dups)}")
    if tpl.get("statement_type") not in STATEMENTS:
        general.append(f"statement_type invalide: {tpl.get('statement_type')}")

    scope = tpl.get("scope")
    company_id = tpl.get("company_id")
    bypass_count = 0
    has_value_line = False

    for l in lines:
        lc = l.get("line_code")
        lt = l.get("line_type")
        if not lc:
            hierarchy_errors.append("line_code manquant")
            continue
        if lt not in LINE_TYPES:
            hierarchy_errors.append(f"line_type invalide ({lc}): {lt}")
        if l.get("display_sign", "natural") not in DISPLAY_SIGNS:
            general.append(f"display_sign invalide ({lc})")
        if l.get("measure", "ytd") not in MEASURES:
            general.append(f"measure invalide ({lc})")
        parent = l.get("parent_line_code")
        if parent and parent not in code_set:
            hierarchy_errors.append(f"parent inconnu ({lc}): {parent}")
        if parent == lc:
            hierarchy_errors.append(f"ligne parent d'elle-même: {lc}")
        if lt in VALUE_LINE_TYPES:
            has_value_line = True
        if lt == "concept":
            if l.get("semantic_bypass"):
                bypass_count += 1
                if scope == "system":
                    bypass_errors.append(f"semantic_bypass interdit en portée système ({lc})")
                if scope != "company":
                    bypass_errors.append(f"semantic_bypass exige la portée société ({lc})")
                if l.get("concept_refs"):
                    bypass_errors.append(f"semantic_bypass et concepts exclusifs ({lc})")
                if not l.get("account_refs"):
                    bypass_errors.append(f"semantic_bypass exige des comptes ({lc})")
                for aid in (l.get("account_refs") or []):
                    a = await db.accounts.find_one({"_id": aid})
                    if not a:
                        bypass_errors.append(f"compte inconnu ({lc}): {aid}")
                    elif company_id and a.get("company_id") != company_id:
                        bypass_errors.append(f"compte d'une autre société ({lc}): {aid}")
            else:
                if not l.get("concept_refs"):
                    concept_errors.append(f"line_type=concept sans concept ({lc})")
                for cid_ in (l.get("concept_refs") or []):
                    c = await db.financial_concepts.find_one({"_id": cid_})
                    if not c or c.get("status") != CONCEPT_ACTIVE:
                        concept_errors.append(f"concept invalide/inactif ({lc}): {cid_}")
                    elif c.get("statement_type") not in (None, tpl.get("statement_type")):
                        concept_errors.append(
                            f"concept d'un autre état ({lc}): {c.get('concept_code')}")
        if lt in FORMULA_LINE_TYPES:
            f = l.get("formula")
            if not (f and f.strip()):
                formula_errors.append(f"formule manquante ({lc})")
            else:
                try:
                    _tokenize(f)
                except HTTPException:
                    formula_errors.append(f"formule malformée ({lc}): {f}")
                for tok in set(_IDENT.findall(f)):
                    if tok not in code_set:
                        formula_errors.append(f"référence de formule inconnue ({lc}): {tok}")
                    elif tok == lc:
                        formula_errors.append(f"auto-référence de formule ({lc})")

    # Circular formula detection (topological resolution over line refs).
    if not formula_errors:
        resolved = {l["line_code"] for l in lines if l.get("line_type") not in FORMULA_LINE_TYPES}
        pending = [l for l in lines if l.get("line_type") in FORMULA_LINE_TYPES]
        progressed = True
        while pending and progressed:
            progressed = False
            still = []
            for l in pending:
                refs = set(_IDENT.findall(l.get("formula") or ""))
                if refs <= resolved:
                    resolved.add(l["line_code"])
                    progressed = True
                else:
                    still.append(l)
            pending = still
        if pending:
            formula_errors.append(
                f"dépendance circulaire de formule: {sorted(p['line_code'] for p in pending)}")

    if not lines:
        general.append("le template ne contient aucune ligne")
    elif not has_value_line:
        general.append("le template ne contient aucune ligne financière significative")

    errors = formula_errors + hierarchy_errors + concept_errors + bypass_errors + general
    valid = not errors
    concept_lines = [l for l in lines if l.get("line_type") == "concept" and not l.get("semantic_bypass")]
    referenced_concepts = sorted({c for l in concept_lines for c in (l.get("concept_codes") or [])})
    semantic_compatibility = "full" if bypass_count == 0 else ("reduced" if concept_lines else "none")
    return {
        "template_id": tpl.get("_id"), "template_code": tpl.get("template_code"),
        "version": tpl.get("version"), "status": tpl.get("status"),
        "statement_type": tpl.get("statement_type"), "scope": scope,
        "template_valid": valid,
        "template_publishable": valid and tpl.get("status") == DRAFT,
        "concept_coverage": {"concept_lines": len(concept_lines),
                             "distinct_concepts": len(referenced_concepts),
                             "referenced_concepts": referenced_concepts},
        "semantic_bypass_count": bypass_count,
        "semantic_compatibility": semantic_compatibility,
        "formula_errors": formula_errors, "hierarchy_errors": hierarchy_errors,
        "concept_errors": concept_errors, "bypass_errors": bypass_errors,
        "general_errors": general, "errors": errors,
        "line_count": len(lines),
    }


async def validate_template(db, user, template_id: str) -> dict:
    tpl = await _load_readable(db, user, template_id)
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    lines.sort(key=lambda d: (d.get("sort_order") or 0, d.get("line_code") or ""))
    return await _collect_validation(db, tpl, lines)


async def publish_template(db, user, template_id: str) -> dict:
    tpl = await _load_writable(db, user, template_id)
    _require_draft(tpl)
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    diag = await _collect_validation(db, tpl, lines)
    if not diag["template_valid"]:
        raise HTTPException(status_code=422, detail={
            "message": "Publication bloquée : le template n'est pas valide", "diagnostics": diag})
    now = _now()
    await db.reporting_templates.update_one({"_id": template_id},
                                            {"$set": {"status": PUBLISHED, "published_at": now}})
    tpl.update({"status": PUBLISHED, "published_at": now})
    return _public(tpl)


async def archive_template(db, user, template_id: str) -> dict:
    tpl = await _load_writable(db, user, template_id)
    if tpl.get("status") == ARCHIVED:
        return _public(tpl)
    await db.reporting_templates.update_one({"_id": template_id}, {"$set": {"status": ARCHIVED}})
    tpl["status"] = ARCHIVED
    return _public(tpl)


# ---------------------------------------------------------------------------
# Listing (system + workspace + company, tenant-safe)
# ---------------------------------------------------------------------------
async def list_available_templates(db, company_id, user, statement_type=None) -> dict:
    company = await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    is_admin = user.get("role") == "admin"
    system = await db.reporting_templates.find({"scope": "system"}).to_list(None)
    custom = await db.reporting_templates.find({"workspace_id": ws}).to_list(None)
    out = []
    for d in system:
        if statement_type and d.get("statement_type") != statement_type:
            continue
        out.append(d)
    for d in custom:
        if d.get("scope") not in ("workspace", "company"):
            continue
        if d.get("scope") == "company" and d.get("company_id") != company_id:
            continue
        if statement_type and d.get("statement_type") != statement_type:
            continue
        if not is_admin and d.get("status") != PUBLISHED:
            continue  # non-admins only see published custom templates
        out.append(d)
    out.sort(key=lambda d: (d.get("scope") or "", d.get("template_code") or "", d.get("version") or 0))
    return {"company_id": company_id, "count": len(out), "templates": [_public(d) for d in out]}


# ---------------------------------------------------------------------------
# Default-template assignment (presentation only; NEVER touches data source)
# ---------------------------------------------------------------------------
async def set_default_template(db, user, payload: DefaultAssignment, company_id: Optional[str]) -> dict:
    scope = payload.scope
    ws, cid = await _authorize_scope_write(db, user, scope, company_id)
    tpl = await db.reporting_templates.find_one({"_id": payload.template_id})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template introuvable")
    if tpl.get("scope") != "system" and tpl.get("workspace_id") != ws:
        raise HTTPException(status_code=404, detail="Template introuvable")
    if tpl.get("status") != PUBLISHED:
        raise HTTPException(status_code=422, detail="Seul un template publié peut devenir template par défaut")
    if tpl.get("statement_type") != payload.statement_type:
        raise HTTPException(status_code=422, detail="Le template ne correspond pas au type d'état")
    if tpl.get("scope") == "company" and tpl.get("company_id") != cid:
        raise HTTPException(status_code=422, detail="Template d'une autre société")
    key = {"workspace_id": ws, "company_id": cid, "statement_type": payload.statement_type}
    now = _now()
    existing = await db.reporting_template_defaults.find_one(key)
    body = {**key, "template_id": tpl["_id"], "template_code": tpl.get("template_code"),
            "scope": scope, "set_by": user.get("id"), "updated_at": now}
    if existing:
        await db.reporting_template_defaults.update_one({"_id": existing["_id"]}, {"$set": body})
        body["_id"] = existing["_id"]
    else:
        body["_id"] = f"rtd_{uuid.uuid4().hex}"
        await db.reporting_template_defaults.insert_one(body)
    return _public(dict(body))


async def get_default_templates(db, user, company_id) -> dict:
    company = await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    out = {"company_id": company_id, "workspace_defaults": {}, "company_defaults": {}, "effective": {}}
    for st in STATEMENTS:
        wd = await db.reporting_template_defaults.find_one(
            {"workspace_id": ws, "company_id": None, "statement_type": st})
        cd = await db.reporting_template_defaults.find_one(
            {"workspace_id": ws, "company_id": company_id, "statement_type": st})
        if wd:
            out["workspace_defaults"][st] = wd.get("template_code")
        if cd:
            out["company_defaults"][st] = cd.get("template_code")
        eff = await resolve_default_template(db, ws, company_id, st)
        out["effective"][st] = (eff.get("template_code"), eff.get("version")) if eff else None
    return out


async def resolve_default_template(db, ws, company_id, statement_type):
    """company default > workspace default > None (engine then falls back to jurisdiction)."""
    defaults_col = getattr(db, "reporting_template_defaults", None)
    if defaults_col is None:
        return None
    for q in ({"workspace_id": ws, "company_id": company_id, "statement_type": statement_type},
              {"workspace_id": ws, "company_id": None, "statement_type": statement_type}):
        d = await defaults_col.find_one(q)
        if not d:
            continue
        tid = d.get("template_id")
        t = await db.reporting_templates.find_one({"_id": tid}) if tid else None
        if t and t.get("status") == PUBLISHED:
            return t
        code = d.get("template_code")
        if code:
            cands = await db.reporting_templates.find(
                {"template_code": code, "status": PUBLISHED}).to_list(None)
            if cands:
                return max(cands, key=lambda x: x.get("version") or 0)
    return None


# ---------------------------------------------------------------------------
# Excel/CSV upload (preview → validate → commit as DRAFT, no auto-publish)
# ---------------------------------------------------------------------------
_TRUE = {"true", "1", "yes", "oui", "y", "vrai"}


def _split(v):
    if not v:
        return []
    return [s.strip() for s in str(v).replace(";", ",").replace("|", ",").split(",") if s.strip()]


def _row_labels(raw):
    return {loc: raw.get(f"label_{loc}") for loc in LOCALES if raw.get(f"label_{loc}")}


async def _validate_upload_rows(db, ws, scope, company_id, statement_type, rows):
    """Return (parsed_lines, errors). No writes. parsed_lines carry resolved ids."""
    errors, parsed = [], []
    seen_codes = set()
    code_set = {(r.get("line_code") or "").strip() for r in rows if (r.get("line_code") or "").strip()}
    for idx, raw in enumerate(rows):
        line_errors = []
        lc = (raw.get("line_code") or "").strip()
        lt = (raw.get("line_type") or "").strip()
        if not lc:
            line_errors.append("line_code manquant")
        elif lc in seen_codes:
            line_errors.append(f"line_code dupliqué: {lc}")
        seen_codes.add(lc)
        if lt not in LINE_TYPES:
            line_errors.append(f"line_type invalide: {lt}")
        parent = (raw.get("parent_line_code") or "").strip() or None
        if parent and parent not in code_set:
            line_errors.append(f"parent inconnu: {parent}")
        display_sign = (raw.get("display_sign") or "natural").strip() or "natural"
        if display_sign not in DISPLAY_SIGNS:
            line_errors.append(f"display_sign invalide: {display_sign}")
        measure = (raw.get("measure") or "ytd").strip() or "ytd"
        if measure not in MEASURES:
            line_errors.append(f"measure invalide: {measure}")
        bypass = str(raw.get("semantic_bypass") or "").strip().lower() in _TRUE
        concept_codes = _split(raw.get("concept_codes"))
        account_codes = _split(raw.get("account_codes"))
        formula = (raw.get("formula") or "").strip() or None
        concept_refs, account_refs = [], []

        if lt in FORMULA_LINE_TYPES and not formula:
            line_errors.append("subtotal/formula exige une formule")
        if formula:
            try:
                _tokenize(formula)
            except HTTPException:
                line_errors.append(f"formule malformée: {formula}")
            for tok in set(_IDENT.findall(formula)):
                if tok not in code_set:
                    line_errors.append(f"référence de formule inconnue: {tok}")
                elif tok == lc:
                    line_errors.append(f"auto-référence de formule: {lc}")
        if bypass:
            if scope == "system":
                line_errors.append("semantic_bypass interdit en portée système")
            if scope != "company":
                line_errors.append("semantic_bypass exige la portée société")
            if concept_codes:
                line_errors.append("semantic_bypass et concept_codes exclusifs")
            if not account_codes:
                line_errors.append("semantic_bypass exige account_codes")
            account_refs, aerr = await _resolve_accounts(db, ws, company_id, account_codes)
            line_errors += aerr
        else:
            if account_codes:
                line_errors.append("account_codes exige semantic_bypass=true")
            if lt == "concept" and not concept_codes:
                line_errors.append("line_type=concept exige concept_codes")
            concept_refs, cerr = await _resolve_concepts(db, concept_codes)
            line_errors += cerr
            for cid_ in concept_refs:
                c = await db.financial_concepts.find_one({"_id": cid_})
                if c and c.get("statement_type") not in (None, statement_type):
                    line_errors.append(f"concept d'un autre état: {c.get('concept_code')}")

        if line_errors:
            errors.append({"index": idx, "line_code": lc, "errors": line_errors})
        else:
            parsed.append({
                "line_code": lc, "line_type": lt, "parent_line_code": parent,
                "concept_refs": concept_refs, "concept_codes": concept_codes,
                "account_refs": account_refs, "semantic_bypass": bypass, "formula": formula,
                "display_sign": display_sign, "measure": measure, "labels": _row_labels(raw)})

    if not any(p["line_type"] in VALUE_LINE_TYPES for p in parsed) and not errors:
        errors.append({"index": -1, "line_code": None,
                       "errors": ["le template ne contient aucune ligne financière significative"]})
    return parsed, errors


async def upload_preview(db, user, meta: UploadCommit) -> dict:
    ws, cid = await _authorize_scope_write(db, user, meta.scope, meta.company_id)
    parsed, errors = await _validate_upload_rows(
        db, ws, meta.scope, cid, meta.statement_type, meta.rows or [])
    bypass = sum(1 for p in parsed if p.get("semantic_bypass"))
    return {
        "template_code": meta.template_code, "statement_type": meta.statement_type, "scope": meta.scope,
        "valid": not errors, "summary": {"lines": len(parsed), "errors": len(errors),
                                         "semantic_bypass_count": bypass},
        "semantic_compatibility": "full" if bypass == 0 else "reduced",
        "parsed_lines": parsed, "errors": errors,
    }


async def upload_commit(db, user, meta: UploadCommit) -> dict:
    ws, cid = await _authorize_scope_write(db, user, meta.scope, meta.company_id)
    # Idempotent against retry: a draft with this code in this workspace is returned as-is.
    existing = await db.reporting_templates.find({"template_code": meta.template_code}).to_list(None)
    for e in existing:
        if e.get("scope") == "system" or (e.get("workspace_id") == ws and e.get("status") != DRAFT):
            raise HTTPException(status_code=409, detail=f"template_code déjà utilisé: {meta.template_code}")
        if e.get("workspace_id") == ws and e.get("status") == DRAFT and e.get("source") == "upload":
            full = _public(e)
            full["idempotent"] = True
            return full
    parsed, errors = await _validate_upload_rows(
        db, ws, meta.scope, cid, meta.statement_type, meta.rows or [])
    if errors:
        raise HTTPException(status_code=422, detail={
            "message": "Import bloqué : lignes invalides", "errors": errors})
    now = _now()
    tpl_id = f"rt_{uuid.uuid4().hex}"
    await db.reporting_templates.insert_one({
        "_id": tpl_id, "template_code": meta.template_code, "statement_type": meta.statement_type,
        "scope": meta.scope, "jurisdiction": meta.jurisdiction, "workspace_id": ws, "company_id": cid,
        "name": meta.name, "based_on_template_id": None, "based_on_template_version": None,
        "version": 1, "status": DRAFT, "source": "upload",
        "created_by": user.get("id"), "created_at": now, "published_at": None})
    for i, p in enumerate(parsed):
        doc = _line_doc(tpl_id, p["line_code"], p["line_type"], parent_line_code=p["parent_line_code"],
                        concept_refs=p["concept_refs"], concept_codes=p["concept_codes"],
                        account_refs=p["account_refs"], semantic_bypass=p["semantic_bypass"],
                        formula=p["formula"], display_sign=p["display_sign"], measure=p["measure"],
                        sort_order=i, labels=p["labels"], now=now)
        await db.reporting_template_lines.insert_one(doc)
    tpl = await db.reporting_templates.find_one({"_id": tpl_id})
    result = _public(tpl)
    result["line_count"] = len(parsed)
    return result


async def ensure_indexes(db) -> None:
    await db.reporting_template_defaults.create_index(
        [("workspace_id", 1), ("company_id", 1), ("statement_type", 1)],
        unique=True, name="uniq_reporting_default")
