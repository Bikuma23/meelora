"""Financial Core — reusable, versioned, multi-jurisdiction TAX ENGINE (A3).

Designed once so AR (A3) and later AP reuse it without touching the engine.

Rules (per user mandate):
  * Rates are NEVER hardcoded in invoices/UI — they live in ``sales_tax_codes``.
  * A tax code carries: jurisdiction, tax_kind (taxable / zero_rated / exempt) and
    a list of VERSIONS keyed by effective_date; each version holds components
    (name, tax_type, rate, payable_account_code). The engine picks the version
    whose effective_date is the latest <= the document date.
  * The engine determines taxes from the JURISDICTION + configuration in effect —
    not simply from the client's address.
  * A document snapshots the applied calculation (codes, rates, bases, amounts) so
    a future rate change never rewrites history.
  * Extensible: add provinces / cantons / countries via ``default_tax_codes`` with
    NO change to the calculation core.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

TAX_KINDS = ("taxable", "zero_rated", "exempt")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(v) -> float:
    return round(float(v or 0), 2)


def public_tax_code(d: dict) -> dict:
    return {"id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
            "code": d.get("code"), "label": d.get("label"), "jurisdiction": d.get("jurisdiction"),
            "tax_kind": d.get("tax_kind"), "versions": d.get("versions", []), "status": d.get("status", "active")}


# --------------------------------------------------------------------------- #
# Jurisdiction default catalogues (extensible; rates versioned by effective date)
# --------------------------------------------------------------------------- #
def _v(effective_date, components):
    return {"effective_date": effective_date, "components": components}


def _c(name, tax_type, rate, account_code):
    return {"name": name, "tax_type": tax_type, "rate": float(rate), "payable_account_code": account_code}


def default_tax_codes(jurisdiction: str) -> list[dict]:
    """Return the seed tax codes for a jurisdiction. Account codes are logical
    placeholders resolved via the company chart during posting; admins can remap."""
    j = (jurisdiction or "").upper()
    common_exempt = [
        {"code": "ZERO", "label": "Détaxé (0%)", "tax_kind": "zero_rated", "versions": [_v("2000-01-01", [])]},
        {"code": "EXEMPT", "label": "Exonéré", "tax_kind": "exempt", "versions": [_v("2000-01-01", [])]},
    ]
    if j in ("CA-QC", "QC", "CA_QC"):
        return [
            {"code": "GST_QST", "label": "TPS 5% + TVQ 9,975%", "tax_kind": "taxable", "versions": [
                _v("2013-01-01", [_c("TPS", "GST", 0.05, "TAX_GST_PAYABLE"),
                                  _c("TVQ", "QST", 0.09975, "TAX_QST_PAYABLE")])]},
            {"code": "GST", "label": "TPS 5%", "tax_kind": "taxable", "versions": [
                _v("2008-01-01", [_c("TPS", "GST", 0.05, "TAX_GST_PAYABLE")])]},
            *common_exempt,
        ]
    if j in ("CA-ON", "ON", "CA_ON"):
        return [
            {"code": "HST", "label": "TVH 13%", "tax_kind": "taxable", "versions": [
                _v("2010-07-01", [_c("TVH", "HST", 0.13, "TAX_HST_PAYABLE")])]},
            *common_exempt,
        ]
    if j in ("CA-BC", "BC", "CA_BC"):
        return [
            {"code": "GST_PST", "label": "TPS 5% + PST 7%", "tax_kind": "taxable", "versions": [
                _v("2013-04-01", [_c("TPS", "GST", 0.05, "TAX_GST_PAYABLE"),
                                  _c("PST", "PST", 0.07, "TAX_PST_PAYABLE")])]},
            *common_exempt,
        ]
    if j in ("CH", "CHE"):
        return [
            {"code": "VAT_STD", "label": "TVA taux normal", "tax_kind": "taxable", "versions": [
                _v("2018-01-01", [_c("TVA", "VAT", 0.077, "TAX_VAT_PAYABLE")]),
                _v("2024-01-01", [_c("TVA", "VAT", 0.081, "TAX_VAT_PAYABLE")])]},
            {"code": "VAT_REDUCED", "label": "TVA taux réduit", "tax_kind": "taxable", "versions": [
                _v("2018-01-01", [_c("TVA", "VAT", 0.025, "TAX_VAT_PAYABLE")]),
                _v("2024-01-01", [_c("TVA", "VAT", 0.026, "TAX_VAT_PAYABLE")])]},
            *common_exempt,
        ]
    # Unknown jurisdiction: only neutral codes; admins add taxable codes explicitly.
    return [
        {"code": "STANDARD", "label": "Taxe standard (à configurer)", "tax_kind": "taxable",
         "versions": [_v("2000-01-01", [_c("TAX", "VAT", 0.0, "TAX_VAT_PAYABLE")])]},
        *common_exempt,
    ]


async def ensure_default_tax_codes(db, workspace_id, company_id, jurisdiction):
    """Idempotent seeding of the jurisdiction defaults (never overwrites existing)."""
    existing = {d["code"] for d in await db.sales_tax_codes.find(
        {"workspace_id": workspace_id, "company_id": company_id}).to_list(None)}
    created = []
    for tc in default_tax_codes(jurisdiction):
        if tc["code"] in existing:
            continue
        doc = {"_id": f"tax_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
               "code": tc["code"], "label": tc["label"], "jurisdiction": (jurisdiction or "").upper(),
               "tax_kind": tc["tax_kind"], "versions": tc["versions"], "status": "active", "created_at": _now()}
        await db.sales_tax_codes.insert_one(doc)
        created.append(doc["code"])
    return created


async def list_tax_codes(db, workspace_id, company_id):
    docs = await db.sales_tax_codes.find({"workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    docs.sort(key=lambda d: d.get("code") or "")
    return [public_tax_code(d) for d in docs]


async def get_tax_code(db, workspace_id, company_id, code):
    d = await db.sales_tax_codes.find_one(
        {"workspace_id": workspace_id, "company_id": company_id, "code": code})
    if not d:
        raise HTTPException(status_code=422, detail=f"Code de taxe inconnu : {code}")
    return d


async def create_tax_code(db, workspace_id, company_id, payload):
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=422, detail="Code de taxe requis")
    kind = payload.get("tax_kind") or "taxable"
    if kind not in TAX_KINDS:
        raise HTTPException(status_code=422, detail="tax_kind invalide")
    if await db.sales_tax_codes.find_one({"workspace_id": workspace_id, "company_id": company_id, "code": code}):
        raise HTTPException(status_code=409, detail="Code de taxe déjà existant")
    doc = {"_id": f"tax_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "code": code, "label": payload.get("label") or code, "jurisdiction": (payload.get("jurisdiction") or "").upper(),
           "tax_kind": kind, "versions": payload.get("versions") or [_v("2000-01-01", [])],
           "status": "active", "created_at": _now()}
    await db.sales_tax_codes.insert_one(doc)
    return public_tax_code(doc)


def _pick_version(tax_code_doc, on_date):
    versions = sorted(tax_code_doc.get("versions", []), key=lambda v: v.get("effective_date") or "")
    chosen = None
    for v in versions:
        if (v.get("effective_date") or "0000") <= (on_date or _now()[:10]):
            chosen = v
    return chosen or (versions[0] if versions else {"effective_date": None, "components": []})


def compute_line_tax(tax_code_doc, base, on_date):
    """Return the tax snapshot for one taxable base at ``on_date``.
    zero_rated/exempt yield zero tax but keep the kind for reporting."""
    kind = tax_code_doc.get("tax_kind", "taxable")
    base = _money(base)
    if kind in ("zero_rated", "exempt"):
        return {"tax_code": tax_code_doc.get("code"), "tax_kind": kind, "effective_date": None,
                "components": [], "tax_total": 0.0}
    version = _pick_version(tax_code_doc, on_date)
    comps = []
    total = 0.0
    for c in version.get("components", []):
        amt = _money(base * float(c.get("rate") or 0))
        total += amt
        comps.append({"name": c.get("name"), "tax_type": c.get("tax_type"), "rate": float(c.get("rate") or 0),
                      "payable_account_code": c.get("payable_account_code"), "amount": amt})
    return {"tax_code": tax_code_doc.get("code"), "tax_kind": kind,
            "effective_date": version.get("effective_date"), "components": comps, "tax_total": _money(total)}
