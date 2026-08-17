"""A4.4 — Document AI extraction (assistance only). STRAT-01 §10 + A4.4 governance
scoping (`memory/A4_4_GOVERNANCE_SCOPING.md`).

Cardinal rules enforced here:
  - AI is ASSISTANCE, never authority: this module NEVER posts, approves, pays,
    closes, decides tax, or bypasses P1.13. `extract_invoice` returns a data DTO only.
  - FAIL-CLOSED: no compliant/attested provider (or region/attestation mismatch) →
    extraction is UNAVAILABLE and NO document data is ever sent. Manual fallback stays
    fully functional.
  - BYO key + DPA is the reference provider path. The Emergent Universal LLM key is
    FORBIDDEN until attested in writing (policy carried by the jurisdiction module).
  - Provider attestation is VERSIONED and verified at gate time.
  - BYO secrets live in the environment ONLY — never in DB / logs / audit / frontend.
  - Human corrections are strictly EXCLUDED from any implicit training.
"""
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException

from ..compliance import jurisdiction

# Bump when the governance contract changes. A provider attestation MUST match the
# current policy version to be considered activable (versioned attestation).
AI_GOVERNANCE_POLICY_VERSION = "A4.4-2026-06"


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProviderAttestation:
    provider: str
    non_training: bool
    retention: str                     # 'zero' | 'minimal' | '<days>d'
    region: Optional[str]              # e.g. 'CH' | 'EU' | 'US' | None
    encryption_in_transit: bool
    encryption_at_rest: bool
    deletion_supported: bool
    subprocessors: List[str] = field(default_factory=list)
    dpa_ref: Optional[str] = None
    attested_by: Optional[str] = None
    attested_at: Optional[str] = None
    version: str = AI_GOVERNANCE_POLICY_VERSION

    def public(self):
        # Never contains secrets. Safe to persist / show in a "Pourquoi ?" drawer.
        return asdict(self)


class ProviderNotConfigured(Exception):
    pass


class DocumentAIProvider(ABC):
    name: str = "abstract"
    model: str = ""
    model_version: str = ""
    uses_emergent_universal_key: bool = False

    @abstractmethod
    def attestation(self) -> ProviderAttestation: ...

    def health(self) -> dict:
        return {"ok": True}

    @abstractmethod
    async def extract_invoice(self, *, storage_ref: str, company_id: str, workspace_id: str,
                              request_id: str, hints: dict) -> dict:
        """MUST return an ExtractionResult dict (see governance schema). MUST NEVER
        create/advance any accounting object."""
        ...


class ByoVisionProvider(DocumentAIProvider):
    """Reference BYO scaffold. The real vision call is intentionally NOT wired yet:
    per the approved gate, no real AI call may happen until a compliant provider is
    effectively configured AND attested. The API key is read from the ENVIRONMENT
    only (never DB/logs/audit/frontend)."""

    uses_emergent_universal_key = False

    def __init__(self, *, name, model, model_version, api_key_env, attestation: ProviderAttestation):
        self.name = name
        self.model = model
        self.model_version = model_version
        self._api_key_env = api_key_env      # NAME of the env var, not the value
        self._attestation = attestation

    def attestation(self) -> ProviderAttestation:
        return self._attestation

    def _api_key(self):
        return os.environ.get(self._api_key_env)  # value never persisted/returned

    def health(self) -> dict:
        return {"ok": bool(self._api_key())}

    async def extract_invoice(self, *, storage_ref, company_id, workspace_id, request_id, hints):
        # Guard: no key configured → not ready (fail-closed upstream).
        if not self._api_key():
            raise ProviderNotConfigured("Clé fournisseur BYO absente de l'environnement.")
        # Real vision extraction is wired in a follow-up tranche once the client's
        # attested BYO provider is provisioned. Until then, do NOT make a real call.
        raise ProviderNotConfigured(
            "Provider d'analyse documentaire non encore câblé (activation après attestation BYO).")


# Provider registry — EMPTY by default ⇒ extraction UNAVAILABLE ⇒ manual fallback.
# Providers are registered from server configuration/env, never from the frontend.
_PROVIDERS: dict = {}


def register_provider(p: DocumentAIProvider):
    _PROVIDERS[p.name] = p


def unregister_provider(name: str):
    _PROVIDERS.pop(name, None)


def _provider_is_compliant(p: DocumentAIProvider, policy: dict):
    att = p.attestation()
    if att.version != AI_GOVERNANCE_POLICY_VERSION:
        return False, "attestation_version_mismatch"
    if p.uses_emergent_universal_key and not policy.get("allow_emergent_universal_key"):
        return False, "emergent_universal_key_forbidden"
    if not att.non_training:
        return False, "no_non_training_guarantee"
    if not (att.encryption_in_transit and att.encryption_at_rest):
        return False, "encryption_insufficient"
    req = policy.get("region_required") or []
    if req and (att.region not in req):
        return False, "region_not_allowed"
    if not p.health().get("ok"):
        return False, "provider_unavailable"
    return True, None


async def extraction_gate(db, ws, co):
    """Fail-closed availability decision. Never transmits any document data; only
    decides whether a compliant, attested, region-appropriate provider exists."""
    policy = await jurisdiction.document_ai_policy(db, ws, co)
    reasons = []
    for p in _PROVIDERS.values():
        ok, why = _provider_is_compliant(p, policy)
        if ok:
            att = p.attestation()
            return {"available": True, "provider": p.name, "model": p.model,
                    "region": att.region, "policy_version": att.version,
                    "region_required": policy["region_required"]}
        reasons.append({"provider": p.name, "reason": why})
    return {"available": False, "reason": "no_compliant_provider",
            "message": "Analyse automatique des documents indisponible — saisie manuelle.",
            "region_required": policy["region_required"],
            "provider_diagnostics": reasons}


# --------------------------------------------------------------------------- #
# ap_extractions — persisted extraction results (approved schema). Confidence &
# provenance are stored per field but NEVER surfaced in the normal UX (only via
# a "Pourquoi ?" drawer). No accounting effect is ever derived automatically.
# --------------------------------------------------------------------------- #
def _field(value=None, *, confidence=None, source="ai", page=None, needs_review=False):
    return {"value": value, "confidence": confidence,
            "provenance": {"source": source, "page": page, "bbox": None, "raw_snippet_ref": None},
            "needs_review": needs_review}


def public_extraction(d):
    if not d:
        return None
    return {"id": d.get("_id"), "document_id": d.get("document_id"), "invoice_id": d.get("invoice_id"),
            "inbox_item_id": d.get("inbox_item_id"), "provider": d.get("provider"), "model": d.get("model"),
            "model_version": d.get("model_version"), "request_id": d.get("request_id"),
            "status": d.get("status"), "created_at": d.get("created_at"), "latency_ms": d.get("latency_ms"),
            "page_count": d.get("page_count"), "overall_confidence": d.get("overall_confidence"),
            "attestation_snapshot": d.get("attestation_snapshot"), "fields": d.get("fields") or {},
            "consistency": d.get("consistency") or {}, "needs_review_fields": d.get("needs_review_fields") or [],
            "corrections": d.get("corrections") or [], "excluded_from_training": d.get("excluded_from_training", True)}


async def _ai_audit(db, ws, co, *, user, provider, model, model_version, document_id, request_id,
                    status, latency_ms=None, page_count=None, overall_confidence=None,
                    attestation=None, reason=None):
    # Audit WITHOUT secrets / raw prompt. Immutable.
    await db.ap_ai_audit.insert_one({
        "_id": f"aiaud_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
        "provider": provider, "model": model, "model_version": model_version,
        "document_id": document_id, "request_id": request_id, "status": status,
        "latency_ms": latency_ms, "page_count": page_count, "overall_confidence": overall_confidence,
        "attestation_snapshot": attestation, "reason": reason,
        "by": (user or {}).get("id"), "by_email": (user or {}).get("email"), "at": _now()})


async def analyze_document(db, ws, co, user, *, document_id=None, invoice_id=None,
                           inbox_item_id=None, storage_ref=None, hints=None):
    """Fail-closed entry point. If no compliant provider is available, NO data is
    sent and the caller falls back to manual entry."""
    gate = await extraction_gate(db, ws, co)
    request_id = f"req_{uuid.uuid4().hex}"
    if not gate.get("available"):
        await _ai_audit(db, ws, co, user=user, provider=None, model=None, model_version=None,
                        document_id=document_id, request_id=request_id, status="unavailable",
                        reason=gate.get("reason"))
        return {"available": False, "message": gate.get("message"), "reason": gate.get("reason"),
                "region_required": gate.get("region_required")}
    provider = _PROVIDERS[gate["provider"]]
    att = provider.attestation()
    started = datetime.now(timezone.utc)
    try:
        result = await provider.extract_invoice(
            storage_ref=storage_ref, company_id=co, workspace_id=ws, request_id=request_id, hints=hints or {})
    except ProviderNotConfigured as e:
        await _ai_audit(db, ws, co, user=user, provider=provider.name, model=provider.model,
                        model_version=provider.model_version, document_id=document_id,
                        request_id=request_id, status="error", reason=str(e), attestation=att.public())
        return {"available": False, "message": "Analyse automatique des documents indisponible — saisie manuelle.",
                "reason": "provider_not_ready"}
    latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    doc = {"_id": f"apx_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
           "document_id": document_id, "invoice_id": invoice_id, "inbox_item_id": inbox_item_id,
           "provider": provider.name, "model": provider.model, "model_version": provider.model_version,
           "request_id": request_id, "status": result.get("status", "ok"), "created_at": _now(),
           "latency_ms": latency_ms, "page_count": result.get("page_count"),
           "overall_confidence": result.get("overall_confidence"),
           "attestation_snapshot": {"non_training": att.non_training, "retention": att.retention,
                                    "region": att.region, "version": att.version},
           "fields": result.get("fields") or {}, "consistency": result.get("consistency") or {},
           "needs_review_fields": result.get("needs_review_fields") or [],
           "corrections": [], "excluded_from_training": True}
    await db.ap_extractions.insert_one(doc)
    await _ai_audit(db, ws, co, user=user, provider=provider.name, model=provider.model,
                    model_version=provider.model_version, document_id=document_id, request_id=request_id,
                    status=doc["status"], latency_ms=latency_ms, page_count=doc["page_count"],
                    overall_confidence=doc["overall_confidence"], attestation=att.public())
    return {"available": True, "extraction": public_extraction(doc)}


async def get_extraction(db, ws, co, xid):
    d = await db.ap_extractions.find_one({"_id": xid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Extraction introuvable")
    return d


async def list_extractions(db, ws, co, *, invoice_id=None, inbox_item_id=None):
    q = {"workspace_id": ws, "company_id": co}
    if invoice_id:
        q["invoice_id"] = invoice_id
    if inbox_item_id:
        q["inbox_item_id"] = inbox_item_id
    docs = await db.ap_extractions.find(q).sort("created_at", -1).to_list(200)
    return [public_extraction(d) for d in docs]


async def apply_corrections(db, ws, co, user, xid, corrections):
    """Human corrections stay in the tenant's data + audit and are STRICTLY excluded
    from any implicit training (flag + no export path)."""
    d = await get_extraction(db, ws, co, xid)
    fields = d.get("fields") or {}
    log = d.get("corrections") or []
    for c in corrections or []:
        path = c.get("field_path")
        if not path or path not in fields:
            continue
        old = (fields.get(path) or {}).get("value")
        fields[path]["value"] = c.get("value")
        fields[path]["provenance"] = {"source": "human", "page": None, "bbox": None, "raw_snippet_ref": None}
        fields[path]["needs_review"] = False
        log.append({"field_path": path, "old_value": old, "new_value": c.get("value"),
                    "by_user_id": user.get("id"), "at": _now()})
    await db.ap_extractions.update_one({"_id": xid}, {"$set": {
        "fields": fields, "corrections": log, "excluded_from_training": True}})
    return public_extraction(await get_extraction(db, ws, co, xid))


async def ensure_a44_indexes(db):
    await db.ap_extractions.create_index([("workspace_id", 1), ("company_id", 1), ("invoice_id", 1)])
    await db.ap_extractions.create_index([("workspace_id", 1), ("company_id", 1), ("inbox_item_id", 1)])
    await db.ap_ai_audit.create_index([("workspace_id", 1), ("company_id", 1), ("document_id", 1)])
