"""Jurisdiction / compliance profile (seed of the Jurisdiction Engine — STRAT-01 §11).

Country/jurisdiction policy is carried HERE, never hardcoded inside AP (or any
business module). AP asks this module e.g. "which regions are allowed for document
AI processing?" and enforces the answer fail-closed. This keeps `if country == CH`
out of the business modules and prepares real Country Packs.
"""
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


# Default jurisdiction profiles. A per-company override may be stored in
# `company_compliance_profiles`. `document_ai_regions` = allowed processing regions
# for document AI (empty = no regional restriction).
DEFAULT_PROFILES = {
    "CH": {"label": "Suisse", "document_ai_regions": ["CH", "EU"]},
    "CA": {"label": "Canada", "document_ai_regions": []},
    "FR": {"label": "France", "document_ai_regions": ["EU"]},
    "DE": {"label": "Allemagne", "document_ai_regions": ["EU"]},
    "IT": {"label": "Italie", "document_ai_regions": ["EU"]},
}


async def get_compliance_profile(db, ws, co):
    prof = await db.company_compliance_profiles.find_one({"workspace_id": ws, "company_id": co})
    if prof:
        return prof
    company = await db.companies.find_one({"_id": co}) or {}
    country = (company.get("country") or company.get("jurisdiction") or "").upper()
    base = DEFAULT_PROFILES.get(country, {"label": country or "—", "document_ai_regions": []})
    return {"company_id": co, "country": country or None, **base, "source": "default"}


async def set_compliance_profile(db, ws, co, *, country=None, document_ai_regions=None):
    upd = {"workspace_id": ws, "company_id": co, "updated_at": _now()}
    if country is not None:
        upd["country"] = country.upper()
    if document_ai_regions is not None:
        upd["document_ai_regions"] = [r.upper() for r in document_ai_regions]
    await db.company_compliance_profiles.update_one(
        {"workspace_id": ws, "company_id": co}, {"$set": upd}, upsert=True)
    return await get_compliance_profile(db, ws, co)


async def document_ai_policy(db, ws, co):
    """Policy consumed by the AP extraction gate (fail-closed enforcement lives in AP).

    - `region_required`: allowed processing regions (empty = unrestricted).
    - `allow_emergent_universal_key`: FALSE by policy — the Emergent Universal LLM
      key is forbidden for document AI until its governance (non-training, retention,
      subprocessors, residency, security) is attested in writing. BYO key + DPA is the
      reference path.
    """
    prof = await get_compliance_profile(db, ws, co)
    return {
        "country": prof.get("country"),
        "region_required": prof.get("document_ai_regions") or [],
        "allow_emergent_universal_key": False,
    }
