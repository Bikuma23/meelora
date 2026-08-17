"""Central, extensible Company-Home registry.

Each module DECLARES the KPIs / quick actions / recent activity / informational
items it exposes; the Home page never imports a module directly. Adding a new
module later only requires registering a contributor here — the Home page then
surfaces its contributions automatically once the module is entitled, enabled
for the company and the user has the required access. A contribution from a
module the user cannot access is never computed nor returned.
"""
from datetime import datetime, timezone

from ..access.effective_access import resolve_effective_access

# module_code -> async builder(ctx) -> {kpis, quick_actions, recent_activity, informational_items}
REGISTRY = {}


def register(module_code):
    def deco(fn):
        REGISTRY[module_code] = fn
        return fn
    return deco


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(v):
    return round(float(v or 0), 2)


class HomeContext:
    def __init__(self, db, workspace_id, company, user, module_codes):
        self.db = db
        self.ws = workspace_id
        self.company = company
        self.cid = company["id"]
        self.user = user
        self.module_codes = set(module_codes)
        self.functional = company.get("functional_currency") or company.get("currency") or ""
        self.today = _now()[:10]

    async def can(self, module, level="read", permission=None):
        r = await resolve_effective_access(self.db, self.user, workspace_id=self.ws,
                                           company_id=self.cid, module=module,
                                           required_level=level, permission=permission)
        return bool(r.get("allowed"))


async def build_home_payload(db, workspace_id, company, user, module_codes):
    """Aggregate authorised contributions into the normalised Home contract."""
    ctx = HomeContext(db, workspace_id, company, user, module_codes)
    kpis, quick_actions, recent, info = [], [], [], []
    for code in module_codes:
        fn = REGISTRY.get(code)
        if not fn:
            continue
        # Module-level read access is the minimum bar; contributors further gate
        # individual items by permission/level.
        if not await ctx.can(code, "read"):
            continue
        try:
            contrib = await fn(ctx) or {}
        except Exception:
            contrib = {}
        kpis += contrib.get("kpis", [])
        quick_actions += contrib.get("quick_actions", [])
        recent += contrib.get("recent_activity", [])
        info += contrib.get("informational_items", [])
    # Home stays a welcome page: keep the ~5 highest-priority KPIs; never pad with
    # empty cards. The grid reflows to the real count.
    kpis.sort(key=lambda k: k.get("priority", 100))
    quick_actions.sort(key=lambda q: q.get("priority", 100))
    recent.sort(key=lambda r: r.get("date", ""), reverse=True)
    return {
        "kpis": kpis[:5],
        "quick_actions": quick_actions[:6],
        "recent_activity": recent[:6],
        "informational_items": info[:5],
    }


# --------------------------------------------------------------------------- #
# ACCOUNTING contributor (real AR data — Ventes & Clients).
# When ACCOUNTING is present it OWNS the sales/revenue KPIs; REPORTING must not
# duplicate them.
# --------------------------------------------------------------------------- #
def _fx(d):
    return float((d.get("fx") or {}).get("rate") or 1.0)


@register("ACCOUNTING")
async def _accounting_home(ctx):
    db, ws, co, cur = ctx.db, ctx.ws, ctx.cid, ctx.functional
    as_of = ctx.today
    month, year = as_of[:7], as_of[:4]

    invs = await db.sales_invoices.find({"workspace_id": ws, "company_id": co,
        "status": {"$in": ["posted", "partially_paid", "paid"]}}).to_list(None)
    # 6-month revenue trend + MoM + YTD/last-year.
    from collections import OrderedDict
    months = []
    ref = datetime.fromisoformat(as_of)
    for i in range(5, -1, -1):
        m = (ref.year * 12 + ref.month - 1 - i)
        months.append(f"{m // 12:04d}-{m % 12 + 1:02d}")
    trend = OrderedDict((m, 0.0) for m in months)
    rev_month = rev_prev = rev_ytd = rev_last_year = 0.0
    prev_month = months[-2] if len(months) >= 2 else ""
    for inv in invs:
        net = float(inv.get("subtotal") or 0) * _fx(inv)
        idate = inv.get("issue_date") or ""
        ym = idate[:7]
        if ym in trend:
            trend[ym] += net
        if ym == month:
            rev_month += net
        if ym == prev_month:
            rev_prev += net
        if idate[:4] == year:
            rev_ytd += net
        elif idate[:4] == f"{int(year)-1:04d}":
            rev_last_year += net

    open_invs = await db.sales_invoices.find({"workspace_id": ws, "company_id": co,
        "status": {"$in": ["posted", "partially_paid"]}}).to_list(None)
    open_count = sum(1 for i in open_invs if float(i.get("balance") or 0) > 0.001)
    open_amount = sum(float(i.get("balance") or 0) * _fx(i) for i in open_invs)

    pays = await db.sales_payments.find({"workspace_id": ws, "company_id": co}).to_list(None)
    coll_month = sum(float(p.get("amount") or 0) * _fx(p) for p in pays if (p.get("date") or "")[:7] == month)
    coll_prev = sum(float(p.get("amount") or 0) * _fx(p) for p in pays if (p.get("date") or "")[:7] == prev_month)

    cust_total = await db.sales_customers.count_documents({"workspace_id": ws, "company_id": co, "status": {"$ne": "inactive"}})

    def pct(cur_v, prev_v):
        if not prev_v:
            return None
        return round((cur_v - prev_v) / prev_v * 100, 1)

    kpis = [
        {"module": "ACCOUNTING", "code": "acc.revenue_month", "label": "Chiffre d'affaires (mois)",
         "value": _money(rev_month), "format": "currency", "unit": cur, "priority": 10,
         "comparison": ({"delta_pct": pct(rev_month, rev_prev), "label": "vs mois dernier"} if pct(rev_month, rev_prev) is not None else None),
         "trend": [round(v, 2) for v in trend.values()], "destination": "acct_sales"},
        {"module": "ACCOUNTING", "code": "acc.revenue_ytd", "label": "Chiffre d'affaires (cumulé)",
         "value": _money(rev_ytd), "format": "currency", "unit": cur, "priority": 20,
         "comparison": ({"delta_pct": pct(rev_ytd, rev_last_year), "label": "vs année dernière"} if pct(rev_ytd, rev_last_year) is not None else None),
         "destination": "acct_sales"},
        {"module": "ACCOUNTING", "code": "acc.open_invoices", "label": "Factures ouvertes",
         "value": open_count, "format": "number", "priority": 30,
         "subvalue": {"value": _money(open_amount), "format": "currency", "unit": cur},
         "destination": "acct_sales"},
        {"module": "ACCOUNTING", "code": "acc.collections_month", "label": "Encaissements (mois)",
         "value": _money(coll_month), "format": "currency", "unit": cur, "priority": 40,
         "comparison": ({"delta_pct": pct(coll_month, coll_prev), "label": "vs mois dernier"} if pct(coll_month, coll_prev) is not None else None),
         "destination": "acct_sales"},
        {"module": "ACCOUNTING", "code": "acc.active_customers", "label": "Clients actifs",
         "value": cust_total, "format": "number", "priority": 50, "destination": "acct_sales"},
    ]

    # Quick actions — gated by real capability.
    can_contribute = await ctx.can("ACCOUNTING", "contribute")
    quick_actions = []
    if can_contribute:
        quick_actions.append({"module": "ACCOUNTING", "code": "acc.new_invoice", "label": "Nouvelle facture",
                              "icon": "file-plus", "destination": "acct_sales", "priority": 10})
        quick_actions.append({"module": "ACCOUNTING", "code": "acc.record_payment", "label": "Paiements reçus",
                              "icon": "wallet", "destination": "acct_sales", "priority": 20})
    quick_actions.append({"module": "ACCOUNTING", "code": "acc.customers", "label": "Clients",
                          "icon": "users", "destination": "acct_sales", "priority": 30})
    quick_actions.append({"module": "ACCOUNTING", "code": "acc.reports", "label": "Rapports",
                          "icon": "bar-chart", "destination": "acct_sales", "priority": 40})

    # Recent activity — real AR events.
    recent = []
    cust_names = {}
    for inv in (invs + open_invs):
        cust_names[inv.get("customer_id")] = None
    if cust_names:
        cs = await db.sales_customers.find({"workspace_id": ws, "company_id": co,
                                            "_id": {"$in": list(cust_names.keys())}}).to_list(None)
        cust_names = {c["_id"]: c.get("name") for c in cs}
    for p in pays[-12:]:
        recent.append({"type": "payment", "label": f"Paiement reçu de {cust_names.get(p.get('customer_id')) or ''}".strip(),
                       "date": p.get("date") or "", "amount": _money(float(p.get("amount") or 0)), "currency": p.get("currency"),
                       "tone": "positive", "destination": "acct_sales",
                       "ref_type": "payment", "ref_id": p.get("id") or str(p.get("_id") or "")})
    posted = [i for i in invs if i.get("status") in ("posted", "partially_paid", "paid")]
    for inv in posted[-12:]:
        recent.append({"type": "invoice", "label": f"Facture {inv.get('number') or ''} comptabilisée".strip(),
                       "date": inv.get("issue_date") or "", "amount": _money(float(inv.get("total") or 0)),
                       "currency": inv.get("currency"), "tone": "neutral", "destination": "acct_sales",
                       "ref_type": "invoice", "ref_id": inv.get("id") or str(inv.get("_id") or "")})
    cns = await db.sales_credit_notes.find({"workspace_id": ws, "company_id": co, "status": "posted"}).to_list(None)
    for cn in cns[-6:]:
        recent.append({"type": "credit_note", "label": f"Note de crédit {cn.get('number') or ''} émise".strip(),
                       "date": cn.get("issue_date") or cn.get("created_at", "")[:10], "amount": -_money(float(cn.get("total") or 0)),
                       "currency": cn.get("currency"), "tone": "negative", "destination": "acct_sales",
                       "ref_type": "credit_note", "ref_id": cn.get("id") or str(cn.get("_id") or "")})

    # Informational items — contextual reminders first (dynamic), then truthful config facts.
    info = []
    from datetime import timedelta
    horizon = (datetime.fromisoformat(as_of) + timedelta(days=7)).date().isoformat()
    overdue_list = [i for i in open_invs
                    if float(i.get("balance") or 0) > 0.001 and (i.get("due_date") or i.get("issue_date") or "") < as_of]
    due_soon = [i for i in open_invs
                if float(i.get("balance") or 0) > 0.001 and as_of <= (i.get("due_date") or i.get("issue_date") or "") <= horizon]
    if overdue_list:
        amt = _money(sum(float(i.get("balance") or 0) * _fx(i) for i in overdue_list))
        amt_str = f"{amt:,.2f}".replace(",", "\u00A0").replace(".", ",")
        info.append({"module": "ACCOUNTING", "code": "acc.info_overdue", "tone": "warning",
                     "text": f"{len(overdue_list)} facture(s) échue(s) — {amt_str} {cur} en souffrance. Pensez à envoyer une relance."})
    if due_soon:
        info.append({"module": "ACCOUNTING", "code": "acc.info_due_soon", "tone": "warning",
                     "text": f"{len(due_soon)} facture(s) arrivent à échéance dans les 7 prochains jours."})

    tp = ctx.company.get("tax_profile") or {}
    if ctx.company.get("functional_currency"):
        info.append({"module": "ACCOUNTING", "code": "acc.info_currency",
                     "text": f"La devise fonctionnelle de ce mandat est {ctx.company.get('functional_currency')}."})
    info.append({"module": "ACCOUNTING", "code": "acc.info_tax",
                 "text": "Les taux de taxes sont appliqués automatiquement selon la juridiction de vos clients."})
    info.append({"module": "ACCOUNTING", "code": "acc.info_terms",
                 "text": "Vous pouvez personnaliser les conditions de paiement dans la fiche client."})
    return {"kpis": kpis, "quick_actions": quick_actions, "recent_activity": recent, "informational_items": info}


# --------------------------------------------------------------------------- #
# REPORTING contributor — defers to ACCOUNTING when present (no duplicate KPIs).
# Provides its own summary only for REPORTING-without-ACCOUNTING clients. No fake
# data: returns nothing until a real reporting datasource exists.
# --------------------------------------------------------------------------- #
@register("REPORTING")
async def _reporting_home(ctx):
    if "ACCOUNTING" in ctx.module_codes:
        return {}  # ACCOUNTING owns the integrated reporting KPIs.
    return {}
