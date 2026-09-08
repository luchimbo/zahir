"""Cliente compartido para BYMA Open Data (open.bymadata.com.ar).

Confirmado por sonda (scripts/exploration/probe_byma.py, 2026-09-08):
  - El contexto TLS por defecto funciona; no hace falta relajar cifrado.
  - Los snapshots son POST; las series de chart son GET.
  - Merval usa chart/index-historical-series/history con symbol=M.
  - YPFD usa chart/historical-series/history con symbol="YPFD 24hs".
"""
from datetime import datetime, timezone

import httpx

BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 PalermoKGBot/1.0 (luciotambo@gmail.com)",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://open.bymadata.com.ar",
    "Referer": "https://open.bymadata.com.ar/",
}


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)


async def post(client: httpx.AsyncClient, path: str, body: dict | None = None) -> dict:
    r = await client.post(BASE + path, json=body or {})
    r.raise_for_status()
    return r.json()


async def chart_history(client: httpx.AsyncClient, path: str, symbol: str, since_epoch: int,
                        until_epoch: int) -> tuple[dict, str]:
    r = await client.get(BASE + path, params={
        "symbol": symbol, "resolution": "D", "from": since_epoch, "to": until_epoch,
    })
    r.raise_for_status()
    return r.json(), str(r.url)


def parse_chart_history(payload: dict) -> list[dict]:
    """Convierte el formato TradingView de BYMA a filas diarias puras."""
    if payload.get("s") != "ok":
        return []
    fields = {key: payload.get(key) or [] for key in ("t", "o", "h", "l", "c", "v")}
    rows = []
    for index, timestamp in enumerate(fields["t"]):
        try:
            observed_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date()
        except (TypeError, ValueError, OSError):
            continue
        rows.append({
            "date": observed_at,
            "t": timestamp,
            "o": fields["o"][index] if index < len(fields["o"]) else None,
            "h": fields["h"][index] if index < len(fields["h"]) else None,
            "l": fields["l"][index] if index < len(fields["l"]) else None,
            "c": fields["c"][index] if index < len(fields["c"]) else None,
            "v": fields["v"][index] if index < len(fields["v"]) else None,
        })
    return rows
