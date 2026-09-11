"""Cliente compartido para el chart público de Yahoo Finance.

Endpoint no oficial (`query1.finance.yahoo.com/v8/finance/chart/{ticker}`), sin
licencia de reuso publicada: la fuente que lo consume entra con mode="approval",
mismo criterio conservador que ambito_series.py. Ver SOURCE_OPERATIONS.md.

Confirmado por sonda (2026-09-09) sobre los 106 tickers ARS del padrón BYMA:
  - 89 resuelven; los 17 restantes son clases B ya cubiertas por su clase
    principal y FCI cerrados, que devuelven 404.
  - Con period1=0 y interval=1d la profundidad real llega a 2000-01-03 para las
    emisoras viejas (BBAR, BMA, TXAR, MOLI, TECO2, TGSU2, YPFD...).
  - `range=max` NO sirve: Yahoo degrada la resolución a mensual e ignora
    interval=1d. Hay que pasar period1/period2 explícitos.
  - meta.longName trae la razón social ("Grupo Financiero Galicia S.A."), que es
    el puente hacia los LegalEntity de IGJ.
  - Un User-Agent de bot recibe 403/429; hace falta uno de navegador.
"""
from datetime import datetime, timezone

import httpx

BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}

PRICE_FIELDS = ("open", "high", "low", "close", "adj_close")


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, timeout=40, follow_redirects=True)


def yahoo_symbol(byma_symbol: str) -> str:
    """BMA.5 -> BMA-5.BA. El punto es separador de sufijo de mercado en Yahoo."""
    return byma_symbol.replace(".", "-") + ".BA"


async def chart(client: httpx.AsyncClient, ticker: str, period1: int,
                period2: int) -> tuple[dict, str]:
    r = await client.get(BASE + ticker, params={
        "period1": period1, "period2": period2, "interval": "1d", "events": "div,split",
    })
    r.raise_for_status()
    return r.json(), str(r.url)


def _epoch_to_date(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError):
        return None


def _at(values, index):
    """Yahoo deja None en ruedas sin operaciones y a veces acorta las listas de
    indicadores respecto de `timestamp`. Ambos casos son ausencia de dato."""
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def parse_chart(payload: dict) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """Convierte la respuesta del chart en (meta, filas, dividendos, splits).

    Función pura, testeable sin red. Tolera result nulo/vacío, chart.error no
    nulo y ausencia de timestamp (ticker sin datos) devolviendo estructuras
    vacías en vez de romper: un ticker sin historia no debe cortar el recorrido.
    """
    empty: tuple[dict, list, list, list] = ({}, [], [], [])
    if not isinstance(payload, dict):
        return empty
    result = (payload.get("chart") or {}).get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return empty
    result = result[0]

    raw_meta = result.get("meta") or {}
    meta = {
        "currency": raw_meta.get("currency"),
        "long_name": raw_meta.get("longName") or raw_meta.get("shortName"),
        "exchange": raw_meta.get("fullExchangeName") or raw_meta.get("exchangeName"),
    }

    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0] or {}
    adjclose = (indicators.get("adjclose") or [{}])[0] or {}
    timestamps = result.get("timestamp") or []

    rows = []
    for index, timestamp in enumerate(timestamps):
        observed_at = _epoch_to_date(timestamp)
        if observed_at is None:
            continue
        rows.append({
            "date": observed_at,
            "open": _at(quote.get("open"), index),
            "high": _at(quote.get("high"), index),
            "low": _at(quote.get("low"), index),
            "close": _at(quote.get("close"), index),
            "adj_close": _at(adjclose.get("adjclose"), index),
            "volume": _at(quote.get("volume"), index),
        })

    events = result.get("events") or {}
    dividends = []
    for item in (events.get("dividends") or {}).values():
        observed_at = _epoch_to_date((item or {}).get("date"))
        if observed_at is None or item.get("amount") is None:
            continue
        dividends.append({"date": observed_at, "amount": item["amount"]})

    splits = []
    for item in (events.get("splits") or {}).values():
        observed_at = _epoch_to_date((item or {}).get("date"))
        numerator, denominator = (item or {}).get("numerator"), (item or {}).get("denominator")
        if observed_at is None or not numerator or not denominator:
            continue
        splits.append({
            "date": observed_at, "ratio": float(numerator) / float(denominator),
            "numerator": numerator, "denominator": denominator,
        })

    dividends.sort(key=lambda row: row["date"])
    splits.sort(key=lambda row: row["date"])
    return meta, rows, dividends, splits
