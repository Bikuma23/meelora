"""CH.3B.1 — Fiscal Activation Gate (per-company state machine).

Makes CH.1+CH.2+CH.3 the real VAT authority for NEW A3/A4 transactions, one
company at a time. This module owns ONLY the state machine + guards + audit; it
performs NO tax resolution and NO posting.

States (per company): legacy → shadow → ready → active (+ guarded rollback).
Invariants:
  * A company reaches `active` only when: profile complete, no policy conflict,
    shadow run executed, differences classified, NO blocking anomaly.
  * Rollback active→(shadow|legacy) is allowed ONLY while no vat_ch transaction
    has been created under the activation. After that, no silent return to legacy.
  * Company A active never affects company B. No global switch.
  * `accounting.fiscal_engine_activate` gates every mutation (no admin bypass).
State is stored on the existing `company_fiscal_activation` doc; the legacy
boolean `fiscal_engine_active` is DERIVED (state == "active") for CH.3 compat.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from . import company_tax_profile as tax_profile

STATES = ("legacy", "shadow", "ready", "active")
ENGINE_VERSION = "vat_ch@1"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _doc(db, ws, co):
    d = await db.company_fiscal_activation.find_one({"workspace_id": ws, "company_id": co})
    if not d:
        return {"workspace_id": ws, "company_id": co, "state": "legacy"}
    # Backward compat: derive a state from the old boolean if state is absent.
    if not d.get("state"):
        d["state"] = "active" if d.get("fiscal_engine_active") else "legacy"
    return d


async def _profile_complete(db, ws, co):
    prof = await tax_profile.get_active_profile(db, ws, co)
    return bool(prof and prof.get("completeness") == "complete")


async def blocking_count(db, ws, co):
    """Number of unresolved BLOCKING shadow differences (0 until CH.3B.2 populates
    `fiscal_shadow_observations`)."""
    return await db.fiscal_shadow_observations.count_documents(
        {"workspace_id": ws, "company_id": co, "classification": "blocking_difference", "resolved": {"$ne": True}})


async def shadow_run_done(db, ws, co):
    return (await db.fiscal_shadow_observations.count_documents(
        {"workspace_id": ws, "company_id": co})) > 0


async def has_vat_ch_transactions(db, ws, co):
    """True once any A3/A4 transaction was resolved by vat_ch (marker set when
    A3/A4 are rewired in CH.3B.3). Prevents silent rollback."""
    q = {"workspace_id": ws, "company_id": co, "fiscal_engine": "vat_ch"}
    if await db.sales_invoices.count_documents(q):
        return True
    if await db.ap_invoices.count_documents(q):
        return True
    return False


async def get_status(db, ws, co):
    d = await _doc(db, ws, co)
    state = d["state"]
    complete = await _profile_complete(db, ws, co)
    blocking = await blocking_count(db, ws, co)
    shadow_done = await shadow_run_done(db, ws, co)
    locked = await has_vat_ch_transactions(db, ws, co)

    reasons = []
    if not complete:
        reasons.append("Profil fiscal incomplet.")
    if blocking:
        reasons.append(f"{blocking} différence(s) bloquante(s) à résoudre.")
    if state in ("legacy", "shadow", "ready") and not shadow_done:
        reasons.append("Comparaison en shadow non exécutée.")
    can_activate = complete and blocking == 0 and shadow_done and state in ("shadow", "ready", "active")

    return {
        "company_id": co, "state": state,
        "fiscal_engine_active": state == "active",  # CH.3 backward-compat
        "since": d.get("since"), "activation_effective_at": d.get("activation_effective_at"),
        "engine_version": d.get("engine_version") or ENGINE_VERSION,
        "profile_complete": complete, "blocking_count": blocking,
        "shadow_run_done": shadow_done, "has_vat_ch_transactions": locked,
        "can_enter_shadow": complete and state in ("legacy", "ready"),
        "can_activate": can_activate,
        "can_rollback": state == "active" and not locked,
        "reasons": reasons,
    }


async def _audit(db, ws, co, user, frm, to, extra=None):
    await db.fiscal_activation_audit.insert_one({
        "_id": f"facta_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
        "event": "fiscal_activation.transition", "from_state": frm, "to_state": to,
        "by": (user or {}).get("id"), "by_email": (user or {}).get("email"),
        "at": _now(), **(extra or {})})


async def _save(db, ws, co, patch):
    await db.company_fiscal_activation.update_one(
        {"workspace_id": ws, "company_id": co},
        {"$set": {"workspace_id": ws, "company_id": co, **patch}}, upsert=True)


async def enter_shadow(db, ws, co, user):
    d = await _doc(db, ws, co)
    if d["state"] == "shadow":
        return await get_status(db, ws, co)
    if d["state"] not in ("legacy", "ready"):
        raise HTTPException(status_code=409, detail="Passage en shadow impossible depuis l'état courant.")
    if not await _profile_complete(db, ws, co):
        raise HTTPException(status_code=409, detail="Profil fiscal incomplet : impossible de démarrer la comparaison.")
    await _save(db, ws, co, {"state": "shadow", "since": _now(), "shadow_started_at": _now(),
                             "engine_version": ENGINE_VERSION})
    await _audit(db, ws, co, user, d["state"], "shadow")
    return await get_status(db, ws, co)


async def mark_ready(db, ws, co, user):
    d = await _doc(db, ws, co)
    if d["state"] != "shadow":
        raise HTTPException(status_code=409, detail="Seule une société en shadow peut être marquée prête.")
    if not await _profile_complete(db, ws, co):
        raise HTTPException(status_code=409, detail="Profil fiscal incomplet.")
    if not await shadow_run_done(db, ws, co):
        raise HTTPException(status_code=409, detail="Comparaison en shadow non exécutée.")
    if await blocking_count(db, ws, co):
        raise HTTPException(status_code=409, detail="Des différences bloquantes subsistent.")
    await _save(db, ws, co, {"state": "ready", "since": _now()})
    await _audit(db, ws, co, user, "shadow", "ready")
    return await get_status(db, ws, co)


async def activate(db, ws, co, user, effective_at=None):
    d = await _doc(db, ws, co)
    if d["state"] == "active":
        return await get_status(db, ws, co)
    if d["state"] not in ("shadow", "ready"):
        raise HTTPException(status_code=409, detail="Activation impossible depuis l'état courant.")
    if not await _profile_complete(db, ws, co):
        raise HTTPException(status_code=409, detail="Profil fiscal incomplet : activation refusée.")
    if not await shadow_run_done(db, ws, co):
        raise HTTPException(status_code=409, detail="Comparaison en shadow requise avant activation.")
    if await blocking_count(db, ws, co):
        raise HTTPException(status_code=409, detail="Des différences bloquantes empêchent l'activation.")
    eff = effective_at or _now()
    await _save(db, ws, co, {"state": "active", "since": _now(), "activated_at": _now(),
                             "activation_effective_at": eff, "engine_version": ENGINE_VERSION})
    await _audit(db, ws, co, user, d["state"], "active", {"activation_effective_at": eff})
    return await get_status(db, ws, co)


async def rollback(db, ws, co, user, to_state="legacy"):
    d = await _doc(db, ws, co)
    if d["state"] != "active":
        raise HTTPException(status_code=409, detail="Aucune activation à annuler.")
    if to_state not in ("legacy", "shadow"):
        raise HTTPException(status_code=422, detail="Cible de rollback invalide.")
    if await has_vat_ch_transactions(db, ws, co):
        raise HTTPException(status_code=409,
                            detail="Rollback impossible : des transactions ont déjà été traitées par le moteur TVA. "
                                   "Un retour au comportement précédent doit être une décision explicite et documentée.")
    await _save(db, ws, co, {"state": to_state, "since": _now(),
                             "activation_effective_at": None, "activated_at": None})
    await _audit(db, ws, co, user, "active", to_state, {"kind": "rollback"})
    return await get_status(db, ws, co)


async def ensure_state_migration(db):
    """Backfill `state` from the legacy boolean without touching history."""
    await db.company_fiscal_activation.update_many(
        {"state": {"$exists": False}, "fiscal_engine_active": True}, {"$set": {"state": "active"}})
    await db.company_fiscal_activation.update_many(
        {"state": {"$exists": False}}, {"$set": {"state": "legacy"}})
    await db.fiscal_shadow_observations.create_index(
        [("workspace_id", 1), ("company_id", 1), ("classification", 1)], name="idx_shadow_obs")
