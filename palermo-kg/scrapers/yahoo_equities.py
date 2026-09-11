"""
Scraper: acciones argentinas — padrón BYMA + series históricas diarias de Yahoo.
Tier 3 — requiere --include-approval en scripts/run_sources.py.

Por qué esta combinación (sondas del 2026-09-09, ver SOURCE_OPERATIONS.md):
  - El padrón sale de BYMA Open Data (leading-equity + general-equity): es el
    único listado gratuito y autoritativo de qué cotiza hoy. Una sola llamada.
  - Los precios NO salen de BYMA: su chart sólo devuelve desde 2024-09 (~486
    ruedas). Ámbito tiene profundidad pero sólo responde para YPFD.BA. Yahoo
    cubre 89 de los 106 tickers ARS con daily desde 2000-01-03, más adjusted
    close, dividendos y splits.
  - Yahoo es una API no oficial sin licencia de reuso publicada: mode="approval",
    mismo criterio conservador que ambito_series.py y cnv.

Los 17 tickers que Yahoo no resuelve son clases B ya cubiertas por su clase
principal (CECOB, CVHB, DGCUB, EDNB, TECOB, TGN4B, TGSUB, CRECB, PNZFB) y FCI
cerrados, que no son empresas (ADBGF, ADGPF, ALAAF, ALABF, MELIF, MELFB, VALFF),
más ATGS. Se reportan en errors y quedan visibles en source_run_metrics.coverage.
"""
import argparse
import asyncio
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared import byma_client, yahoo_client
from scrapers.shared.contract import SourceResult, add_source_arguments, bounded
from scrapers.shared.db_helpers import (bulk_upsert_observations, ensure_source, get_conn,
    get_or_create_entity, latest_observation_date, link_security_to_legal_entity,
    mark_source_synced, upsert_property)

SOURCE_NAME = "yahoo_ar_equities"
SOURCE_URL = "https://finance.yahoo.com"
PANEL_URL = "https://open.bymadata.com.ar"
REQUEST_PAUSE_SECONDS = 0.5

# (sufijo de series_key, campo de la fila, unidad)
PRICE_SERIES = (
    ("open", "open", "ARS"), ("high", "high", "ARS"), ("low", "low", "ARS"),
    ("close", "close", "ARS"), ("adj_close", "adj_close", "ARS"),
    ("volume", "volume", "shares"),
)


def series_slug(symbol: str) -> str:
    """BMA.5 -> bma_5. observations.series_key valida ^[a-z][a-z0-9_]{0,149}$."""
    return re.sub(r"[^a-z0-9]", "_", symbol.lower())


def observations_for(entity_id: str, symbol: str, rows: list[dict], dividends: list[dict],
                     splits: list[dict], origin: str) -> list[dict]:
    """Arma el lote de observaciones de un ticker. Pura, testeable sin red."""
    slug = series_slug(symbol)
    observations = []
    for row in rows:
        observed_at = row["date"].isoformat()
        payload = {**row, "date": observed_at}
        for suffix, field, unit in PRICE_SERIES:
            if row.get(field) is None:
                continue
            observations.append({
                "entity_id": entity_id, "series_key": f"yahoo_{slug}_{suffix}",
                "observed_at": observed_at, "observed_period": observed_at,
                "frequency": "daily", "value": row[field], "unit": unit,
                "payload": payload, "origins": [origin],
            })
    for row in dividends:
        observed_at = row["date"].isoformat()
        observations.append({
            "entity_id": entity_id, "series_key": f"yahoo_{slug}_dividend",
            "observed_at": observed_at, "observed_period": observed_at,
            "frequency": "irregular", "value": row["amount"], "unit": "ARS",
            "payload": {"date": observed_at, "amount": row["amount"]}, "origins": [origin],
        })
    for row in splits:
        observed_at = row["date"].isoformat()
        observations.append({
            "entity_id": entity_id, "series_key": f"yahoo_{slug}_split_ratio",
            "observed_at": observed_at, "observed_period": observed_at,
            "frequency": "irregular", "value": row["ratio"], "unit": "index",
            "payload": {"date": observed_at, "numerator": row["numerator"],
                        "denominator": row["denominator"]},
            "origins": [origin],
        })
    return observations


async def resolve_universe(args, result: SourceResult) -> list[dict]:
    """Tickers a ingerir: los explícitos de --symbols, o el padrón vigente de BYMA."""
    if args.symbols:
        return [{"symbol": symbol.strip().upper(), "panel": "manual"}
                for symbol in args.symbols.split(",") if symbol.strip()]
    async with byma_client.make_client() as client:
        rows, errors = await byma_client.list_equities(client)
    result.errors.extend(errors)
    return byma_client.select_ars_tickers(rows)


async def ingest_ticker(conn, client, source_id: str, spec: dict, args,
                        result: SourceResult) -> date | None:
    """Ingiere un ticker. Devuelve la última fecha escrita, o None."""
    symbol = spec["symbol"]
    slug = series_slug(symbol)
    ticker = yahoo_client.yahoo_symbol(symbol)

    if args.since:
        since = date.fromisoformat(args.since)
    else:
        last = await latest_observation_date(conn, source_id, f"yahoo_{slug}_close")
        since = (last + timedelta(days=1)) if last else None
    period1 = int(datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc).timestamp()) if since else 0

    try:
        payload, origin = await yahoo_client.chart(client, ticker, period1, int(time.time()))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (404, 422):
            raise
        # Yahoo no cubre ese ticker (clases B y FCI cerrados del padrón). Es un
        # hueco conocido de cobertura, no una falla de la corrida: va a skipped
        # y a coverage, no a errors, para no bloquear la promoción del piloto.
        result.skipped += 1
        result.coverage[symbol] = 0
        return None

    meta, rows, dividends, splits = yahoo_client.parse_chart(payload)
    result.seen += len(rows)
    result.coverage[symbol] = len(rows)
    if not rows and not dividends and not splits:
        result.skipped += 1
        return None
    result.accepted += len(rows)
    if not args.write:
        return max((row["date"] for row in rows), default=None)

    issuer_name = meta.get("long_name") or symbol
    entity_id = await get_or_create_entity(
        conn, name=f"{issuer_name} ({symbol})", entity_type="Security", subtype="equity",
        origin_url=origin, source_id=source_id, external_id=symbol,
    )
    for key, value in (("ticker", symbol), ("market", "BYMA"),
                       ("currency", meta.get("currency") or "ARS"),
                       ("issuer_name", issuer_name), ("yahoo_symbol", ticker)):
        if value:
            await upsert_property(conn, entity_id, key, value, "string", source_id, origins=[origin])
    if args.link_legal_entities:
        linked = await link_security_to_legal_entity(conn, entity_id, issuer_name, origins=[origin])
        if linked:
            result.coverage[f"{symbol}__legal_entity"] = 1

    observations = observations_for(entity_id, symbol, rows, dividends, splits, origin)
    result.written += await bulk_upsert_observations(conn, observations, source_id)
    return max((row["date"] for row in rows), default=None)


async def main():
    parser = argparse.ArgumentParser(description="Acciones argentinas — padrón BYMA + histórico Yahoo")
    add_source_arguments(parser)
    parser.add_argument("--symbols", default=None,
                        help="Subconjunto de tickers BYMA separados por coma (ej: GGAL,ALUA). "
                             "Sin esta opción se usa el padrón vigente completo.")
    parser.add_argument("--link-legal-entities", action="store_true",
                        help="Vincula cada Security con la sociedad IGJ homónima (match exacto).")
    args = parser.parse_args()

    if args.neighborhood or args.commune:
        return SourceResult(skipped=1, errors=["Fuente nacional: no admite acotar por barrio/comuna."])

    result = SourceResult()
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, SOURCE_NAME, SOURCE_URL, 3)
        universe = bounded(await resolve_universe(args, result), args.limit)
        if not universe:
            result.errors.append("Padrón vacío: no se resolvió ningún ticker.")
            return result

        checkpoints = []
        async with yahoo_client.make_client() as client:
            for index, spec in enumerate(universe):
                try:
                    last = await ingest_ticker(conn, client, source_id, spec, args, result)
                except Exception as exc:
                    result.errors.append(f"{spec['symbol']}: {type(exc).__name__}: {exc}")
                    last = None
                if last:
                    checkpoints.append(last)
                if index + 1 < len(universe):
                    await asyncio.sleep(REQUEST_PAUSE_SECONDS)

        if checkpoints:
            result.checkpoint = max(checkpoints).isoformat()
        if args.write and result.ok:
            await mark_source_synced(conn, source_id)
        print(f"[OK] {SOURCE_NAME}: {len(universe)} tickers, {result.seen} ruedas vistas, "
              f"{result.written} observaciones escritas, {result.skipped} sin cobertura, "
              f"{len(result.errors)} errores | write={args.write}")
        return result
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
