"""Financial Core — shared currency / FX primitive (A3 foundation).

P2 had NO exchange-rate primitive (the journal is functional-currency only). This
module introduces the SHARED currency layer so AR (A3) — and later AP — reuse one
FX engine, never a parallel one.

Principles:
  * Rates are stored (``exchange_rates``) with an effective date and a source.
  * A transaction (invoice / payment / credit note) always snapshots the exact
    rate + date + source it used; looking up a *current* rate later can NEVER
    mutate a historical transaction.
  * The canonical journal is always balanced in the company functional currency;
    transaction-currency amounts travel as metadata only.
"""
import uuid
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def money(v) -> float:
    return round(float(v or 0), 2)


async def record_rate(db, workspace_id, company_id, *, from_currency, to_currency,
                      rate, rate_date, source="manual", rate_type="current", reference=None):
    """Record an exchange rate. ``rate_type`` (current|closing) is extensible: a
    closing rate is used first for the A4.6 unrealized FX revaluation; current
    is the default for transaction booking. Non-breaking — legacy rows are
    ``current``. OANDA can later feed either type without touching callers."""
    from_currency, to_currency = from_currency.upper(), to_currency.upper()
    rt = rate_type if rate_type in ("current", "closing") else "current"
    doc = {"_id": f"fx_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "from_currency": from_currency, "to_currency": to_currency,
           "rate": float(rate), "rate_date": rate_date, "source": source,
           "rate_type": rt, "reference": reference, "created_at": _now()}
    await db.exchange_rates.insert_one(doc)
    return doc


async def get_rate_typed(db, workspace_id, company_id, *, from_currency, to_currency, on_date, rate_type):
    """Latest recorded rate of an EXACT ``rate_type`` with rate_date <= on_date
    (direct, else inverse). Returns {rate, rate_date, source, rate_type} or None.
    Rows without an explicit rate_type are treated as 'current' (legacy)."""
    from_currency, to_currency = from_currency.upper(), to_currency.upper()
    if from_currency == to_currency:
        return {"rate": 1.0, "rate_date": on_date, "source": "identity", "rate_type": rate_type}
    if rate_type == "current":
        type_q = {"$or": [{"rate_type": "current"}, {"rate_type": {"$exists": False}}, {"rate_type": None}]}
    else:
        type_q = {"rate_type": rate_type}
    scope = {"workspace_id": workspace_id, "company_id": company_id,
             "rate_date": {"$lte": on_date}, **type_q}
    direct = await db.exchange_rates.find(
        {**scope, "from_currency": from_currency, "to_currency": to_currency}).sort("rate_date", -1).to_list(1)
    if direct:
        d = direct[0]
        return {"rate": d["rate"], "rate_date": d["rate_date"], "source": d.get("source", "stored"), "rate_type": rate_type}
    inv = await db.exchange_rates.find(
        {**scope, "from_currency": to_currency, "to_currency": from_currency}).sort("rate_date", -1).to_list(1)
    if inv and inv[0]["rate"]:
        d = inv[0]
        return {"rate": round(1.0 / d["rate"], 8), "rate_date": d["rate_date"],
                "source": d.get("source", "stored") + ":inverse", "rate_type": rate_type}
    return None


async def get_rate(db, workspace_id, company_id, *, from_currency, to_currency, on_date):
    """Latest recorded rate with rate_date <= on_date (direct, else inverse).
    Returns {rate, rate_date, source} or None. Identity when currencies match."""
    from_currency, to_currency = from_currency.upper(), to_currency.upper()
    if from_currency == to_currency:
        return {"rate": 1.0, "rate_date": on_date, "source": "identity"}
    scope = {"workspace_id": workspace_id, "company_id": company_id, "rate_date": {"$lte": on_date}}
    direct = await db.exchange_rates.find(
        {**scope, "from_currency": from_currency, "to_currency": to_currency}).sort("rate_date", -1).to_list(1)
    if direct:
        d = direct[0]
        return {"rate": d["rate"], "rate_date": d["rate_date"], "source": d.get("source", "stored")}
    inv = await db.exchange_rates.find(
        {**scope, "from_currency": to_currency, "to_currency": from_currency}).sort("rate_date", -1).to_list(1)
    if inv and inv[0]["rate"]:
        d = inv[0]
        return {"rate": round(1.0 / d["rate"], 8), "rate_date": d["rate_date"], "source": d.get("source", "stored") + ":inverse"}
    return None


def convert(amount, rate) -> float:
    return money(float(amount or 0) * float(rate or 0))
