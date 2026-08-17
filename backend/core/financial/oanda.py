"""OANDA v20 REST dated-rate retrieval (server-side only).

Fetches the midpoint daily candle close for a currency pair on a given date via
the official OANDA v20 API — never scrapes oanda.com. Credentials come strictly
from environment variables. When the token is absent the service degrades
gracefully (``available: False``) so the UI never breaks; the manual rate entry
remains usable.
"""
import os
from datetime import date, datetime, timedelta, timezone

import httpx

SOURCE = "OANDA v20 REST API / candles, midpoint close, daily UTC candle"


def is_configured() -> bool:
    return bool(os.environ.get("OANDA_API_TOKEN") and os.environ.get("OANDA_ACCOUNT_ID"))


def _base_url() -> str:
    return (os.environ.get("OANDA_BASE_URL") or "https://api-fxpractice.oanda.com").rstrip("/")


def _instrument(from_currency: str, to_currency: str) -> str:
    return f"{(from_currency or '').upper()}_{(to_currency or '').upper()}"


async def fetch_daily_rate(from_currency: str, to_currency: str, on_date: str) -> dict:
    """Return {available, rate, pair, date, source, retrieved_at, candle_time} or
    {available: False, reason}. Same currency → rate 1.0 without an API call."""
    fc, tc = (from_currency or "").upper(), (to_currency or "").upper()
    if not fc or not tc:
        return {"available": False, "reason": "Paire de devises invalide."}
    if fc == tc:
        return {"available": True, "rate": 1.0, "pair": f"{fc}_{tc}", "date": on_date,
                "source": "identity", "retrieved_at": datetime.now(timezone.utc).isoformat(), "candle_time": None}
    if not is_configured():
        return {"available": False, "reason": "OANDA non configuré (clé API absente). Saisissez le taux manuellement."}
    try:
        d = date.fromisoformat((on_date or "")[:10])
    except Exception:
        return {"available": False, "reason": "Date de facture invalide."}
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    url = f"{_base_url()}/v3/accounts/{os.environ['OANDA_ACCOUNT_ID']}/instruments/{_instrument(fc, tc)}/candles"
    params = {"price": "M", "granularity": "D",
              "from": start.isoformat().replace("+00:00", "Z"),
              "to": end.isoformat().replace("+00:00", "Z"),
              "dailyAlignment": 0, "alignmentTimezone": "UTC", "includeFirst": "true"}
    headers = {"Authorization": f"Bearer {os.environ['OANDA_API_TOKEN']}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.RequestError:
        return {"available": False, "reason": "OANDA indisponible (réseau)."}
    if resp.status_code == 401:
        return {"available": False, "reason": "Authentification OANDA échouée (vérifiez le jeton/environnement)."}
    if resp.status_code >= 400:
        return {"available": False, "reason": f"Requête OANDA refusée ({resp.status_code})."}
    candles = (resp.json() or {}).get("candles", [])
    candle = next((c for c in candles if c.get("complete") and (c.get("mid") or {}).get("c")), None)
    if candle is None:
        return {"available": False, "reason": "Aucun taux OANDA pour cette date (week-end/jour férié ?)."}
    try:
        rate = float(candle["mid"]["c"])
    except Exception:
        return {"available": False, "reason": "Taux OANDA illisible."}
    return {"available": True, "rate": rate, "pair": _instrument(fc, tc), "date": on_date,
            "source": SOURCE, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "candle_time": candle.get("time")}
