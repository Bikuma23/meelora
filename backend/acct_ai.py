"""Routeur IA (Phase 3) — Comptabilité. Extrait de server.py sans changement de logique.
Les helpers partagés (db, rapports, KPI, MONTHS_FR, auth) sont injectés via init() par server.py."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import ai_service

router = APIRouter()

# --- Références partagées, liées au démarrage par server.init ---
db = None
log_action = None
_acct_report = None
_kpi_data = None
_bilan_sommaire_data = None
_pnl_figures = None
_cashflow_data = None
_pkey = None
_add_months = None
MONTHS_FR = None
_get_current_user = None


def init(**kw):
    global db, log_action, _acct_report, _kpi_data, _bilan_sommaire_data
    global _pnl_figures, _cashflow_data, _pkey, _add_months, MONTHS_FR, _get_current_user
    db = kw["db"]
    log_action = kw["log_action"]
    _acct_report = kw["_acct_report"]
    _kpi_data = kw["_kpi_data"]
    _bilan_sommaire_data = kw["_bilan_sommaire_data"]
    _pnl_figures = kw["_pnl_figures"]
    _cashflow_data = kw.get("_cashflow_data")
    _pkey = kw["_pkey"]
    _add_months = kw["_add_months"]
    MONTHS_FR = kw["MONTHS_FR"]
    _get_current_user = kw["get_current_user"]


async def _get_user(request: Request):
    return await _get_current_user(request)


async def _get_admin(request: Request):
    user = await _get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user



AI_SECRET_FIELDS = ("openai_api_key", "azure_api_key")

async def _ai_config():
    return await db.acct_ai_config.find_one({"_id": "config"}) or {}

def _ai_config_public(cfg):
    st = ai_service.ai_status(cfg)
    return {
        "enabled": bool(cfg.get("enabled")),
        "provider": cfg.get("provider") or "emergent",
        "model": cfg.get("model") or ai_service.DEFAULT_MODEL,
        "azure_endpoint": cfg.get("azure_endpoint") or "",
        "azure_deployment": cfg.get("azure_deployment") or "",
        "azure_api_version": cfg.get("azure_api_version") or "2024-08-01-preview",
        "has_openai_key": bool(cfg.get("openai_api_key")),
        "has_azure_key": bool(cfg.get("azure_api_key")),
        "variance_threshold_amount": cfg.get("variance_threshold_amount", 10000),
        "variance_threshold_pct": cfg.get("variance_threshold_pct", 10),
        "anomaly_sensitivity": cfg.get("anomaly_sensitivity", 2.5),
        "configured": st["configured"],
    }

class AIConfigBody(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    openai_api_key: Optional[str] = None
    azure_endpoint: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_deployment: Optional[str] = None
    azure_api_version: Optional[str] = None
    variance_threshold_amount: Optional[float] = None
    variance_threshold_pct: Optional[float] = None
    anomaly_sensitivity: Optional[float] = None

@router.get("/acct/ai/status")
async def acct_ai_status(user: dict = Depends(_get_user)):
    return ai_service.ai_status(await _ai_config())

@router.get("/acct/ai/config")
async def acct_ai_get_config(user: dict = Depends(_get_admin)):
    return _ai_config_public(await _ai_config())

@router.put("/acct/ai/config")
async def acct_ai_put_config(body: AIConfigBody, user: dict = Depends(_get_admin)):
    provided = body.dict(exclude_unset=True)
    sets = {}
    for k, v in provided.items():
        if k in AI_SECRET_FIELDS and (v is None or v == ""):
            continue  # ne pas écraser un secret existant avec du vide
        sets[k] = v
    if sets:
        sets["updated_by"] = user["email"]; sets["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.acct_ai_config.update_one({"_id": "config"}, {"$set": sets}, upsert=True)
        await log_action(user, "Modifier", "Comptabilité", "Configuration IA mise à jour")
    return _ai_config_public(await _ai_config())

@router.delete("/acct/ai/config/key")
async def acct_ai_clear_keys(user: dict = Depends(_get_admin)):
    await db.acct_ai_config.update_one({"_id": "config"}, {"$set": {"openai_api_key": "", "azure_api_key": "", "enabled": False}}, upsert=True)
    await log_action(user, "Modifier", "Comptabilité", "Clés IA effacées")
    return _ai_config_public(await _ai_config())

# ---- 1. Analyse de variance ----
# Scénarios budgétaires : champs P&L correspondants (mois + cumulatif).
VARIANCE_SCENARIOS = {
    "ca":   {"label": "Budget CA",     "bud": "bud_ca",   "ecart": "ecart_ca",   "ecart_cum": "ecart_ca_cum"},
    "rev1": {"label": "Budget Rév-1",  "bud": "bud_rev1", "ecart": "ecart_rev1", "ecart_cum": "ecart_rev1_cum"},
    "rev2": {"label": "Budget Rév-2",  "bud": "bud_rev2", "ecart": "ecart_rev2", "ecart_cum": "ecart_rev2_cum"},
}


def _scenario_has_data(pnl, scen):
    """Un scénario a des données si au moins une ligne du P&L a un budget non nul."""
    f = VARIANCE_SCENARIOS[scen]
    for ln in pnl["lines"]:
        if ln.get("kind") not in ("data", "total"):
            continue
        if abs(ln["values"].get(f["bud"]) or 0) > 0.005:
            return True
    return False


async def _ai_variance_ctx(year, month, amt_thr, pct_thr, scenario="ca"):
    f = VARIANCE_SCENARIOS.get(scenario, VARIANCE_SCENARIOS["ca"])
    pnl = await _acct_report(year, month, "pnl")
    rows = []
    for ln in pnl["lines"]:
        if ln.get("kind") not in ("data", "total"):
            continue
        v = ln["values"]
        ec = v.get(f["ecart"]); bud = v.get(f["bud"])
        if ec is None:
            continue
        pct = (abs(ec) / abs(bud) * 100) if bud else None
        if abs(ec) >= amt_thr or (pct is not None and pct >= pct_thr):
            rows.append({"poste": ln["label"], "account": ln.get("account"),
                         "reel": round(v.get("reel") or 0, 2), "budget": round(bud or 0, 2),
                         "ecart": round(ec, 2), "ecart_pct": round(pct, 1) if pct is not None else None,
                         "ecart_ytd": round(v.get(f["ecart_cum"]) or 0, 2)})
    rows.sort(key=lambda r: abs(r["ecart"]), reverse=True)
    return rows[:25]

def _iqr_outlier_indices(txns):
    """Détection d'aberrations par écart interquartile (déterministe, sans IA)."""
    amts = sorted((t.get("amount") or 0) for t in txns)
    n = len(amts)
    if n < 4:
        return set()
    def pct(p):
        idx = p * (n - 1); lo = int(idx); frac = idx - lo
        return amts[lo] + (amts[min(lo + 1, n - 1)] - amts[lo]) * frac
    q1, q3 = pct(0.25), pct(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return set()
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {i for i, t in enumerate(txns) if (t.get("amount") or 0) < lo or (t.get("amount") or 0) > hi}

async def _variance_txns(year, month, rows, max_rows=3, max_txn=25, summarize_threshold=200):
    """Filtrage déterministe des transactions avant transmission à l'IA.
    Ne renvoie QUE les transactions des comptes en écart majeur, priorisées par
    aberration statistique puis par montant. Résume si > summarize_threshold lignes."""
    pk = _pkey(year, month)
    led = await db.acct_ledger.find_one({"_id": pk})
    if not led or not led.get("transactions"):
        return None
    doc = await db.acct_account_map.find_one({"_id": "current"})
    amap = (doc.get("map", {}) if doc else {})
    rev = {}
    for src, tgt in amap.items():
        rev.setdefault(int(tgt), set()).add(int(src))
    by_acct = {}
    for t in led["transactions"]:
        by_acct.setdefault(t["account"], []).append(t)
    result = {}
    for r in [r for r in rows if r.get("account") is not None][:max_rows]:
        acct = r.get("account")
        srcset = {int(acct)} | rev.get(int(acct), set())
        rel = []
        for s in srcset:
            rel.extend(by_acct.get(s, []))
        if not rel:
            continue
        if len(rel) > summarize_threshold:
            groups = {}
            for t in rel:
                key = (t.get("description") or "—").strip().lower()[:60]
                g = groups.setdefault(key, {"description": (t.get("description") or "—"), "count": 0, "total": 0.0})
                g["count"] += 1; g["total"] = round(g["total"] + (t.get("amount") or 0), 2)
            summ = sorted(groups.values(), key=lambda x: abs(x["total"]), reverse=True)[:20]
            result[r["poste"]] = {"mode": "resume", "n_transactions": len(rel), "groupes": summ}
        else:
            outset = _iqr_outlier_indices(rel)
            enriched = [{"date": t.get("date"), "description": t.get("description"),
                         "montant": t.get("amount"), "inhabituelle": (i in outset)} for i, t in enumerate(rel)]
            enriched.sort(key=lambda t: (not t["inhabituelle"], -abs(t["montant"] or 0)))
            result[r["poste"]] = {"mode": "detail", "n_transactions": len(rel), "transactions": enriched[:max_txn]}
    return result or None

async def _ai_variance_compare_ctx(year, month, amt_thr, pct_thr, active):
    """Contexte multi-scénarios : pour chaque poste significatif, écarts du réel face à
    chaque scénario disponible (CA, Rév-1, Rév-2). 'active' = liste des scénarios ayant des données."""
    pnl = await _acct_report(year, month, "pnl")
    rows = []
    for ln in pnl["lines"]:
        if ln.get("kind") not in ("data", "total"):
            continue
        v = ln["values"]
        scen_data = {}
        max_ec = 0.0
        for s in active:
            f = VARIANCE_SCENARIOS[s]
            ec = v.get(f["ecart"]); bud = v.get(f["bud"])
            if ec is None:
                continue
            pct = (abs(ec) / abs(bud) * 100) if bud else None
            scen_data[f["label"]] = {"budget": round(bud or 0, 2), "ecart": round(ec, 2),
                                     "ecart_pct": round(pct, 1) if pct is not None else None}
            max_ec = max(max_ec, abs(ec))
        if not scen_data:
            continue
        keep = any((abs(d["ecart"]) >= amt_thr) or (d["ecart_pct"] is not None and d["ecart_pct"] >= pct_thr) for d in scen_data.values())
        if not keep:
            continue
        rows.append({"poste": ln["label"], "account": ln.get("account"),
                     "reel": round(v.get("reel") or 0, 2), "_max": max_ec, "scenarios": scen_data})
    rows.sort(key=lambda r: r["_max"], reverse=True)
    for r in rows:
        r.pop("_max", None)
    return rows[:25]


@router.get("/acct/ai/variance/scenarios")
async def acct_ai_variance_scenarios(year: int, month: int, user: dict = Depends(_get_user)):
    """Indique quels scénarios budgétaires disposent de données pour la période (pour l'UI)."""
    pnl = await _acct_report(year, month, "pnl")
    return {"scenarios": {s: _scenario_has_data(pnl, s) for s in VARIANCE_SCENARIOS}}


@router.post("/acct/ai/variance")
async def acct_ai_variance(year: int, month: int, scenario: str = "ca", user: dict = Depends(_get_user)):
    cfg = await _ai_config()
    amt = float(cfg.get("variance_threshold_amount", 10000)); pct = float(cfg.get("variance_threshold_pct", 10))

    if scenario == "compare":
        pnl = await _acct_report(year, month, "pnl")
        active = [s for s in VARIANCE_SCENARIOS if _scenario_has_data(pnl, s)]
        if len(active) < 2:
            return {"available": True, "commentary": None, "rows": [], "empty": True, "scenario": scenario,
                    "reason_empty": "La comparaison nécessite au moins deux scénarios budgétaires avec des données."}
        rows = await _ai_variance_compare_ctx(year, month, amt, pct, active)
        if not rows:
            return {"available": True, "commentary": None, "rows": [], "empty": True, "scenario": scenario}
        detail = await _variance_txns(year, month, rows)
        labels = ", ".join(VARIANCE_SCENARIOS[s]["label"] for s in active)
        system = ("Tu es un analyste financier. Compare le réel face à plusieurs révisions budgétaires (" + labels + "). "
                  "Commente UNIQUEMENT à partir des données fournies, n'invente aucun chiffre. Rédige en français, 4 à 7 phrases concises. "
                  "Mets en évidence : (1) les postes où l'écart se creuse ou se réduit d'une révision à l'autre (dérive budgétaire), "
                  "(2) les écarts majeurs communs à tous les scénarios, (3) le sens (dépassement/économie). Priorise les postes les plus significatifs.")
        if detail:
            system += (" Des transactions détaillées (grand livre) filtrées par le système sont fournies pour les postes en plus gros écart ; "
                       "utilise-les pour signaler une transaction ponctuelle inhabituelle (« inhabituelle=true ») plutôt qu'une dérive générale. Échantillon ciblé, non exhaustif.")
        import json as _json
        user_p = (f"Période {MONTHS_FR[month-1]} {year}. Comparaison multi-scénarios (réel vs {labels}). "
                  f"Seuils: {amt}$ ou {pct}%. Écarts par poste et par scénario:\n{_json.dumps(rows, ensure_ascii=False)}")
        if detail:
            user_p += "\n\nTransactions détaillées ciblées (filtrage déterministe, non exhaustif) par poste en écart:\n" + _json.dumps(detail, ensure_ascii=False)
        try:
            txt = await ai_service.ai_complete(cfg, system, user_p, user["email"], max_tokens=700)
            return {"available": True, "commentary": txt, "rows": rows, "ledger_used": bool(detail), "detail": detail or {}, "scenario": scenario, "compared": active}
        except ai_service.AINotConfigured as e:
            return {"available": False, "reason": str(e), "rows": rows, "scenario": scenario}
        except ai_service.AIError as e:
            return {"available": False, "reason": str(e), "rows": rows, "scenario": scenario}

    if scenario not in VARIANCE_SCENARIOS:
        scenario = "ca"
    scen = VARIANCE_SCENARIOS[scenario]
    rows = await _ai_variance_ctx(year, month, amt, pct, scenario)
    if not rows:
        return {"available": True, "commentary": None, "rows": [], "empty": True, "scenario": scenario}
    detail = await _variance_txns(year, month, rows)
    system = ("Tu es un analyste financier. Commente UNIQUEMENT à partir des données d'écarts fournies (réel vs budget). "
              "N'invente aucun chiffre ni contexte. Rédige en français, 3 à 6 phrases concises, en citant les postes et montants les plus significatifs. "
              "Indique le sens de l'écart (dépassement/économie). Ne liste pas tout, priorise les écarts majeurs.")
    if detail:
        system += (" Des transactions détaillées (grand livre) filtrées par le système sont fournies pour les postes en plus gros écart. "
                   "Utilise-les pour préciser si un écart provient d'une transaction ponctuelle inhabituelle (champ « inhabituelle=true ») "
                   "plutôt que d'une dérive générale du compte. Ces transactions sont un échantillon ciblé, pas la liste exhaustive.")
    import json as _json
    user_p = (f"Période {MONTHS_FR[month-1]} {year}. Scénario budgétaire comparé : {scen['label']}. "
              f"Seuils: {amt}$ ou {pct}%. Écarts significatifs (réel vs {scen['label']}):\n{_json.dumps(rows, ensure_ascii=False)}")
    if detail:
        user_p += "\n\nTransactions détaillées ciblées (filtrage déterministe, non exhaustif) par poste en écart:\n" + _json.dumps(detail, ensure_ascii=False)
    try:
        txt = await ai_service.ai_complete(cfg, system, user_p, user["email"], max_tokens=600)
        return {"available": True, "commentary": txt, "rows": rows, "ledger_used": bool(detail), "detail": detail or {}, "scenario": scenario}
    except ai_service.AINotConfigured as e:
        return {"available": False, "reason": str(e), "rows": rows, "scenario": scenario}
    except ai_service.AIError as e:
        return {"available": False, "reason": str(e), "rows": rows, "scenario": scenario}

# ---- 2. Détection d'anomalies (statistique + explication IA) ----
async def _ai_anomalies(year, month, sensitivity):
    pk = _pkey(year, month)
    cur = await db.acct_bv.find_one({"_id": pk})
    if not cur:
        return []
    hist = []
    for k in range(1, 7):
        hy, hm = _add_months(year, month, -k)
        d = await db.acct_bv.find_one({"_id": _pkey(hy, hm)})
        if d:
            hist.append({a["account"]: (a.get("i") or 0.0) for a in d.get("accounts", [])})
    if len(hist) < 3:
        return []
    names = {a["account"]: a.get("name", "") for a in cur.get("accounts", [])}
    out = []
    for a in cur.get("accounts", []):
        acc = a["account"]; val = a.get("i") or 0.0
        series = [h[acc] for h in hist if acc in h]
        if len(series) < 3:
            continue
        mean = sum(series) / len(series)
        var = sum((x - mean) ** 2 for x in series) / len(series)
        std = var ** 0.5
        if std < 1 and abs(val - mean) < 5000:
            continue
        z = (val - mean) / std if std > 0 else (0 if abs(val - mean) < 1 else 99)
        if abs(z) >= sensitivity and abs(val - mean) >= 5000:
            out.append({"account": acc, "name": names.get(acc, ""), "value": round(val, 2),
                        "moyenne": round(mean, 2), "ecart": round(val - mean, 2), "z": round(z, 1)})
    out.sort(key=lambda r: abs(r["z"]), reverse=True)
    return out[:15]

@router.post("/acct/ai/anomalies")
async def acct_ai_anomalies(year: int, month: int, user: dict = Depends(_get_user)):
    cfg = await _ai_config()
    sens = float(cfg.get("anomaly_sensitivity", 2.5))
    anomalies = await _ai_anomalies(year, month, sens)
    result = {"available": True, "anomalies": anomalies, "summary": None}
    if not anomalies:
        return result
    st = ai_service.ai_status(cfg)
    if not st["configured"]:
        result["available"] = False
        result["reason"] = "Fonctionnalité IA non configurée."
        return result
    import json as _json
    system = ("Tu es un contrôleur financier. À partir de la liste d'anomalies statistiques fournie (comptes dont le solde s'écarte fortement de leur moyenne récente), "
              "rédige en français un court paragraphe (2-4 phrases) signalant les cas à vérifier en priorité. N'invente aucun chiffre. Ce sont des signalements non bloquants.")
    user_p = f"Anomalies détectées pour {MONTHS_FR[month-1]} {year} (seuil z={sens}):\n{_json.dumps(anomalies, ensure_ascii=False)}"
    try:
        result["summary"] = await ai_service.ai_complete(cfg, system, user_p, user["email"], max_tokens=400)
    except (ai_service.AINotConfigured, ai_service.AIError):
        pass
    return result

# ---- 3. Chat Q&A ----
async def _cashflow_ctx(year, month):
    """Flux de trésorerie du mois (ouverture = mois précédent -> clôture = mois courant), si disponible."""
    if _cashflow_data is None:
        return None
    oy, om = _add_months(year, month, -1)
    if not await db.acct_bv.find_one({"_id": _pkey(oy, om)}):
        return None
    try:
        cf = await _cashflow_data(oy, om, year, month)
    except Exception:
        return None
    return {
        "periode": f"{cf.get('open_label')} -> {cf.get('close_label')}",
        "benefice_net": cf.get("benefice_net"), "amortissement": cf.get("amortissement"),
        "activites_exploitation": cf.get("exploitation_total"),
        "fonds_de_roulement": cf.get("fdr"),
        "activites_investissement": cf.get("investissement_total"), "detail_investissement": cf.get("investissement"),
        "activites_financement": cf.get("financement_total"), "detail_financement": cf.get("financement"),
        "variation_nette_encaisse": cf.get("variation_nette"),
        "encaisse_ouverture": cf.get("encaisse_ouverture"), "encaisse_cloture": cf.get("encaisse_cloture"),
    }


async def _ai_chat_ctx(year, month):
    import json as _json
    kpi = await _kpi_data(year, month, with_trend=False)
    pnl = await _acct_report(year, month, "pnl_sommaire")
    bil = await _bilan_sommaire_data(year, month)

    def pack_pnl(lines):
        out = []
        for l in lines:
            if l.get("kind") not in ("data", "total", "header"):
                continue
            v = l.get("values", {})
            row = {"poste": l["label"], "reel": v.get("reel"), "cumulatif": v.get("cumulatif")}
            if v.get("bud_ca") is not None:
                row["budget_ca"] = v.get("bud_ca")
            out.append(row)
        return out

    def pack_bilan(side):
        # inclut les lignes détaillées (data) ET les totaux/entêtes
        return [{"poste": l["label"], "valeur": l["value"]} for l in side if l.get("label")]

    trend = []
    for k in range(5, -1, -1):
        hy, hm = _add_months(year, month, -k)
        if await db.acct_bv.find_one({"_id": _pkey(hy, hm)}):
            try:
                p = _pnl_figures(await _acct_report(hy, hm, "pnl_sommaire"))
                trend.append({"mois": f"{MONTHS_FR[hm-1]} {hy}", "ventes": p["sales"].get("reel"), "cogs": p["cogs"].get("reel"), "charges": p["charges"].get("reel")})
            except Exception:
                pass
    cashflow = await _cashflow_ctx(year, month)
    ctx = {
        "periode": f"{MONTHS_FR[month-1]} {year}",
        "kpi": {"DSO_jours": kpi["dso"]["value"], "DPO_jours": kpi["dpo"]["value"], "FDR": kpi["fdr"]["value"], "BFR": kpi["fdr"].get("bfr", {}).get("value")},
        "etat_resultats": pack_pnl(pnl["lines"]),
        "bilan_actif": pack_bilan(bil["actif"]),
        "bilan_passif": pack_bilan(bil["passif"]),
        "bilan_total_actif": bil.get("total_actif"),
        "bilan_total_passif": bil.get("total_passif"),
        "flux_tresorerie": cashflow,
        "tendance_6_mois": trend,
    }
    return _json.dumps(ctx, ensure_ascii=False)

class AIChatBody(BaseModel):
    session_id: str
    question: str
    year: int
    month: int

@router.post("/acct/ai/chat")
async def acct_ai_chat(body: AIChatBody, user: dict = Depends(_get_user)):
    cfg = await _ai_config()
    st = ai_service.ai_status(cfg)
    if not st["configured"]:
        return {"available": False, "reason": "Fonctionnalité IA non configurée."}
    ctx = await _ai_chat_ctx(body.year, body.month)
    system = ("Tu es l'assistant financier du module Comptabilité. Réponds en français en t'appuyant sur les données JSON fournies "
              "(bilan détaillé actif/passif, état des résultats avec budget, flux de trésorerie, KPI, tendance 6 mois). "
              "Les libellés du contexte peuvent différer légèrement de la question : rapproche les termes équivalents "
              "(ex. « créances clients » ≈ « comptes clients / débiteurs », « encaisse » ≈ « trésorerie / caisse / banque », "
              "« fournisseurs » ≈ « comptes fournisseurs / créditeurs »). Cite le libellé exact du contexte et le montant. "
              "N'invente JAMAIS de chiffres. Ne réponds « information non disponible » QUE si, après avoir cherché tous les libellés équivalents, "
              "la donnée est réellement absente du contexte. Sois concis et factuel.")
    user_p = f"Contexte (données réelles du module, période {MONTHS_FR[body.month-1]} {body.year}):\n{ctx}\n\nQuestion: {body.question}"
    try:
        answer = await ai_service.ai_complete(cfg, system, user_p, user["email"], max_tokens=700)
    except ai_service.AINotConfigured as e:
        return {"available": False, "reason": str(e)}
    except ai_service.AIError as e:
        return {"available": False, "reason": f"Erreur de connexion au service IA : {e}. Vérifiez la configuration de l'assistant IA."}
    now = datetime.now(timezone.utc).isoformat()
    await db.acct_ai_chat.insert_one({"session_id": body.session_id, "user": user["email"], "q": body.question, "a": answer, "at": now})
    return {"available": True, "answer": answer}

@router.get("/acct/ai/chat/history")
async def acct_ai_chat_history(session_id: str, user: dict = Depends(_get_user)):
    docs = await db.acct_ai_chat.find({"session_id": session_id}).sort("at", 1).to_list(50)
    return [{"q": d["q"], "a": d["a"], "at": d.get("at")} for d in docs]

# ---- 4. Suggestion de mapping ----
class AISuggestBody(BaseModel):
    account: int
    name: str

@router.post("/acct/ai/suggest-mapping")
async def acct_ai_suggest_mapping(body: AISuggestBody, user: dict = Depends(_get_user)):
    cfg = await _ai_config()
    st = ai_service.ai_status(cfg)
    if not st["configured"]:
        return {"available": False, "reason": "Fonctionnalité IA non configurée."}
    tmpl = await db.acct_template.find_one({"_id": "current"}) or {}
    names = tmpl.get("account_names", {})
    candidates = [{"account": a, "name": names.get(str(a), "")} for a in tmpl.get("accounts", [])][:450]
    import json as _json
    system = ("Tu aides à classer un nouveau compte comptable. À partir du nom et du numéro du nouveau compte et de la liste des comptes existants du modèle, "
              "propose le compte existant le plus pertinent auquel le regrouper. Réponds STRICTEMENT en JSON: {\"account\": <numero>, \"name\": \"<nom>\", \"raison\": \"<courte justification>\"}. "
              "Si aucun compte ne convient clairement, mets account à null.")
    user_p = f"Nouveau compte: {body.account} — {body.name}\nComptes existants:\n{_json.dumps(candidates, ensure_ascii=False)}"
    try:
        raw = await ai_service.ai_complete(cfg, system, user_p, user["email"], max_tokens=300)
    except ai_service.AINotConfigured as e:
        return {"available": False, "reason": str(e)}
    except ai_service.AIError as e:
        return {"available": False, "reason": str(e)}
    import re
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        parsed = _json.loads(m.group(0)) if m else {}
    except Exception:
        parsed = {}
    return {"available": True, "suggestion": parsed, "raw": raw}
