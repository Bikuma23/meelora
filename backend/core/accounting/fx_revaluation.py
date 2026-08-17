"""A4.6 — Unrealized FX revaluation + Aging AP ↔ GL reconciliation.

Built on A4.1–A4.5 + Financial Core P2. Conforms to STRAT-01 and the approved
scoping (memory/A4_6_SCOPING.md). Cardinal rules (validated with the owner):

 - NO parallel AP ledger / no second AP balance. The subledger (Aging) stays
   valued from canonical transactions at each transaction's HISTORICAL rate.
   The unrealized revaluation is carried SEPARATELY by AP_FX_REVAL; the
   historical AP control account is NEVER used to carry the adjustment.
 - Reconciliation identity:
       Aging AP (historical)  ± AP_FX_REVAL  =  AP presented at closing rate.
 - Calculation/simulation has NO GL effect. Posting is an explicit sensitive
   human action (accounting.fx_revaluation_post), creating EXACTLY ONE canonical
   P2 entry, balanced, atomic and idempotent. A reversal is auto-prepared for the
   NEXT period and linked bidirectionally; it never bypasses open/locked/closed.
 - Realized FX (A4.3) and unrealized FX (A4.6) are strictly separated: distinct
   accounts, distinct entries. A later realization never recycles the unrealized
   accounts.
 - Rate: prefer an explicit 'closing' rate, else fall back to the latest
   'current' rate — the fallback is ALWAYS surfaced in "Pourquoi ?", never
   silent. A rate with doubtful freshness raises an EXCEPTION requiring human
   review (never invented/auto-accepted).
 - Monetary classification (monetary|non_monetary) is deterministic and
   explainable — NEVER decided by AI.
 - Only the OPEN balance at the analysis date is revalued (never the historical
   amount already settled).
"""
import uuid
from datetime import datetime, timezone, date, timedelta

from fastapi import HTTPException

from ..financial import journal as journal_service
from ..financial import fx as fx_service
from .ar import _functional_currency, _money
from .gl import _get_period, _assert_postable_period
from . import ap as ap_service

_STALE_DAYS_DEFAULT = 7  # closing-rate freshness threshold (days) — governable later
_TOL = 0.01
_STATUSES = ("calculated", "posted", "reversed", "cancelled")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _audit(action, user, frm, to, extra=None):
    a = {"action": action, "by": user.get("id"), "by_email": user.get("email"),
         "from": frm, "to": to, "at": _now()}
    if extra:
        a.update(extra)
    return a


# --------------------------------------------------------------------------- #
# Monetary classification — deterministic, explainable, NEVER AI (STRAT-01 §10)
# --------------------------------------------------------------------------- #
def classify_ap_position(position_type):
    """Canonical monetary classification for an OPEN AP position. Returns
    (monetary_classification, classification_reason). Deterministic and
    explainable; a Country/Accounting Policy layer may govern this later, but
    an AI provider must NEVER decide it."""
    if position_type in ("invoice", "credit_note"):
        return "monetary", "Dette fournisseur ouverte réglée en trésorerie (poste monétaire)"
    # Advances that confer a right to receive goods/services are non-monetary and
    # are not revalued; refundable advances would be classified 'monetary' here.
    return "non_monetary", "Poste non monétaire — exclu de la réévaluation"


# --------------------------------------------------------------------------- #
# Rate resolution — closing first, traceable current fallback, staleness guard
# --------------------------------------------------------------------------- #
async def _resolve_closing_rate(db, ws, co, from_ccy, functional, as_of, stale_days):
    """Return a rate snapshot dict (never silently accepts a doubtful rate).
    {rate, effective_rate_date, source, rate_type, is_fallback, stale, reason}."""
    if (from_ccy or "").upper() == (functional or "").upper():
        return {"rate": 1.0, "effective_rate_date": as_of, "source": "identity",
                "rate_type": "closing", "is_fallback": False, "stale": False, "reason": "Même devise"}
    closing = await fx_service.get_rate_typed(db, ws, co, from_currency=from_ccy,
                                              to_currency=functional, on_date=as_of, rate_type="closing")
    used, is_fallback = closing, False
    if not used:
        used = await fx_service.get_rate_typed(db, ws, co, from_currency=from_ccy,
                                               to_currency=functional, on_date=as_of, rate_type="current")
        is_fallback = True
    if not used:
        return None
    eff = used.get("rate_date") or as_of
    stale = False
    try:
        stale = (date.fromisoformat(as_of[:10]) - date.fromisoformat(eff[:10])).days > int(stale_days)
    except Exception:
        stale = False
    reason = ("Taux de clôture du " + eff) if not is_fallback else \
             ("Taux de clôture indisponible — dernier taux courant du " + eff + " utilisé")
    return {"rate": used["rate"], "effective_rate_date": eff, "source": used.get("source", "stored"),
            "rate_type": ("current" if is_fallback else "closing"), "is_fallback": is_fallback,
            "stale": stale, "reason": reason}


# --------------------------------------------------------------------------- #
# Public shape
# --------------------------------------------------------------------------- #
def public_revaluation(d):
    if not d:
        return None
    return {
        "id": d.get("_id"), "as_of": d.get("as_of"), "status": d.get("status", "calculated"),
        "functional_currency": d.get("functional_currency"),
        "financial_period_id": d.get("financial_period_id"), "financial_year_id": d.get("financial_year_id"),
        "rate_snapshots": d.get("rate_snapshots") or [], "positions": d.get("positions") or [],
        "totals": d.get("totals") or {}, "exceptions": d.get("exceptions") or [],
        "revaluation_journal_entry_id": d.get("revaluation_journal_entry_id"),
        "reversal_journal_entry_id": d.get("reversal_journal_entry_id"),
        "reversal_prepared_for_period_id": d.get("reversal_prepared_for_period_id"),
        "reversal_status": d.get("reversal_status"),
        "prepared_by": d.get("prepared_by"), "calculated_at": d.get("calculated_at"),
        "posted_by": d.get("posted_by"), "posted_at": d.get("posted_at"),
        "created_at": d.get("created_at"), "audit": d.get("audit", []),
    }


async def _existing_posted(db, ws, co, as_of, period_id):
    return await db.ap_fx_revaluations.find_one({
        "workspace_id": ws, "company_id": co, "as_of": as_of,
        "financial_period_id": period_id, "status": {"$in": ["posted", "reversed"]}})


# --------------------------------------------------------------------------- #
# Calculate (no GL effect). Idempotent per (as_of, period): replaces any draft.
# --------------------------------------------------------------------------- #
async def calculate_revaluation(db, ws, co, user, *, as_of, period_id, stale_days=None):
    period = await _get_period(db, ws, co, period_id)
    functional = await _functional_currency(db, ws, co)
    stale_days = _STALE_DAYS_DEFAULT if stale_days is None else int(stale_days)

    # A posted run for this scope already exists → return it (read-only). Never a
    # second revaluation for the same perimeter (idempotence, anti double reval).
    posted = await _existing_posted(db, ws, co, as_of, period_id)
    if posted:
        return {**public_revaluation(posted), "already_posted": True}

    invs = await db.ap_invoices.find({"workspace_id": ws, "company_id": co,
                                      "document_status": "approved", "posting_status": "posted"}).to_list(None)
    positions, exceptions = [], []
    rate_cache, rate_snaps = {}, []
    total_gain, total_loss = 0.0, 0.0
    for inv in invs:
        ccy = (inv.get("currency") or functional).upper()
        if ccy == functional.upper():
            continue  # functional currency → no unrealized FX
        open_ccy = float(inv.get("balance") or 0)
        if open_ccy <= 0.001:
            continue
        cls, cls_reason = classify_ap_position("invoice")
        if cls != "monetary":
            continue
        if ccy not in rate_cache:
            snap = await _resolve_closing_rate(db, ws, co, ccy, functional, as_of, stale_days)
            rate_cache[ccy] = snap
            if snap is None:
                exceptions.append({"code": "rate_unavailable", "ref": ccy,
                                   "message": f"Aucun taux disponible pour {ccy}→{functional} au {as_of}."})
            else:
                rate_snaps.append({"currency": ccy, "requested_date": as_of,
                                   "effective_rate_date": snap["effective_rate_date"], "rate": snap["rate"],
                                   "source": snap["source"], "rate_type": snap["rate_type"],
                                   "is_fallback": snap["is_fallback"], "stale": snap["stale"], "reason": snap["reason"]})
                if snap["stale"]:
                    exceptions.append({"code": "rate_stale", "ref": ccy,
                                       "message": f"Taux {ccy}→{functional} au {snap['effective_rate_date']} : fraîcheur douteuse (> {stale_days} j)."})
        snap = rate_cache[ccy]
        if snap is None:
            continue
        hist_rate = (inv.get("fx") or {}).get("rate", 1.0)
        hist_func = fx_service.convert(open_ccy, hist_rate)
        closing_func = fx_service.convert(open_ccy, snap["rate"])
        delta = _money(closing_func - hist_func)  # >0 = payable worth more = LOSS
        if delta > 0:
            total_loss = _money(total_loss + delta)
        elif delta < 0:
            total_gain = _money(total_gain + (-delta))
        positions.append({
            "position_type": "invoice", "source_id": inv["_id"],
            "source_number": inv.get("supplier_invoice_number"), "supplier_id": inv.get("supplier_id"),
            "currency": ccy, "open_balance_ccy": _money(open_ccy),
            "historical_rate": hist_rate, "historical_func": _money(hist_func),
            "closing_rate": snap["rate"], "closing_func": _money(closing_func), "delta_func": delta,
            "monetary_classification": cls, "classification_reason": cls_reason,
            "journal_entry_id_source": inv.get("journal_entry_id"),
            "rate_is_fallback": snap["is_fallback"], "rate_reason": snap["reason"]})

    net_delta = _money(total_loss - total_gain)  # >0 net loss, <0 net gain
    totals = {"functional_currency": functional, "position_count": len(positions),
              "total_unrealized_loss": total_loss, "total_unrealized_gain": total_gain,
              "net_delta_func": net_delta,
              "by_currency": [{"currency": r["currency"], "rate": r["rate"],
                               "rate_type": r["rate_type"], "is_fallback": r["is_fallback"]} for r in rate_snaps]}

    now = _now()
    # Replace any existing NON-posted (draft) run for this scope so recalculating
    # the same date never accumulates multiple runs / entries.
    await db.ap_fx_revaluations.delete_many({
        "workspace_id": ws, "company_id": co, "as_of": as_of,
        "financial_period_id": period_id, "status": "calculated"})
    doc = {"_id": f"fxrev_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
           "as_of": as_of, "financial_period_id": period["_id"], "financial_year_id": period.get("financial_year_id"),
           "functional_currency": functional, "status": "calculated",
           "rate_snapshots": rate_snaps, "positions": positions, "totals": totals, "exceptions": exceptions,
           "revaluation_journal_entry_id": None, "reversal_journal_entry_id": None,
           "reversal_prepared_for_period_id": None, "reversal_status": None,
           "prepared_by": user.get("id"), "calculated_at": now, "created_at": now,
           "audit": [_audit("calculate", user, None, "calculated",
                            {"positions": len(positions), "net_delta": net_delta})]}
    await db.ap_fx_revaluations.insert_one(doc)
    return {**public_revaluation(doc), "already_posted": False}


async def get_revaluation(db, ws, co, rid):
    d = await db.ap_fx_revaluations.find_one({"_id": rid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Réévaluation introuvable")
    return d


async def list_revaluations(db, ws, co, *, status=None):
    q = {"workspace_id": ws, "company_id": co}
    if status:
        q["status"] = status
    docs = await db.ap_fx_revaluations.find(q).sort("created_at", -1).to_list(500)
    return [public_revaluation(d) for d in docs]


def _reval_gl_lines(mapping, total_loss, total_gain):
    """Balanced revaluation lines. Historical AP control is NEVER touched — the
    adjustment is carried by AP_FX_REVAL against the DISTINCT unrealized P&L."""
    lines = []
    if total_loss > _TOL:
        lines.append({"account": mapping["fx_unrealized_loss_account_code"],
                      "description": "Perte de change non réalisée", "debit": total_loss, "credit": 0})
    if total_gain > _TOL:
        lines.append({"account": mapping["fx_unrealized_gain_account_code"],
                      "description": "Gain de change non réalisé", "debit": 0, "credit": total_gain})
    net = _money(total_loss - total_gain)
    if net > _TOL:
        lines.append({"account": mapping["ap_fx_reval_account_code"],
                      "description": "Ajustement réévaluation fournisseurs", "debit": 0, "credit": net})
    elif net < -_TOL:
        lines.append({"account": mapping["ap_fx_reval_account_code"],
                      "description": "Ajustement réévaluation fournisseurs", "debit": -net, "credit": 0})
    return lines


async def _next_period(db, ws, co, period):
    """First chronological period after ``period`` (by start_date)."""
    nxt = await db.financial_periods.find({
        "workspace_id": ws, "company_id": co,
        "start_date": {"$gt": period.get("end_date", period.get("start_date"))}}).sort("start_date", 1).to_list(1)
    return nxt[0] if nxt else None


# --------------------------------------------------------------------------- #
# Post (SENSITIVE) — exactly one canonical P2 entry + auto-prepared reversal
# --------------------------------------------------------------------------- #
async def post_revaluation(db, ws, co, user, rid):
    d = await get_revaluation(db, ws, co, rid)
    if d.get("status") in ("posted", "reversed") and d.get("revaluation_journal_entry_id"):
        return public_revaluation(d)  # idempotent — no duplicate ledger write
    if d.get("status") != "calculated":
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    # Maker-checker: the preparer of the run cannot post their own revaluation.
    if d.get("prepared_by") == user.get("id"):
        raise HTTPException(status_code=403,
                            detail="Séparation des tâches : le préparateur du calcul ne peut pas comptabiliser sa propre réévaluation.")
    # Doubtful rate must be resolved before posting (never post on a stale rate).
    if any(e.get("code") in ("rate_stale", "rate_unavailable") for e in d.get("exceptions") or []):
        raise HTTPException(status_code=409,
                            detail="Taux à fraîcheur douteuse ou indisponible : mettez à jour le taux de clôture avant de comptabiliser.")
    # Anti double revaluation for the same perimeter/period.
    other = await _existing_posted(db, ws, co, d["as_of"], d["financial_period_id"])
    if other:
        raise HTTPException(status_code=409, detail="Une réévaluation est déjà comptabilisée pour cette date et cette période.")
    totals = d.get("totals") or {}
    total_loss = float(totals.get("total_unrealized_loss") or 0)
    total_gain = float(totals.get("total_unrealized_gain") or 0)
    if total_loss <= _TOL and total_gain <= _TOL:
        raise HTTPException(status_code=409, detail="Aucune différence de change à comptabiliser.")
    period = await _get_period(db, ws, co, d["financial_period_id"])
    await _assert_postable_period(db, ws, co, period)
    mapping = await ap_service.get_ap_mapping(db, ws, co)
    gl = _reval_gl_lines(mapping, total_loss, total_gain)
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=period.get("financial_year_id"), financial_period_id=period["_id"],
        entry_date=d["as_of"], reference=f"FXREV-{d['_id'][-8:]}",
        description=f"Réévaluation FX non réalisée au {d['as_of']}", lines=gl,
        external_id=f"{d['_id']}:reval", source_type="ap_fx_revaluation", source_system="purchases")
    await db.ap_fx_revaluations.update_one({"_id": rid}, {"$set": {
        "status": "posted", "revaluation_journal_entry_id": je["_id"],
        "posted_by": user.get("id"), "posted_at": _now()},
        "$push": {"audit": _audit("post", user, "calculated", "posted", {"je": je["_id"]})}})
    # Auto-prepare the reversal for the next period; post it now if that period is
    # open, otherwise keep it PREPARED (never bypass locked/closed).
    nxt = await _next_period(db, ws, co, period)
    if nxt:
        await db.ap_fx_revaluations.update_one({"_id": rid}, {"$set": {
            "reversal_prepared_for_period_id": nxt["_id"], "reversal_status": "prepared"}})
        if nxt.get("status") == "open":
            try:
                await _post_reversal_internal(db, ws, co, user, rid)
            except HTTPException:
                pass  # keep as prepared; a user can post it explicitly later
    return public_revaluation(await get_revaluation(db, ws, co, rid))


async def _post_reversal_internal(db, ws, co, user, rid):
    d = await get_revaluation(db, ws, co, rid)
    if d.get("reversal_journal_entry_id"):
        return d  # idempotent
    if d.get("status") != "posted" or not d.get("revaluation_journal_entry_id"):
        raise HTTPException(status_code=409, detail="Aucune réévaluation comptabilisée à extourner.")
    tgt_id = d.get("reversal_prepared_for_period_id")
    if not tgt_id:
        raise HTTPException(status_code=409, detail="Aucune période suivante disponible pour l'extourne.")
    period = await _get_period(db, ws, co, tgt_id)
    await _assert_postable_period(db, ws, co, period)
    totals = d.get("totals") or {}
    total_loss = float(totals.get("total_unrealized_loss") or 0)
    total_gain = float(totals.get("total_unrealized_gain") or 0)
    mapping = await ap_service.get_ap_mapping(db, ws, co)
    # SAME accounts reversed: swap debit/credit of every original revaluation line.
    orig = _reval_gl_lines(mapping, total_loss, total_gain)
    rev_lines = [{"account": ln["account"], "description": f"Extourne — {ln['description']}",
                  "debit": ln.get("credit", 0), "credit": ln.get("debit", 0)} for ln in orig]
    rev_je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=period.get("financial_year_id"), financial_period_id=period["_id"],
        entry_date=period.get("start_date"), reference=f"FXREV-REV-{d['_id'][-8:]}",
        description=f"Extourne réévaluation FX au {d['as_of']}", lines=rev_lines,
        external_id=f"{d['_id']}:reversal", source_type="ap_fx_revaluation_reversal", source_system="purchases",
        reverses_journal_entry_id=d["revaluation_journal_entry_id"])
    await journal_service.link_reversal(db, ws, co, d["revaluation_journal_entry_id"], rev_je["_id"])
    await db.ap_fx_revaluations.update_one({"_id": rid}, {"$set": {
        "status": "reversed", "reversal_journal_entry_id": rev_je["_id"], "reversal_status": "posted"},
        "$push": {"audit": _audit("reverse", user, "posted", "reversed", {"je": rev_je["_id"]})}})
    return await get_revaluation(db, ws, co, rid)


async def post_reversal(db, ws, co, user, rid):
    """Post a PREPARED reversal (permission enforced at route). Inherits the
    source run's provenance; posting still respects period + permission."""
    return public_revaluation(await _post_reversal_internal(db, ws, co, user, rid))


# --------------------------------------------------------------------------- #
# Reconciliation — Aging AP (historical) ± AP_FX_REVAL = AP presented (closing)
# Derived report, recomputed on demand. NO balance stored, no forcing entry.
# --------------------------------------------------------------------------- #
async def _gl_net_credit(db, ws, co, account_codes, as_of):
    """Net credit (Σcredit − Σdebit, functional) of the given account_codes over
    posted journal entries with entry_date <= as_of."""
    codes = set(c for c in account_codes if c)
    entries = await db.journal_entries.find({
        "workspace_id": ws, "company_id": co, "entry_date": {"$lte": as_of}}).to_list(None)
    ids = {e["_id"] for e in entries}
    if not ids:
        return 0.0
    net = 0.0
    lines = await db.journal_entry_lines.find({
        "workspace_id": ws, "company_id": co, "account_code": {"$in": list(codes)}}).to_list(None)
    for ln in lines:
        if ln.get("journal_entry_id") in ids:
            net += float(ln.get("credit") or 0) - float(ln.get("debit") or 0)
    return _money(net)


async def reconcile(db, ws, co, as_of=None):
    as_of = as_of or _now()[:10]
    functional = await _functional_currency(db, ws, co)
    mapping = await ap_service.get_ap_mapping(db, ws, co)
    ap_code = mapping["ap_account_code"]
    reval_code = mapping["ap_fx_reval_account_code"]

    ag = await ap_service.aging(db, ws, co, as_of=as_of)
    subledger = _money(ag["accounting_total"])           # posted open invoices @ historical
    approved_unposted = _money(ag.get("approved_unposted") or 0)

    gl_ap_control = await _gl_net_credit(db, ws, co, [ap_code], as_of)
    gl_ap_reval = await _gl_net_credit(db, ws, co, [reval_code], as_of)

    # Legitimate/timing components between the subledger and the GL control.
    # GL only holds POSTED invoices; the subledger floors each balance at 0, so
    # the executed-unposted relief must be capped per invoice (an over-relief
    # never reduces the subledger below zero — otherwise a false anomaly appears).
    invs_all = {inv["_id"]: inv async for inv in db.ap_invoices.find({"workspace_id": ws, "company_id": co})}
    posted_paid = {}       # invoice_id -> posted-payment applied (functional @ invoice rate)
    executed_paid = {}     # invoice_id -> executed-not-posted applied (functional @ invoice rate)
    posted_advances = 0.0
    posted_applied_to_unposted = 0.0
    async for p in db.ap_payments.find({"workspace_id": ws, "company_id": co,
                                        "payment_state": {"$in": ["executed", "posted"]}}):
        rate = (p.get("fx") or {}).get("rate", 1.0)
        applied = _money(sum(float(a.get("amount_applied") or 0) for a in p.get("allocations") or [] if a.get("active", True)))
        is_posted = p.get("payment_state") == "posted"
        if is_posted:
            advance = _money(float(p.get("amount") or 0) - applied)
            if advance > 0.001:
                posted_advances = _money(posted_advances + fx_service.convert(advance, rate))
        for a in p.get("allocations") or []:
            if not a.get("active", True):
                continue
            iid = a.get("invoice_id")
            amt_func = fx_service.convert(float(a.get("amount_applied") or 0), a.get("invoice_fx_rate") or rate)
            inv = invs_all.get(iid)
            inv_is_posted = bool(inv and inv.get("posting_status") == "posted")
            if is_posted:
                if inv_is_posted:
                    posted_paid[iid] = _money(posted_paid.get(iid, 0.0) + amt_func)
                else:
                    posted_applied_to_unposted = _money(posted_applied_to_unposted + amt_func)
            elif inv_is_posted:  # executed, not posted
                executed_paid[iid] = _money(executed_paid.get(iid, 0.0) + amt_func)

    executed_unposted_relief = 0.0
    for iid, exec_f in executed_paid.items():
        inv = invs_all.get(iid)
        if not inv:
            continue
        hr = (inv.get("fx") or {}).get("rate", 1.0)
        total_f = fx_service.convert(float(inv.get("total") or 0), hr)
        credited_f = fx_service.convert(float(inv.get("credited_total") or 0), hr)
        posted_only_remaining = max(total_f - credited_f - posted_paid.get(iid, 0.0), 0.0)
        executed_unposted_relief = _money(executed_unposted_relief + min(exec_f, posted_only_remaining))

    available_credits = 0.0
    async for c in db.ap_supplier_credits.find({"workspace_id": ws, "company_id": co, "status": "available"}):
        available_credits = _money(available_credits + float(c.get("remaining") or 0))

    expected_gl = _money(subledger - posted_advances - posted_applied_to_unposted
                         + executed_unposted_relief - available_credits)
    residual = _money(gl_ap_control - expected_gl)
    reconciled = abs(residual) <= _TOL

    differences = []
    if not reconciled:
        differences.append({"category": "anomaly", "label": "Écart inexpliqué",
                            "amount_func": residual, "severity": "high",
                            "hint": "Écriture directe au compte de contrôle hors sous-registre, ou différence d'arrondi anormale."})
    if abs(gl_ap_reval) > _TOL:
        differences.append({"category": "legitimate", "label": "Réévaluation FX non réalisée (AP_FX_REVAL)",
                            "amount_func": gl_ap_reval, "hint": "Ajustement de présentation au taux de clôture — non extourné."})
    if posted_advances > _TOL:
        differences.append({"category": "legitimate", "label": "Avances / paiements non affectés",
                            "amount_func": _money(-posted_advances), "hint": "Avances comptabilisées réduisant le compte fournisseurs."})
    if available_credits > _TOL:
        differences.append({"category": "legitimate", "label": "Crédits fournisseurs disponibles",
                            "amount_func": _money(-available_credits), "hint": "Sur-crédits générant un solde débiteur fournisseur."})
    if executed_unposted_relief > _TOL:
        differences.append({"category": "temporal", "label": "Paiements exécutés non comptabilisés",
                            "amount_func": _money(executed_unposted_relief), "hint": "Sous-registre déjà réduit ; comptabilisation du paiement en attente."})
    if posted_applied_to_unposted > _TOL:
        differences.append({"category": "temporal", "label": "Paiements comptabilisés sur factures non comptabilisées",
                            "amount_func": _money(-posted_applied_to_unposted), "hint": "Paiement comptabilisé alors que la facture reste à comptabiliser."})
    if approved_unposted > _TOL:
        differences.append({"category": "temporal", "label": "Factures approuvées non comptabilisées",
                            "amount_func": approved_unposted, "hint": "Engagements hors Grand Livre en attente de comptabilisation."})

    # Exceptions First ordering: anomalies first, then legitimate, then temporal.
    order = {"anomaly": 0, "legitimate": 1, "temporal": 2}
    differences.sort(key=lambda x: order.get(x["category"], 9))

    return {
        "as_of": as_of, "functional_currency": functional,
        "ap_control_account": ap_code, "ap_fx_reval_account": reval_code,
        "subledger_aging_func": subledger, "ap_fx_reval_balance_func": gl_ap_reval,
        "gl_ap_control_func": gl_ap_control, "expected_gl_func": expected_gl,
        "residual_func": residual, "status": "reconciled" if reconciled else "differences",
        "components": {"posted_advances_func": _money(posted_advances),
                       "executed_unposted_relief_func": executed_unposted_relief,
                       "posted_applied_to_unposted_func": posted_applied_to_unposted,
                       "available_credits_func": available_credits,
                       "approved_unposted_func": approved_unposted},
        "differences": differences, "aging_rows": [r for r in ag["rows"] if r["kind"] == "accounting"],
    }


async def ensure_indexes(db):
    await db.ap_fx_revaluations.create_index(
        [("workspace_id", 1), ("company_id", 1), ("as_of", 1), ("financial_period_id", 1)],
        name="idx_ap_fxrev_scope")
    await db.ap_fx_revaluations.create_index(
        [("workspace_id", 1), ("company_id", 1), ("status", 1)], name="idx_ap_fxrev_status")
