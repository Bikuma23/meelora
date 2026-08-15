"""P3.1 — Localization (i18n) for SYSTEM reporting referential.

Dedicated i18n table for concepts / templates / template lines (approved
design decision). Internal codes (concept_code, template_code, line_code)
stay language-neutral; only human labels are localized here. Custom-scoped
templates may embed labels directly (tolerated), so this system table is for
system-managed entities. Writes require a platform manager; reads require an
authenticated tenant user. Deterministic fallback on resolve.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import require_platform_manager, require_tenant_context

EntityType = Literal["concept", "template", "template_line"]
FALLBACK_LOCALE = "en"


class LabelUpsert(BaseModel):
    entity_type: EntityType
    entity_id: str
    locale: str = Field(min_length=2, max_length=5)
    label: str = Field(min_length=1, max_length=240)


def _now():
    return datetime.now(timezone.utc).isoformat()


async def set_label(db, user, payload: LabelUpsert) -> dict:
    require_platform_manager(user)
    key = {"entity_type": payload.entity_type, "entity_id": payload.entity_id,
           "locale": payload.locale.lower(), "scope": "system"}
    now = _now()
    existing = await db.financial_i18n_labels.find_one(key)
    if existing:
        await db.financial_i18n_labels.update_one(
            {"_id": existing["_id"]}, {"$set": {"label": payload.label, "updated_at": now}})
        return {"id": existing["_id"], **key, "label": payload.label,
                "created_at": existing.get("created_at"), "updated_at": now}
    new_id = f"i18n_{uuid.uuid4().hex}"
    await db.financial_i18n_labels.insert_one(
        {"_id": new_id, **key, "label": payload.label, "created_at": now, "updated_at": now})
    return {"id": new_id, **key, "label": payload.label, "created_at": now, "updated_at": now}


async def get_labels(db, user, entity_type: str, entity_id: str) -> dict:
    require_tenant_context(user)
    docs = await db.financial_i18n_labels.find({
        "entity_type": entity_type, "entity_id": entity_id, "scope": "system"}).to_list(None)
    return {"entity_type": entity_type, "entity_id": entity_id,
            "labels": {d["locale"]: d["label"] for d in docs}}


async def resolve(db, entity_type: str, entity_id: str, locale: str,
                  default_locale: str = FALLBACK_LOCALE) -> Optional[str]:
    """Deterministic label resolution: requested → default → FALLBACK → None."""
    docs = await db.financial_i18n_labels.find({
        "entity_type": entity_type, "entity_id": entity_id, "scope": "system"}).to_list(None)
    by_locale = {d["locale"]: d["label"] for d in docs}
    for loc in (locale.lower(), (default_locale or "").lower(), FALLBACK_LOCALE):
        if loc and loc in by_locale:
            return by_locale[loc]
    return None


async def ensure_indexes(db) -> None:
    await db.financial_i18n_labels.create_index(
        [("entity_type", 1), ("entity_id", 1), ("locale", 1), ("scope", 1)],
        unique=True, name="uniq_i18n_entity_locale")
