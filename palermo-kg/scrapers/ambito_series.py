"""
Scraper: Ámbito Financiero — series históricas de mercado (MERVAL, YPFD.BA)
Fuente: https://mercados.ambito.com (endpoint interno del propio front-end de
        https://www.ambito.com, confirmado por inspección del DOM, no
        documentado públicamente como API — mode="approval" en el catálogo).
Tier 2 — requiere --include-approval en scripts/run_sources.py.

Backfill histórico real de MERVAL/YPFD: BYMA Open Data (scrapers/byma_*.py)
sólo da el snapshot del día; este endpoint sí devuelve series diarias de años
de profundidad. Confirmado por sonda manual el 2026-09-08:
  https://mercados.ambito.com/indice/.merv/historico-general/{desde}/{hasta}
  https://mercados.ambito.com/acciones/YPFD.BA/historico-general/{desde}/{hasta}
  (desde/hasta en formato DD-MM-YYYY; respuesta JSON [[headers],[fila],...]
  con números en formato es-AR: "." miles, "," decimales.)

Este mismo módulo sirve a dos entradas del catálogo (ambito_merval, ambito_ypf)
distinguidas por --symbol; scripts/run_sources.py fija sys.argv[0] al nombre
del módulo, no al de la fuente, así que el símbolo (y por lo tanto el
source_name real) se resuelve siempre desde el argumento, nunca desde argv[0].
"""
import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.contract import SourceResult, add_source_arguments, bounded
from scrapers.shared.db_helpers import (
    bulk_upsert_observations, ensure_source, get_conn, get_or_create_entity,
    latest_observation_date, mark_source_synced, upsert_property,
)

BASE_URL = "https://mercados.ambito.com"
SOURCE_URL = "https://www.ambito.com"
HEADERS = {"User-Agent": "Mozilla/5.0 PalermoKGBot/1.0 (luciotambo@gmail.com)"}

# symbol -> (source_name del catálogo, endpoint, entity_type, entity_name, external_id, series_prefix, unit)
SPECS = {
    "MERVAL": ("ambito_merval", "/indice/.merv/historico-general/",
               "MarketIndex", "Índice S&P Merval", "MERVAL", "merval", "index"),
    "YPFD.BA": ("ambito_ypf", "/acciones/YPFD.BA/historico-general/",
                "Security", "YPF S.A. (YPFD)", "YPFD", "ypfd", "ARS"),
}

DEFAULT_BACKFILL_START = date(2007, 1, 1)  # sondas: 2010 tiene datos de Merval; 2000/1996 vacío.


def parse_es_number(raw) -> float | None:
    """'3.126.275,37' -> 3126275.37. Función pura, testeable sin red.

    Ámbito normalmente serializa los números como string es-AR, pero algunas
    filas (visto en 2025) devuelven un valor "0" ya como int/float JSON crudo
    en vez de string formateado — se acepta también ese caso."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = str(raw).strip().replace(".", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_ddmmyyyy(raw: str) -> date:
    day, month, year = raw.strip().split("-")
    return date(int(year), int(month), int(day))


def parse_history_response(data: list) -> list[dict]:
    """Convierte la matriz [[headers],[fila],...] de Ámbito en dicts con
    claves normalizadas. Función pura, testeable sin red."""
    if not data or len(data) < 2:
        return []
    header = [h.strip().lower().rstrip(".").replace(" %", "") for h in data[0]]
    rows = []
    for raw_row in data[1:]:
        record = dict(zip(header, raw_row))
        fecha = record.get("fecha")
        if not fecha:
            continue
        rows.append({
            "date": parse_ddmmyyyy(fecha),
            "open": parse_es_number(record.get("apertura")),
            "close": parse_es_number(record.get("ultimo")),
            "var_pct": parse_es_number(record.get("var")),
            "high": parse_es_number(record.get("max")),
            "low": parse_es_number(record.get("min")),
        })
    return rows


def year_chunks(start: date, end: date):
    """Genera tramos [desde, hasta] de a lo sumo un año, del más viejo al más nuevo."""
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(date(cursor.year, 12, 31), end)
        chunks.append((cursor, chunk_end))
        cursor = date(cursor.year + 1, 1, 1)
    return chunks


async def fetch_range(client: httpx.AsyncClient, endpoint: str, desde: date, hasta: date) -> list[dict]:
    url = BASE_URL + endpoint + desde.strftime("%d-%m-%Y") + "/" + hasta.strftime("%d-%m-%Y")
    r = await client.get(url)
    r.raise_for_status()
    return parse_history_response(r.json())


async def main():
    parser = argparse.ArgumentParser(description="Ámbito Financiero — series históricas")
    add_source_arguments(parser)
    parser.add_argument("--symbol", choices=list(SPECS), default="MERVAL",
                        help="Serie a ingerir (default: MERVAL).")
    args = parser.parse_args()

    if args.neighborhood or args.commune:
        return SourceResult(skipped=1, errors=["Fuente nacional: no admite acotar por barrio/comuna."])

    source_name, endpoint, entity_type, entity_name, external_id, prefix, unit = SPECS[args.symbol]
    result = SourceResult()
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, source_name, SOURCE_URL, 2)
        close_key = f"ambito_{prefix}_close"
        since_raw = await latest_observation_date(conn, source_id, close_key)
        since = (since_raw + timedelta(days=1)) if since_raw else DEFAULT_BACKFILL_START
        if args.since:
            since = date.fromisoformat(args.since)
        today = date.today()

        all_points = []
        async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            for desde, hasta in year_chunks(since, today):
                try:
                    rows = await fetch_range(client, endpoint, desde, hasta)
                except Exception as exc:
                    result.errors.append(f"{desde}/{hasta}: {type(exc).__name__}: {exc}")
                    continue
                all_points.extend(rows)
                await asyncio.sleep(1)

        result.seen = len(all_points)
        all_points = bounded(all_points, args.limit)
        result.accepted = len(all_points)

        if not args.write:
            print(f"[OK] {source_name} (validate): {result.seen} filas vistas, "
                  f"{result.accepted} aceptadas | since={since} write=False")
            return result

        entity_id = await get_or_create_entity(
            conn, name=entity_name, entity_type=entity_type,
            subtype="equity_index" if entity_type == "MarketIndex" else "equity",
            origin_url=SOURCE_URL, source_id=source_id, external_id=external_id,
        )
        await upsert_property(conn, entity_id, "ticker", external_id, "string", source_id, origins=[SOURCE_URL])

        observations = []
        for row in all_points:
            observed_at = row["date"].isoformat()
            for suffix, value in (("open", row["open"]), ("close", row["close"]),
                                  ("high", row["high"]), ("low", row["low"]),
                                  ("var_pct", row["var_pct"])):
                if value is None:
                    continue
                observations.append({
                    "entity_id": entity_id, "series_key": f"ambito_{prefix}_{suffix}",
                    "observed_at": observed_at, "observed_period": observed_at,
                    "frequency": "daily", "value": value,
                    "unit": "pct" if suffix == "var_pct" else unit,
                    "payload": {"fecha": observed_at, **row, "date": observed_at},
                    "origins": [BASE_URL + endpoint + observed_at],
                })

        result.written = await bulk_upsert_observations(conn, observations, source_id)
        if result.ok:
            await mark_source_synced(conn, source_id)
        if all_points:
            result.checkpoint = max(row["date"] for row in all_points).isoformat()

        print(f"[OK] {source_name}: {result.seen} filas vistas, {result.accepted} aceptadas, "
              f"{result.written} escritas | since={since} write=True")
        return result
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
