"""Cliente compartido para BYMA Open Data (open.bymadata.com.ar).

Confirmado por sonda (scripts/exploration/probe_byma.py, 2026-09-08):
  - El contexto TLS por defecto funciona; no hace falta relajar cifrado.
  - Los snapshots son POST; las series de chart son GET.
  - Merval usa chart/index-historical-series/history con symbol=M.
  - YPFD usa chart/historical-series/history con symbol="YPFD 24hs".

Ampliado por sonda del 2026-09-09 (padrón de especies):
  - leading-equity devuelve 40 filas; general-equity, 347.
  - La paginación es `page_size` en snake_case dentro del body. Con `pageSize`,
    `size` o `limit` la API ignora el pedido y devuelve la página 1 de 2 (189
    filas, cortando en HARG) sin señalar nada: hay que leer `content` para
    detectarlo.
"""
import re
from datetime import datetime, timezone

import httpx

EQUITY_PANELS = ("leading-equity", "general-equity")
# Sufijos de clase de liquidación: D = dólar MEP, C = cable, B/5 = otras clases.
# Solo se descartan cuando la raíz cotiza por separado (ALUAD -> ALUA), nunca
# por la sola forma del ticker: CECO2, DGCU2, TECO2 o MOLA5 son especies propias.
_CLASS_SUFFIX_RE = re.compile(r"^(?P<root>.+?)\.?(?P<suffix>[BCD5])$")

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


async def list_equities(client: httpx.AsyncClient,
                        panels: tuple[str, ...] = EQUITY_PANELS) -> tuple[list[dict], list[str]]:
    """Padrón de especies de renta variable listadas hoy en BYMA.

    Devuelve ``(filas, errores)``. Cada fila lleva ``_panel`` para saber de qué
    panel vino. Un panel que devuelve menos filas de las que su propio
    ``content.total_elements_count`` declara se reporta como error en vez de
    ingerirse truncado: un universo incompleto es peor que uno ausente.
    """
    rows, errors = [], []
    for panel in panels:
        try:
            payload = await post(client, panel, {"excludeZeroPxAndQty": False, "page_size": 1000})
        except Exception as exc:
            errors.append(f"{panel}: {type(exc).__name__}: {exc}")
            continue
        data = [row for row in (payload.get("data") or []) if isinstance(row, dict)]
        declared = (payload.get("content") or {}).get("total_elements_count")
        if declared is not None and len(data) != declared:
            errors.append(f"{panel}: padrón truncado ({len(data)} de {declared} filas)")
            continue
        for row in data:
            rows.append({**row, "_panel": panel})
    return rows, errors


def select_ars_tickers(rows: list[dict]) -> list[dict]:
    """Filtra el padrón a emisoras argentinas en pesos. Pura, testeable sin red.

    Las filas vienen duplicadas por ``settlementType`` (1 = CI, 2 = 24hs) y por
    aparecer en ambos paneles; se conserva una sola por símbolo. Después se
    colapsan las clases de liquidación contra su raíz para no contar dos veces
    la misma empresa (ALUAD y ALUA son Aluar; MOLA5 y MOLA son Molinos Agro).
    """
    by_symbol: dict[str, dict] = {}
    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        if not symbol or row.get("denominationCcy") != "ARS":
            continue
        by_symbol.setdefault(symbol, {
            "symbol": symbol,
            "security_type": row.get("securityType"),
            "sub_type": row.get("securitySubType"),
            "panel": row.get("_panel"),
        })
    selected = []
    for symbol, spec in by_symbol.items():
        match = _CLASS_SUFFIX_RE.match(symbol)
        if match and match.group("root") in by_symbol:
            continue
        selected.append(spec)
    return sorted(selected, key=lambda spec: spec["symbol"])


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
