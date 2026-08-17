"""CH.1 — Jurisdiction / Accounting Policy Engine (canonical, versioned).

Foundation for Country Packs (CH/CA/EU). Business engines (A2/A3/A4/P2) ask a
POLICY QUESTION and receive a resolved, explainable, snapshotable decision — they
never contain `if country == CH`. Cardinal rules (GATE CH.1):

  - Canonical API: resolve(domain, context, as_of) -> PolicyDecision ; explain(snapshot).
  - Append-only / WORM: a policy version has status draft|published. Only PUBLISHED
    versions are usable by resolve(). A draft is freely editable; once published it
    is immutable for business content. A correction => a NEW version.
  - Jurisdiction hierarchy is GENERIC (specificity by path depth), never the word
    "canton": 'CH-GE' > 'CH' > '*' ; 'CA-QC' > 'CA' > '*' ; 'EU-FR' > 'EU' > '*'.
  - Deterministic resolution & conflicts: specificity -> scope(company>system) ->
    priority -> effective_from(recent). A remaining perfect tie => policy_conflict
    (fail-closed). No arbitrary tie-break by _id / Mongo order / created_at.
  - Per-domain absence strategy: required (fail-closed, e.g. vat) / fallback_allowed
    (explicit Core canonical fallback, e.g. rounding) / optional (feature simply
    unavailable, e.g. document_ai). No generic silent "neutral" financial decision.
  - Snapshot stores the RESOLVED RESULT (+ reason + sources), so explain() of a
    historical fact NEVER re-resolves against today's policies.
  - Resolution cache is invalidated from a new policy's effective_from (even if in
    the past) — distinct from transaction snapshots, which are never invalidated.
  - sources[] is a structured object (authority, title, ref, url, published version/
    date, effective_from, verified_at, archived_hash?).
  - Overridability declared per policy: configurable | overrideable | non_overrideable.
    manage/Client Admin can NEVER override a non_overrideable regulatory rule.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

ENGINE_VERSION = "CH1-1.0"

# Per-domain absence strategy.
DOMAIN_STRATEGY = {
    "vat": "required",
    "vat_ch": "required",
    "monetary_classification": "required",
    "fx_freshness": "fallback_allowed",
    "rounding": "fallback_allowed",
    "document_ai": "optional",
}
# Explicit Core canonical fallbacks (only for fallback_allowed domains).
CORE_FALLBACK = {
    "fx_freshness": {"result": {"stale_days": 7}, "reason": "Valeur canonique par défaut du socle (fraîcheur de taux 7 jours)."},
    "rounding": {"result": {"decimals": 2, "mode": "half_up"}, "reason": "Arrondi canonique du socle (2 décimales)."},
}


class PolicyError(Exception):
    """Fail-closed policy resolution error (never a silent financial decision)."""
    def __init__(self, code, message, detail=None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _inputs_hash(domain, context, as_of):
    return hashlib.sha256(_canonical({"d": domain, "c": context or {}, "a": as_of,
                                      "e": ENGINE_VERSION}).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Jurisdiction hierarchy (generic — depth = specificity, no hardcoded "canton")
# --------------------------------------------------------------------------- #
def jurisdiction_candidates(country, subdivision=None):
    """Most-specific → least-specific jurisdictions for a context.
    e.g. ('CH','GE') -> ['CH-GE','CH','*'] ; ('CA','QC') -> ['CA-QC','CA','*']."""
    out = []
    c = (country or "").upper() or None
    s = (subdivision or "").upper() or None
    if c and s:
        out.append(f"{c}-{s}")
    if c:
        out.append(c)
    out.append("*")
    return out


def _specificity(jurisdiction, candidates):
    # Higher = more specific. candidates ordered specific->general.
    try:
        return len(candidates) - candidates.index(jurisdiction)
    except ValueError:
        return -1


# --------------------------------------------------------------------------- #
# Policy lifecycle (draft -> published ; append-only versions)
# --------------------------------------------------------------------------- #
def _pid(scope, domain, jurisdiction, key="base"):
    return f"{scope}:{domain}:{jurisdiction}:{key}"


async def create_draft(db, *, domain, jurisdiction, rules, sources, effective_from,
                       effective_to=None, priority=100, scope="system", key="base",
                       overridability="non_overrideable", workspace_id=None, company_id=None,
                       user=None):
    if scope == "company" and not (workspace_id and company_id):
        raise PolicyError("bad_scope", "Un override société exige workspace_id + company_id.")
    policy_id = _pid(scope, domain, jurisdiction, key)
    published = await db.jurisdiction_policies.find(
        {"policy_id": policy_id, "status": "published"}).sort("policy_version", -1).to_list(1)
    next_version = (published[0]["policy_version"] + 1) if published else 1
    doc = {"_id": f"pol_{uuid.uuid4().hex}", "policy_id": policy_id,
           "domain": domain, "jurisdiction": jurisdiction, "scope": scope, "key": key,
           "policy_version": next_version, "status": "draft",
           "effective_from": effective_from, "effective_to": effective_to, "priority": int(priority),
           "overridability": overridability, "rules": rules or [], "sources": sources or [],
           "workspace_id": workspace_id if scope == "company" else "system",
           "company_id": company_id if scope == "company" else None,
           "created_by": (user or {}).get("id"), "created_at": _now(), "published_at": None}
    await db.jurisdiction_policies.insert_one(doc)
    return doc


async def update_draft(db, policy_doc_id, *, rules=None, sources=None, effective_from=None,
                       effective_to=None, priority=None, overridability=None):
    d = await db.jurisdiction_policies.find_one({"_id": policy_doc_id})
    if not d:
        raise PolicyError("not_found", "Politique introuvable.")
    if d.get("status") != "draft":
        raise PolicyError("immutable", "Seule une version brouillon peut être modifiée.")
    upd = {}
    for k, v in (("rules", rules), ("sources", sources), ("effective_from", effective_from),
                 ("effective_to", effective_to), ("priority", priority),
                 ("overridability", overridability)):
        if v is not None:
            upd[k] = v
    if upd:
        await db.jurisdiction_policies.update_one({"_id": policy_doc_id}, {"$set": upd})
    return await db.jurisdiction_policies.find_one({"_id": policy_doc_id})


async def check_overlaps(db, domain, jurisdiction, effective_from, priority, scope,
                         key, workspace_id=None, exclude_id=None):
    """Publication-time defense: another PUBLISHED policy of a DIFFERENT logical id
    with the same (domain, jurisdiction, scope, priority) starting on the same
    effective_from = ambiguous overlap."""
    q = {"domain": domain, "jurisdiction": jurisdiction, "scope": scope,
         "priority": int(priority), "status": "published", "effective_from": effective_from,
         "policy_id": {"$ne": _pid(scope, domain, jurisdiction, key)}}
    if scope == "company":
        q["workspace_id"] = workspace_id
    if exclude_id:
        q["_id"] = {"$ne": exclude_id}
    clash = await db.jurisdiction_policies.find_one(q)
    return clash


async def publish_draft(db, policy_doc_id, *, user=None):
    d = await db.jurisdiction_policies.find_one({"_id": policy_doc_id})
    if not d:
        raise PolicyError("not_found", "Politique introuvable.")
    if d.get("status") == "published":
        return d  # idempotent
    if d.get("status") != "draft":
        raise PolicyError("bad_state", f"Publication impossible (statut « {d.get('status')} »).")
    clash = await check_overlaps(db, d["domain"], d["jurisdiction"], d["effective_from"],
                                 d["priority"], d["scope"], d["key"],
                                 workspace_id=d.get("workspace_id"), exclude_id=d["_id"])
    if clash:
        raise PolicyError("policy_conflict",
                          "Chevauchement de politiques détecté à la publication.",
                          {"clashes_with": clash["_id"]})
    await db.jurisdiction_policies.update_one(
        {"_id": policy_doc_id}, {"$set": {"status": "published", "published_at": _now()}})
    await db.policy_audit.insert_one({
        "_id": f"polaud_{uuid.uuid4().hex}", "event": "policy.published",
        "policy_id": d["policy_id"], "policy_version": d["policy_version"], "domain": d["domain"],
        "jurisdiction": d["jurisdiction"], "effective_from": d["effective_from"],
        "by": (user or {}).get("id"), "at": _now()})
    _invalidate_cache(d["domain"], d["jurisdiction"], d["effective_from"])
    return await db.jurisdiction_policies.find_one({"_id": policy_doc_id})


async def publish_policy(db, **kw):
    """Convenience: create a draft and publish it in one call (used by seeds/tests)."""
    user = kw.pop("user", None)
    d = await create_draft(db, user=user, **kw)
    return await publish_draft(db, d["_id"], user=user)


# --------------------------------------------------------------------------- #
# Resolution cache (safe: published versions are immutable). Invalidated from a
# new policy's effective_from (even if in the past) — NEVER touches snapshots.
# --------------------------------------------------------------------------- #
_CACHE = {}  # key -> {"decision": ..., "domain":..., "jurisdiction":..., "as_of":...}


def _invalidate_cache(domain, jurisdiction, effective_from):
    drop = []
    base = jurisdiction.split("-")[0] if jurisdiction and jurisdiction != "*" else None
    for k, e in _CACHE.items():
        if e["domain"] != domain:
            continue
        # invalidate resolutions whose as_of is on/after the new effective_from and
        # whose jurisdiction is within the affected branch (or global).
        if e["as_of"] >= effective_from and (jurisdiction == "*" or base is None
                                             or e["jurisdiction"].split("-")[0] == base):
            drop.append(k)
    for k in drop:
        _CACHE.pop(k, None)


def clear_cache():
    _CACHE.clear()


# --------------------------------------------------------------------------- #
# Generic published-policy resolution (deterministic, fail-closed on ties)
# --------------------------------------------------------------------------- #
async def _resolve_policy_doc(db, ws, co, domain, candidates, as_of):
    q = {"domain": domain, "status": "published", "jurisdiction": {"$in": candidates},
         "effective_from": {"$lte": as_of},
         "$or": [{"scope": "system"},
                 {"scope": "company", "workspace_id": ws, "company_id": co}]}
    docs = await db.jurisdiction_policies.find(q).to_list(1000)
    docs = [d for d in docs if not d.get("effective_to") or d["effective_to"] > as_of]
    if not docs:
        return None
    # 1) within each logical policy_id keep the current version (latest effective_from, then version).
    by_pid = {}
    for d in docs:
        cur = by_pid.get(d["policy_id"])
        if (cur is None or (d["effective_from"], d["policy_version"])
                > (cur["effective_from"], cur["policy_version"])):
            by_pid[d["policy_id"]] = d
    finalists = list(by_pid.values())
    # 2) rank across policy_ids: specificity -> scope -> priority -> effective_from.
    def rank(d):
        return (_specificity(d["jurisdiction"], candidates),
                1 if d["scope"] == "company" else 0,
                d["priority"], d["effective_from"])
    finalists.sort(key=rank, reverse=True)
    top = finalists[0]
    if len(finalists) > 1 and rank(finalists[1]) == rank(top) \
            and finalists[1]["policy_id"] != top["policy_id"]:
        raise PolicyError("policy_conflict",
                          f"Conflit de politiques {domain}/{top['jurisdiction']} : départage impossible.",
                          {"a": top["_id"], "b": finalists[1]["_id"]})
    return top


def _match_rule(policy_doc, context):
    for r in policy_doc.get("rules", []):
        m = r.get("match") or {}
        if all((context or {}).get(k) == v for k, v in m.items()):
            return r
    return None


# --------------------------------------------------------------------------- #
# PolicyDecision assembly
# --------------------------------------------------------------------------- #
def _decision(domain, jurisdiction, policy_doc, rule, result, reason, context, as_of,
              sources=None, extra=None):
    d = {"domain": domain, "jurisdiction": jurisdiction,
         "policy_id": (policy_doc or {}).get("policy_id"),
         "policy_version": (policy_doc or {}).get("policy_version"),
         "effective_from": (policy_doc or {}).get("effective_from"),
         "effective_to": (policy_doc or {}).get("effective_to"),
         "rule_id": (rule or {}).get("rule_id"),
         "result": result, "reason": reason,
         "sources": sources if sources is not None else (policy_doc or {}).get("sources", []),
         "overridability": (policy_doc or {}).get("overridability", "non_overrideable"),
         "decision_id": f"dec_{uuid.uuid4().hex}", "engine_version": ENGINE_VERSION,
         "inputs_hash": _inputs_hash(domain, context, as_of), "resolved_at": _now(),
         "context": context, "as_of": as_of}
    if extra:
        d.update(extra)
    return d


# --------------------------------------------------------------------------- #
# Domain handlers
# --------------------------------------------------------------------------- #
async def _handle_vat(db, ws, co, context, as_of, candidates):
    """Migration wrapper: rates/versions come from the existing `sales_tax_codes`
    (source of truth → 100% parity). The vat policy doc carries sources/metadata."""
    from ..financial import tax_engine
    code = (context or {}).get("tax_code")
    if not code:
        raise PolicyError("no_matching_rule", "Code de taxe requis pour la décision TVA.")
    tc = await db.sales_tax_codes.find_one({"workspace_id": ws, "company_id": co, "code": code})
    if not tc:
        raise PolicyError("policy_unavailable",
                          f"Code de taxe « {code} » introuvable : décision fiscale obligatoire indisponible.")
    kind = tc.get("tax_kind", "taxable")
    version = None if kind in ("zero_rated", "exempt") else tax_engine._pick_version(tc, as_of)
    components = (version or {}).get("components", []) if version else []
    eff = (version or {}).get("effective_date")
    meta = await _resolve_policy_doc(db, ws, co, "vat", candidates, as_of)  # sources/metadata (optional)
    result = {"tax_code": code, "tax_kind": kind, "rate_version_effective_date": eff,
              "components": components}
    rate_txt = ", ".join(f"{c['name']} {float(c['rate'])*100:.2f}%" for c in components) or "0%"
    reason = f"Code « {code} » ({kind}) — {rate_txt} en vigueur au {eff or as_of}."
    return _decision("vat", (meta or {}).get("jurisdiction") or candidates[0], meta, None,
                     result, reason, context, as_of,
                     sources=(meta or {}).get("sources", []))


async def _handle_policy_doc_domain(db, ws, co, domain, context, as_of, candidates):
    policy = await _resolve_policy_doc(db, ws, co, domain, candidates, as_of)
    if policy is None:
        return None
    rule = _match_rule(policy, context)
    if rule is None:
        raise PolicyError("no_matching_rule",
                          f"Aucune règle {domain} applicable au contexte fourni.")
    return _decision(domain, policy["jurisdiction"], policy, rule, rule.get("result"),
                     rule.get("reason") or f"Règle {rule.get('rule_id')} appliquée.",
                     context, as_of)


async def _company_vat_status(db, ws, co, context):
    if context and context.get("vat_status"):
        return context["vat_status"]
    from . import jurisdiction
    prof = await jurisdiction.get_compliance_profile(db, ws, co)
    return prof.get("vat_status") or "taxable"


async def _vat_fx(db, ws, co, context, tax_date):
    """VAT FX: snapshot the FISCAL-date rate (AFC), conceptually distinct from the
    booking (transaction) FX and from closing/revaluation FX (A4.6). Reads the
    canonical exchange_rates registry — never a duplicate FX store."""
    ccy = (context or {}).get("currency")
    if not ccy:
        return None
    from ..financial import fx as fx_service
    from ..accounting.ar import _functional_currency
    functional = await _functional_currency(db, ws, co)
    if (ccy or "").upper() == (functional or "").upper():
        return {"applicable": False, "currency": ccy, "functional_currency": functional}
    rate = await fx_service.get_rate(db, ws, co, from_currency=ccy, to_currency=functional, on_date=tax_date)
    if not rate:
        return {"applicable": True, "currency": ccy, "functional_currency": functional,
                "rate": None, "needs_review": True, "reason": "Taux fiscal indisponible à la date fiscale."}
    return {"applicable": True, "currency": ccy, "functional_currency": functional,
            "tax_date": tax_date, "rate": rate.get("rate"), "rate_source": rate.get("source"),
            "basis": "fiscal_date_rate",
            "reason": f"Conversion TVA au taux du {rate.get('rate_date') or tax_date} (indépendant du taux de clôture)."}


async def _handle_vat_ch(db, ws, co, context, as_of, candidates):
    """Structured Swiss VAT decision (output/input) — A3/A4 consume it, never CH rules."""
    policy = await _resolve_policy_doc(db, ws, co, "vat_ch", candidates, as_of)
    if policy is None:
        return None
    conf = (policy.get("rules") or [{}])[0].get("result", {})
    rates = conf.get("rates", {})
    reporting = conf.get("reporting", {})
    roles = conf.get("account_roles", {})
    ctx = context or {}
    side = ctx.get("side", "output")
    kind = ctx.get("transaction_kind", "domestic")
    tax_date = ctx.get("tax_date") or as_of
    vat_status = await _company_vat_status(db, ws, co, ctx)

    def rate_for(cat):
        return float(rates.get(cat, 0.0))

    res = {"tax_code": None, "tax_treatment": None, "rate": 0.0, "side": side,
           "recoverability": None, "reporting_mapping": {}, "account_roles": {},
           "legal_basis": conf.get("legal_basis", []), "vat_status": vat_status}
    needs_review = False

    if side == "output":
        cat = ctx.get("rate_category")
        if kind == "export":
            res.update({"tax_treatment": "zero_rated_export", "tax_code": "CH_VAT_EXPORT", "rate": 0.0,
                        "reporting_mapping": {"base_field": "200", "deduction_field": "220"}})
            reason = "Exportation / prestation à l'étranger : exonérée avec droit à déduction (0 %)."
        elif cat == "exempt":
            res.update({"tax_treatment": "exempt_without_credit", "tax_code": "CH_VAT_EXEMPT", "rate": 0.0,
                        "reporting_mapping": {"base_field": "200", "exempt_field": "230"}})
            reason = "Prestation exclue du champ (art. 21) : sans TVA ni droit à déduction amont."
        elif cat == "out_of_scope":
            res.update({"tax_treatment": "out_of_scope", "tax_code": "CH_VAT_OOS", "rate": 0.0,
                        "reporting_mapping": {"base_field": "910"}})
            reason = "Opération hors champ de la TVA."
        else:
            cat = cat or "standard"  # Happy Path proposal for a domestic sale
            code = {"standard": "CH_VAT_STD", "reduced": "CH_VAT_REDUCED", "accommodation": "CH_VAT_ACC"}[cat]
            tf = {"standard": "302", "reduced": "312", "accommodation": "342"}[cat]
            res.update({"tax_treatment": f"{cat}_rated" if cat != "standard" else "standard_rated",
                        "tax_code": code, "rate": rate_for(cat),
                        "reporting_mapping": {"base_field": "200", "tax_field": tf},
                        "account_roles": {"output_vat_role": roles.get("output_vat_role", "TAX_VAT_PAYABLE")}})
            reason = f"Vente domestique — TVA {res['rate']*100:.1f}% (taux {cat})."
    else:  # input / both
        hint = ctx.get("recoverability_hint")
        if hint == "business_taxable":
            rec = {"mode": "full", "reason": "Achat professionnel taxable : impôt préalable déductible."}
        elif hint == "excluded":
            rec = {"mode": "none", "reason": "Lié à une activité exclue : TVA non déductible (portée en charge)."}
        elif hint == "mixed":
            mr = ctx.get("mixed_rate")
            if mr is None:
                rec = {"mode": "needs_review", "reason": "Usage mixte : clé de répartition à préciser."}
                needs_review = True
            else:
                rec = {"mode": "partial", "rate": float(mr), "reason": f"Usage mixte : {float(mr)*100:.0f}% déductible."}
        else:
            rec = {"mode": "needs_review", "reason": "Information fiscale insuffisante : récupérabilité à confirmer."}
            needs_review = True  # NEVER invent a deduction (adjustment 2)

        if kind == "services_from_abroad":
            liable = True
            if vat_status != "taxable":
                # Non-registered recipient: CHF 10'000/year threshold applies (adjustment 1).
                ytd = float(ctx.get("acquisition_ytd") or 0)
                liable = ytd >= 10000.0
            res.update({"tax_treatment": "reverse_charge_acquisition", "tax_code": "CH_VAT_ACQ",
                        "rate": rate_for("standard"), "side": "both",
                        "reporting_mapping": {"acquisition_tax_field": "380", "input_tax_field": "400"},
                        "account_roles": {"acquisition_vat_role": roles.get("acquisition_vat_role", "TAX_VAT_ACQUISITION"),
                                          "input_vat_role": roles.get("input_vat_role", "TAX_RECOVERABLE"),
                                          "non_recoverable_target": roles.get("non_recoverable_target", "EXPENSE")},
                        "acquisition_liable": liable,
                        "recoverability": rec if liable else {"mode": "none", "reason": "Non assujetti sous le seuil CHF 10'000 : pas d'impôt sur les acquisitions."}})
            if vat_status == "taxable":
                reason = "Acquisition de prestations de l'étranger (auto-liquidation) — assujetti CH : imposable."
            elif liable:
                reason = "Acquisition de prestations de l'étranger — non assujetti, seuil CHF 10000 franchi : imposable."
            else:
                reason = "Acquisition de prestations de l'étranger — non assujetti, sous le seuil CHF 10000 : non imposable."
        elif kind == "import_goods":
            res.update({"tax_treatment": "import_goods", "tax_code": "CH_VAT_IMPORT",
                        "rate": rate_for(ctx.get("rate_category") or "standard"),
                        "reporting_mapping": {"input_tax_field": "400"},
                        "account_roles": {"input_vat_role": roles.get("input_vat_role", "TAX_RECOVERABLE"),
                                          "non_recoverable_target": roles.get("non_recoverable_target", "EXPENSE")},
                        "recoverability": rec})
            reason = "Importation de biens : TVA à l'importation (justificatif OFDF)."
        else:  # domestic purchase
            cat = ctx.get("rate_category") or "standard"
            res.update({"tax_treatment": "standard_rated" if cat == "standard" else f"{cat}_rated",
                        "tax_code": {"standard": "CH_VAT_STD", "reduced": "CH_VAT_REDUCED", "accommodation": "CH_VAT_ACC"}[cat],
                        "rate": rate_for(cat),
                        "reporting_mapping": {"input_tax_field": "400"},
                        "account_roles": {"input_vat_role": roles.get("input_vat_role", "TAX_RECOVERABLE"),
                                          "non_recoverable_target": roles.get("non_recoverable_target", "EXPENSE")},
                        "recoverability": rec})
            reason = f"Achat domestique — impôt préalable {res['rate']*100:.1f}%."

    # VAT FX (adjustment 3) — separate from transaction/closing FX.
    res["vat_fx"] = await _vat_fx(db, ws, co, ctx, tax_date)
    if res.get("vat_fx") and res["vat_fx"].get("needs_review"):
        needs_review = True
    # Rounding snapshot from the canonical CH.1 domain.
    try:
        rnd = await resolve(db, ws, co, domain="rounding", context={}, as_of=as_of)
        res["rounding"] = rnd.get("result")
    except PolicyError:
        res["rounding"] = None

    dec = _decision("vat_ch", policy["jurisdiction"], policy, (policy.get("rules") or [{}])[0],
                    res, reason, context, as_of, sources=policy.get("sources", []),
                    extra={"needs_review": needs_review})
    return dec


async def _handle_document_ai(db, ws, co, context, as_of, candidates):
    """Absorb existing jurisdiction.document_ai_policy (optional domain)."""
    from . import jurisdiction
    pol = await jurisdiction.document_ai_policy(db, ws, co)
    result = {"region_required": pol.get("region_required") or [],
              "allow_emergent_universal_key": pol.get("allow_emergent_universal_key", False)}
    reason = ("Régions autorisées : " + (", ".join(result["region_required"]) or "aucune restriction")
              + " ; clé Emergent interdite." if not result["allow_emergent_universal_key"]
              else "Politique IA documentaire.")
    return _decision("document_ai", pol.get("country") or candidates[0], None, None,
                     result, reason, context, as_of, sources=[])


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def _company_jurisdiction(db, ws, co, context):
    ctx = dict(context or {})
    if ctx.get("country"):
        return ctx.get("country"), ctx.get("canton") or ctx.get("subdivision") or ctx.get("province")
    from . import jurisdiction
    prof = await jurisdiction.get_compliance_profile(db, ws, co)
    return (prof.get("country") or None), (ctx.get("subdivision"))


async def resolve(db, ws, co, *, domain, context=None, as_of):
    """Canonical decision. Deterministic, fail-closed, cacheable. `as_of` mandatory."""
    if not as_of:
        raise PolicyError("as_of_required", "as_of (date d'effet) est obligatoire.")
    if domain not in DOMAIN_STRATEGY:
        raise PolicyError("unknown_domain", f"Domaine inconnu : {domain}.")
    context = context or {}
    country, subdivision = await _company_jurisdiction(db, ws, co, context)
    candidates = jurisdiction_candidates(country, subdivision)
    ihash = _inputs_hash(domain, {**context, "_j": candidates}, as_of)
    ckey = f"{ws}:{co}:{ihash}"
    if ckey in _CACHE:
        return _CACHE[ckey]["decision"]

    if domain == "vat":
        decision = await _handle_vat(db, ws, co, context, as_of, candidates)
    elif domain == "vat_ch":
        decision = await _handle_vat_ch(db, ws, co, context, as_of, candidates)
    elif domain == "document_ai":
        decision = await _handle_document_ai(db, ws, co, context, as_of, candidates)
    else:
        decision = await _handle_policy_doc_domain(db, ws, co, domain, context, as_of, candidates)

    if decision is None:
        strategy = DOMAIN_STRATEGY[domain]
        if strategy == "fallback_allowed" and domain in CORE_FALLBACK:
            fb = CORE_FALLBACK[domain]
            decision = _decision(domain, "*", None, None, fb["result"], fb["reason"],
                                 context, as_of, sources=[], extra={"fallback": True})
        elif strategy == "optional":
            decision = _decision(domain, "*", None, None, None,
                                 "Fonctionnalité indisponible : aucune politique applicable.",
                                 context, as_of, sources=[], extra={"available": False})
        else:  # required
            raise PolicyError("policy_unavailable",
                              f"Décision {domain} obligatoire mais aucune politique applicable "
                              f"(pays={country}, date={as_of}).")
    _CACHE[ckey] = {"decision": decision, "domain": domain,
                    "jurisdiction": (country or "*"), "as_of": as_of}
    return decision


def snapshot(decision):
    """Immutable snapshot to freeze on a transaction. Stores the RESOLVED RESULT so
    explain() never needs a fresh resolution."""
    return {k: decision.get(k) for k in (
        "domain", "jurisdiction", "policy_id", "policy_version", "effective_from",
        "effective_to", "rule_id", "result", "reason", "sources", "engine_version",
        "inputs_hash", "decision_id", "resolved_at", "as_of")}


def explain(snap):
    """« Pourquoi ? » built PURELY from a historical snapshot — no current resolution."""
    if not snap:
        return None
    return {"statement": snap.get("reason"), "result": snap.get("result"),
            "policy_id": snap.get("policy_id"), "policy_version": snap.get("policy_version"),
            "effective_from": snap.get("effective_from"), "effective_to": snap.get("effective_to"),
            "rule_id": snap.get("rule_id"), "sources": snap.get("sources") or [],
            "engine_version": snap.get("engine_version"), "as_of": snap.get("as_of"),
            "decision_id": snap.get("decision_id")}


async def list_effective(db, ws, co, *, domain, jurisdiction=None, as_of=None):
    as_of = as_of or _now()[:10]
    cands = [jurisdiction] if jurisdiction else jurisdiction_candidates(
        *(await _company_jurisdiction(db, ws, co, {})))
    q = {"domain": domain, "status": "published", "jurisdiction": {"$in": cands},
         "$or": [{"scope": "system"}, {"scope": "company", "workspace_id": ws, "company_id": co}]}
    docs = await db.jurisdiction_policies.find(q).sort("effective_from", -1).to_list(200)
    return [{"policy_id": d["policy_id"], "policy_version": d["policy_version"],
             "jurisdiction": d["jurisdiction"], "effective_from": d["effective_from"],
             "effective_to": d.get("effective_to"), "priority": d["priority"],
             "overridability": d.get("overridability"), "sources": d.get("sources", [])} for d in docs]


# --------------------------------------------------------------------------- #
# Override guard (declared overridability enforced regardless of admin/manage)
# --------------------------------------------------------------------------- #
def assert_overridable(decision, *, field=None):
    ov = (decision or {}).get("overridability", "non_overrideable")
    if ov == "non_overrideable":
        raise PolicyError("not_overridable",
                          "Règle réglementaire non modifiable : override interdit (même pour un administrateur).")
    return True


# --------------------------------------------------------------------------- #
# Seed default system policies (no NEW business rules; wraps/expresses existing).
# --------------------------------------------------------------------------- #
async def ensure_seed(db):
    async def seed(domain, jurisdiction, rules, sources, overridability, effective_from="2000-01-01",
                   key="base", priority=100):
        pid = _pid("system", domain, jurisdiction, key)
        if await db.jurisdiction_policies.find_one({"policy_id": pid, "status": "published",
                                                    "effective_from": effective_from}):
            return
        await publish_policy(db, domain=domain, jurisdiction=jurisdiction, rules=rules,
                             sources=sources, effective_from=effective_from, scope="system",
                             key=key, overridability=overridability, priority=priority)

    # fx_freshness (R4 authority; same default as A4.6 — 7 days). fallback also exists.
    await seed("fx_freshness", "*", [{"rule_id": "default", "match": {},
               "result": {"stale_days": 7},
               "reason": "Un taux plus ancien que 7 jours avant la date d'analyse est jugé douteux."}],
               [], "overrideable")
    # monetary_classification (R4 authority; mirrors A4.6 classify_ap_position).
    await seed("monetary_classification", "*", [
        {"rule_id": "invoice", "match": {"position_type": "invoice"},
         "result": {"classification": "monetary"},
         "reason": "Dette fournisseur ouverte réglée en trésorerie (poste monétaire)."},
        {"rule_id": "credit_note", "match": {"position_type": "credit_note"},
         "result": {"classification": "monetary"},
         "reason": "Note de crédit fournisseur ouverte (poste monétaire)."},
        {"rule_id": "default", "match": {},
         "result": {"classification": "non_monetary"},
         "reason": "Poste non monétaire — exclu de la réévaluation."}], [], "overrideable")
    # rounding (fallback_allowed): NO '*' policy is seeded — the explicit Core
    # fallback (2 decimals) is the canonical default; jurisdictions may publish overrides.
    # vat metadata wrapper (sources only; rates delegated to sales_tax_codes).
    ch_sources = [{"authority": "AFC/ESTV", "title": "Taux de la TVA (Suisse)",
                   "doc_ref": "vat-rates-switzerland", "url": "https://www.estv.admin.ch/en/vat-rates-switzerland",
                   "published_version": "2026", "published_date": None, "effective_from": "2024-01-01",
                   "verified_at": "2026-06", "archived_hash": None}]
    await seed("vat", "CH", [{"rule_id": "delegate", "match": {},
               "result": {"delegated_to": "sales_tax_codes"},
               "reason": "Taux TVA suisses issus du référentiel versionné des codes de taxe."}],
               ch_sources, "non_overrideable")

    # vat_ch — structured Swiss VAT authority (rates delegated for parity; adds
    # treatment/recoverability/reporting/roles). Two versions for reproducibility.
    common = {"reporting": {}, "legal_basis": ["MWSTG art. 18, 21, 23, 25, 28-30, 45-49"],
              "account_roles": {"output_vat_role": "TAX_VAT_PAYABLE", "input_vat_role": "TAX_RECOVERABLE",
                                "acquisition_vat_role": "TAX_VAT_ACQUISITION", "non_recoverable_target": "EXPENSE"}}
    await seed("vat_ch", "CH", [{"rule_id": "ch_v1", "match": {},
               "result": {**common, "rates": {"standard": 0.077, "reduced": 0.025, "accommodation": 0.037}},
               "reason": "TVA CH taux 2018-2023."}], ch_sources, "non_overrideable",
               effective_from="2018-01-01")
    await seed("vat_ch", "CH", [{"rule_id": "ch_v2", "match": {},
               "result": {**common, "rates": {"standard": 0.081, "reduced": 0.026, "accommodation": 0.038}},
               "reason": "TVA CH taux dès 2024."}], ch_sources, "non_overrideable",
               effective_from="2024-01-01")


async def ensure_indexes(db):
    await db.jurisdiction_policies.create_index(
        [("domain", 1), ("jurisdiction", 1), ("status", 1), ("effective_from", 1)],
        name="idx_policy_resolve")
    await db.jurisdiction_policies.create_index(
        [("policy_id", 1), ("policy_version", 1)], name="idx_policy_version")
    await db.jurisdiction_policies.create_index(
        [("scope", 1), ("workspace_id", 1), ("company_id", 1)], name="idx_policy_scope")
