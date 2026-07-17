"""Ingesta acotada de locales bailables y permisos de eventos masivos de GCBA.

Fuente oficial BA Data. Por defecto opera en modo dry-run; usar --write para
persistir entidades y propiedades. Solo considera Palermo/Comuna 14 o puntos
dentro del bounding box definido.
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

from scrapers.shared.db_helpers import (
    bulk_get_or_create_entities,
    bulk_upsert_properties,
    get_conn,
    get_source_id,
    mark_source_synced,
)
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.usig import geocode_address

LOCALES_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/locales-bailables/locales_bailables.csv"
EVENTS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/permisos-eventos-masivos/permisos-eventos-masivos.csv"
LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390


def clean(value) -> str:
    value = "" if value is None else str(value).strip()
    return "" if value.lower() in {"", "null", "none", "nan", "s/d"} else value


def parse_float(value):
    try:
        return float(clean(value).replace(",", "."))
    except ValueError:
        return None


def in_palermo(lat, lng) -> bool:
    return lat is not None and lng is not None and LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


async def fetch_rows(client, url):
    response = await client.get(url)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


async def ingest(conn, source_id, candidates):
    records = [{key: value for key, value in c.items() if key != "props"} for c in candidates]
    ids = await bulk_get_or_create_entities(conn, records)
    props = []
    for candidate in candidates:
        entity_id = ids.get(candidate["name"])
        if not entity_id:
            continue
        for key, value, value_type in candidate["props"]:
            if clean(value):
                props.append({"entity_id": entity_id, "key": key, "value": normalize_value(value),
                              "value_type": value_type, "confidence": 0.95,
                              "origins": [candidate["origin_url"]]})
    await bulk_upsert_properties(conn, props, source_id)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Persiste la muestra validada en la base")
    parser.add_argument("--only", choices=["locales", "events"])
    parser.add_argument("--limit", type=int, default=50, help="Máximo de direcciones de locales a consultar (default: 50)")
    args = parser.parse_args()
    candidates = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        if args.only in (None, "locales"):
            checked = 0
            for row in await fetch_rows(client, LOCALES_URL):
                if checked >= args.limit:
                    break
                address = f"{clean(row.get('DOMICILIO'))} {clean(row.get('nº'))}".strip()
                if not address:
                    continue
                checked += 1
                geocoded = await geocode_address(client, address)
                if not geocoded or not in_palermo(geocoded.lat, geocoded.lng):
                    continue
                name = normalize_name(clean(row.get("NOMBRE")) or clean(row.get("RAZON SOCIAL")))
                if name:
                    candidates.append({"name": f"Local Bailable {name} - {address}", "entity_type": "Organization",
                        "subtype": "nightclub", "lat": geocoded.lat, "lng": geocoded.lng, "origin_url": LOCALES_URL,
                        "props": [("legal_name", clean(row.get("RAZON SOCIAL")), "string"),
                                  ("address", address, "string"), ("registration_status", clean(row.get("Estado")), "string"),
                                  ("capacity", clean(row.get("Capacidad")), "string"),
                                  ("permit_number", clean(row.get("EXPEDIENTE HABILITACION")), "string")]})
        if args.only in (None, "events"):
            for row in await fetch_rows(client, EVENTS_URL):
                lat, lng = parse_float(row.get("lat")), parse_float(row.get("long"))
                if clean(row.get("barrio")).lower() != "palermo" and not in_palermo(lat, lng):
                    continue
                title = normalize_name(row.get("denominacion_evento"))
                if title:
                    candidates.append({"name": f"Evento Masivo {title} - {clean(row.get('fecha'))}", "entity_type": "Event",
                        "subtype": "mass_event", "lat": lat, "lng": lng, "origin_url": EVENTS_URL,
                        "props": [("event_date", clean(row.get("fecha")), "string"), ("hours", clean(row.get("horario")), "string"),
                                  ("capacity", clean(row.get("capacidad")), "number"), ("venue", clean(row.get("predio")), "string"),
                                  ("address", clean(row.get("domicilio")), "string"), ("permit_number", clean(row.get("disposicion_autorizante")), "string")]})

    print(f"Candidatos oficiales: {len(candidates)}")
    if not args.write:
        print("Dry-run: no se escribió nada. Use --write tras revisar la muestra.")
        return
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        await ingest(conn, source_id, candidates)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
