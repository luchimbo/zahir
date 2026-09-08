"""
Scraper: BCRA — Estadísticas Monetarias (v4.0) y Cambiarias (v1.0)
Fuente: https://api.bcra.gob.ar
Tier 1 — API pública oficial, sin autenticación.

Confirmado por sonda (scripts/exploration/probe_bcra_api.py, 2026-09-08): la
API responde de forma confiable con TLS estándar; la nota previa en
SOURCE_OPERATIONS.md sobre BCRA "no responde de forma confiable" se refería a
otro endpoint (padrón de entidades), no a estas dos APIs de estadísticas.

Una entidad EconomicSeries por variable monetaria (idVariable estable, la
descripción puede cambiar de redacción) y una por moneda cambiaria. Sin
geografía: es contexto macro nacional, no un dato de CABA (db/RULES.md §11).
"""
import argparse
import asyncio
import os
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

SOURCE_NAME = "bcra_estadisticas"
SOURCE_URL = "https://api.bcra.gob.ar"
HEADERS = {"User-Agent": "PalermoKGBot/1.0 (luciotambo@gmail.com)"}

# Cobertura macro deliberadamente acotada. El catálogo tiene más de 1.600
# variables; ingerirlo completo no es una operación razonable para la capa
# contextual ni para los límites de TiDB. BCRA_VARIABLE_IDS permite ampliar
# explícitamente este conjunto en una ejecución manual.
MACRO_VARIABLE_IDS = (1, 4, 5, 7, 14, 15, 26, 27, 28, 160, 1240)
CAMBIARIAS_CODES = ["USD"]  # dólar oficial: la serie cambiaria más consultada.
PAGE_LIMIT = 1000
FREQUENCY_BY_BCRA_CODE = {"D": "daily", "S": "weekly", "M": "monthly", "T": "quarterly", "A": "annual"}


def configured_variable_ids() -> set[int]:
    raw = os.getenv("BCRA_VARIABLE_IDS", "").strip()
    if not raw:
        return set(MACRO_VARIABLE_IDS)
    try:
        return {int(value.strip()) for value in raw.split(",") if value.strip()}
    except ValueError as exc:
        raise ValueError("BCRA_VARIABLE_IDS debe ser una lista de enteros separados por coma") from exc


def frequency_for(variable: dict) -> str:
    return FREQUENCY_BY_BCRA_CODE.get(str(variable.get("periodicidad") or "").upper(), "irregular")


def parse_monetarias_catalog(payload: dict) -> list[dict]:
    """Función pura: lista de variables del envelope v4.0."""
    return payload.get("results") or []


def parse_monetarias_detalle(payload: dict) -> list[dict]:
    """Función pura: [{"fecha","valor"}] de un resultado de /monetarias/{id}."""
    results = payload.get("results") or []
    if not results:
        return []
    return results[0].get("detalle") or []


def parse_cotizaciones(payload: dict) -> list[dict]:
    """Función pura: aplana {"results":[{"fecha","detalle":[...]}]} a filas
    [{"fecha","codigoMoneda","tipoCotizacion"}]."""
    rows = []
    for entry in payload.get("results") or []:
        fecha = entry.get("fecha")
        for det in entry.get("detalle") or []:
            rows.append({"fecha": fecha, "codigoMoneda": det.get("codigoMoneda"),
                        "tipoCotizacion": det.get("tipoCotizacion")})
    return rows


async def get_json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    for attempt in range(2):
        r = await client.get(url, params=params or {})
        if r.status_code != 429 or attempt:
            r.raise_for_status()
            return r.json()
        await asyncio.sleep(60)
    raise RuntimeError("BCRA devolvió 429 dos veces")


async def fetch_monetarias_catalog(client: httpx.AsyncClient) -> list[dict]:
    first = await get_json(client, f"{SOURCE_URL}/estadisticas/v4.0/monetarias",
                           {"limit": PAGE_LIMIT, "offset": 0})
    variables = parse_monetarias_catalog(first)
    count = int((((first.get("metadata") or {}).get("resultset") or {}).get("count") or len(variables)))
    for offset in range(PAGE_LIMIT, count, PAGE_LIMIT):
        page = await get_json(client, f"{SOURCE_URL}/estadisticas/v4.0/monetarias",
                              {"limit": PAGE_LIMIT, "offset": offset})
        variables.extend(parse_monetarias_catalog(page))
        await asyncio.sleep(0.25)
    return variables


async def backfill_variable(client, conn, source_id, variable: dict, since: date | None) -> tuple[list[dict], list[str]]:
    id_variable = variable["idVariable"]
    series_key = f"bcra_var_{id_variable}"
    start = since or (date.fromisoformat(variable["primerFechaInformada"])
                      if variable.get("primerFechaInformada") else date(2000, 1, 1))
    errors = []
    all_detalle = []
    cursor = start
    today = date.today()
    while cursor <= today:
        chunk_end = min(date(cursor.year, 12, 31), today)
        try:
            payload = await get_json(client, f"{SOURCE_URL}/estadisticas/v4.0/monetarias/{id_variable}",
                                     {"desde": cursor.isoformat(), "hasta": chunk_end.isoformat(), "limit": PAGE_LIMIT})
            all_detalle.extend(parse_monetarias_detalle(payload))
        except Exception as exc:
            errors.append(f"var {id_variable} {cursor}/{chunk_end}: {type(exc).__name__}: {exc}")
        cursor = date(cursor.year + 1, 1, 1)
        await asyncio.sleep(0.25)

    entity_id = await get_or_create_entity(
        conn, name=variable.get("descripcion") or f"Variable BCRA {id_variable}",
        entity_type="EconomicSeries", subtype="monetary_variable",
        origin_url=SOURCE_URL, source_id=source_id, external_id=str(id_variable),
    )
    for key, value in (
        ("series_code", str(id_variable)), ("series_description", variable.get("descripcion")),
        ("unit", variable.get("unidadExpresion")), ("frequency", variable.get("periodicidad")),
        ("publisher", "BCRA"),
    ):
        if value:
            await upsert_property(conn, entity_id, key, str(value), "string", source_id, origins=[SOURCE_URL])

    observations = [
        {
            "entity_id": entity_id, "series_key": series_key, "observed_at": row["fecha"],
            "observed_period": row["fecha"], "frequency": frequency_for(variable), "value": row.get("valor"),
            "unit": variable.get("unidadExpresion"), "payload": row,
            "origins": [f"{SOURCE_URL}/estadisticas/v4.0/monetarias/{id_variable}"],
        }
        for row in all_detalle if row.get("valor") is not None
    ]
    return observations, errors


async def backfill_cambiaria(client, conn, source_id, codigo: str, since: date | None) -> tuple[list[dict], list[str]]:
    series_key = f"bcra_fx_{codigo.lower()}"
    start = since or date(2015, 1, 1)
    today = date.today()
    errors = []
    all_rows = []
    cursor = start
    while cursor <= today:
        chunk_end = min(date(cursor.year, 12, 31), today)
        try:
            payload = await get_json(client, f"{SOURCE_URL}/estadisticascambiarias/v1.0/Cotizaciones/{codigo}",
                                     {"fechadesde": cursor.isoformat(), "fechahasta": chunk_end.isoformat(), "limit": PAGE_LIMIT})
            all_rows.extend(parse_cotizaciones(payload))
        except Exception as exc:
            errors.append(f"fx {codigo} {cursor}/{chunk_end}: {type(exc).__name__}: {exc}")
        cursor = date(cursor.year + 1, 1, 1)
        await asyncio.sleep(0.25)

    entity_id = await get_or_create_entity(
        conn, name=f"Tipo de Cambio Oficial {codigo}/ARS", entity_type="EconomicSeries",
        subtype="exchange_rate", origin_url=SOURCE_URL, source_id=source_id, external_id=f"FX-{codigo}",
    )
    for key, value in (("series_code", f"FX-{codigo}"), ("unit", "ARS"),
                       ("frequency", "daily"), ("publisher", "BCRA")):
        await upsert_property(conn, entity_id, key, value, "string", source_id, origins=[SOURCE_URL])

    observations = [
        {
            "entity_id": entity_id, "series_key": series_key, "observed_at": row["fecha"],
            "observed_period": row["fecha"], "frequency": "daily", "value": row.get("tipoCotizacion"),
            "unit": "ARS", "payload": row,
            "origins": [f"{SOURCE_URL}/estadisticascambiarias/v1.0/Cotizaciones/{codigo}"],
        }
        for row in all_rows if row.get("tipoCotizacion") is not None
    ]
    return observations, errors


async def main():
    parser = argparse.ArgumentParser(description="BCRA — Estadísticas Monetarias y Cambiarias")
    add_source_arguments(parser)
    args = parser.parse_args()

    if args.neighborhood or args.commune:
        return SourceResult(skipped=1, errors=["Fuente nacional: no admite acotar por barrio/comuna."])

    result = SourceResult()
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, SOURCE_NAME, SOURCE_URL, 1)
        async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            try:
                catalog = await fetch_monetarias_catalog(client)
            except Exception as exc:
                result.errors.append(f"catálogo monetarias: {type(exc).__name__}: {exc}")
                return result
            requested_ids = configured_variable_ids()
            available = {variable["idVariable"]: variable for variable in catalog}
            missing = requested_ids - set(available)
            if missing:
                result.errors.append(f"variables BCRA no encontradas: {sorted(missing)}")
            variables = [available[var_id] for var_id in sorted(requested_ids) if var_id in available]

            if not args.write:
                # Validar conectividad/forma sin correr el backfill completo
                # (con cientos de variables x años, sería un runtime enorme).
                try:
                    await get_json(client, f"{SOURCE_URL}/estadisticascambiarias/v1.0/Cotizaciones/USD")
                except Exception as exc:
                    result.errors.append(f"cambiarias USD: {type(exc).__name__}: {exc}")
                result.seen = result.accepted = len(variables)
                result.coverage = {"mode": "validate", "variables_en_catalogo": len(catalog),
                                   "variables_seleccionadas": len(variables)}
                print(f"[OK] bcra_estadisticas (validate): {len(variables)} variables seleccionadas, "
                      f"cambiarias USD {'OK' if result.ok else 'FALLÓ'} | write=False")
                return result

            all_observations = []
            for variable in variables:
                since = None if args.since is None else date.fromisoformat(args.since)
                if since is None:
                    since_raw = await latest_observation_date(conn, source_id, f"bcra_var_{variable['idVariable']}")
                    since = (since_raw + timedelta(days=1)) if since_raw else None
                observations, errors = await backfill_variable(client, conn, source_id, variable, since)
                all_observations.extend(observations)
                result.errors.extend(errors)

            for codigo in CAMBIARIAS_CODES:
                since_raw = await latest_observation_date(conn, source_id, f"bcra_fx_{codigo.lower()}")
                since = (since_raw + timedelta(days=1)) if since_raw else None
                observations, errors = await backfill_cambiaria(client, conn, source_id, codigo, since)
                all_observations.extend(observations)
                result.errors.extend(errors)

        result.seen = len(all_observations)
        accepted_observations = bounded(all_observations, args.limit)
        result.accepted = len(accepted_observations)
        result.written = await bulk_upsert_observations(conn, accepted_observations, source_id)
        if result.ok:
            await mark_source_synced(conn, source_id)
        result.coverage = {"variables_procesadas": len(variables), "series_cambiarias": len(CAMBIARIAS_CODES),
                           "variables_en_catalogo": len(catalog)}

        print(f"[OK] bcra_estadisticas: {len(variables)} variables, {len(all_observations)} puntos, "
              f"{result.written} escritos | write=True")
        return result
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
