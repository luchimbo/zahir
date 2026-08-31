"""
Scraper: Productoras de eventos masivos (AGC CABA)
Fuente: datosabiertos GCBA - Agencia Gubernamental de Control
Tier 1 - CSV oficial; los registros se geocodifican con USIG antes de filtrar.
"""

import argparse
import asyncio
import csv
import io
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.db_helpers import (
    get_conn,
    get_source_id,
    bulk_get_or_create_entities,
    bulk_upsert_properties,
    mark_source_synced,
)
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.usig import geocode_address

SUPPORTS_SOURCE_CONTRACT = True

PRODUCTORAS_CSV_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/"
    "productoras-eventos-masivos/productoras-de-eventos-masivos.csv"
)


def clean(value) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "s/d", "sd", "n/a", "nan"}:
        return ""
    return value


def parse_args():
    parser = argparse.ArgumentParser(description="Scraper Productoras de eventos masivos CABA (AGC)")
    add_source_arguments(parser)
    parser.add_argument("--max-geocode", type=int, default=None, help="Tapa el costo de geocodificación USIG por ejecución.")
    return parser.parse_args()


async def main():
    args = parse_args()
    print("=== Scraper Productoras de eventos masivos AGC (CABA) ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")

        print("-> Descargando CSV de productoras...")
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            response = await client.get(PRODUCTORAS_CSV_URL)
            response.raise_for_status()
            text = response.content.decode("utf-8-sig", "replace")
            rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))

        print(f"  {len(rows)} registros oficiales descargados.")

        if args.max_geocode is not None and len(rows) > args.max_geocode:
            rows = rows[:args.max_geocode]
            print(f"  Geocodificando solo {len(rows)} direcciones (teto de costo).")

        print("-> Geocodificando direcciones (USIG)...")
        async with httpx.AsyncClient(timeout=30) as client:
            locations = await asyncio.gather(
                *(
                    geocode_address(client, clean(row.get("DIRECCION"))) if clean(row.get("DIRECCION")) else None
                    for row in rows
                )
            )

        candidates = []
        for row, geo in zip(rows, locations):
            name = normalize_name(clean(row.get("RAZON SOCIAL")))
            if not name:
                continue
            if not record_in_scope(
                lat=getattr(geo, "lat", None),
                lng=getattr(geo, "lng", None),
                scope=args.scope,
                neighborhood=args.neighborhood,
                commune=args.commune,
            ):
                continue
            candidates.append({
                "name": name,
                "entity_type": "Organization",
                "subtype": "event_producer",
                "lat": getattr(geo, "lat", None),
                "lng": getattr(geo, "lng", None),
                "origin_url": PRODUCTORAS_CSV_URL,
                "props": {
                    "address": (clean(row.get("DIRECCION")), "string"),
                    "phone": (clean(row.get("TELEFONO")), "string"),
                    "registration_resolution": (clean(row.get("ULTIMA DISPOSICION")), "string"),
                    "registration_expiry": (clean(row.get("VENCIMIENTO INSCRIPCION")), "string"),
                },
            })

        candidates = bounded(candidates, args.limit)
        print(f"  {len(candidates)} productoras dentro de {args.scope}.")

        if not candidates:
            print("  Sin candidatos para insertar.")
            return

        if not args.write:
            print("Validación completada; usar --write para persistir.")
            return

        entity_records = [
            {
                "name": c["name"],
                "entity_type": c["entity_type"],
                "subtype": c["subtype"],
                "lat": c["lat"],
                "lng": c["lng"],
                "origin_url": c["origin_url"],
            }
            for c in candidates
        ]
        ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

        prop_records = []
        for c in candidates:
            entity_id = ids_by_name.get(c["name"])
            if not entity_id:
                continue
            for key, (val, vtype) in c["props"].items():
                if not val:
                    continue
                prop_records.append({
                    "entity_id": entity_id,
                    "key": key,
                    "value": normalize_value(val),
                    "value_type": vtype,
                    "confidence": 0.95,
                    "origins": [PRODUCTORAS_CSV_URL],
                })

        await bulk_upsert_properties(conn, prop_records, source_id)
        await mark_source_synced(conn, source_id)
        print(f"  [OK] Ingesta productoras AGC completada: {len(candidates)} entidades.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
