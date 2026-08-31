"""
Scraper: BA Data GCBA - WiFi Público
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV sin autenticacion.

Dataset: puntos-wi-fi-publicos
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

SUPPORTS_SOURCE_CONTRACT = True

WIFI_CSV_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/puntos-wi-fi-publicos/sitios-de-wifi.csv"


def clean(value) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "s/d", "sd", "n/a", "nan"}:
        return ""
    return value


def parse_float(value):
    value = clean(value)
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def parse_args():
    parser = argparse.ArgumentParser(description="Scraper GCBA WiFi Publico (CABA)")
    add_source_arguments(parser)
    return parser.parse_args()


async def main():
    args = parse_args()
    print("=== Scraper GCBA WiFi Publico (CABA) ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        
        print(f"-> Descargando CSV de WiFi Publico...")
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            r = await client.get(WIFI_CSV_URL)
            r.raise_for_status()
            text = r.content.decode("utf-8-sig", "replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            
        print(f"  {len(rows)} filas descargadas en total.")
        
        candidates = []
        for row in rows:
            lat = parse_float(row.get("lat"))
            lng = parse_float(row.get("long"))
            if not record_in_scope(lat=lat, lng=lng,
                                   row_neighborhood=clean(row.get("barrio")),
                                   row_commune=clean(row.get("comuna")),
                                   scope=args.scope,
                                   neighborhood=args.neighborhood,
                                   commune=args.commune):
                continue
                
            nombre_raw = clean(row.get("nombre"))
            if not nombre_raw:
                continue
                
            # Nombre descriptivo canonico
            nombre_canonico = normalize_name(f"WiFi Publico - {nombre_raw}")
            
            calle = clean(row.get("calle_nombre"))
            altura = clean(row.get("calle_altura"))
            direccion = f"{calle} {altura}".strip() if calle and altura else clean(row.get("direccion_normalizada") or "")
            
            candidates.append({
                "name": nombre_canonico,
                "entity_type": "Facility",
                "subtype": "wifi_publico",
                "lat": lat,
                "lng": lng,
                "origin_url": WIFI_CSV_URL,
                "props": {
                    "address": (direccion, "string"),
                    "neighborhood": (clean(row.get("barrio")), "string"),
                    "commune": (clean(row.get("comuna")), "string"),
                    "wifi_type": (clean(row.get("tipo")), "string"),
                    "wifi_subcategory": (clean(row.get("subcategor")), "string"),
                    "status": (clean(row.get("estado")), "string"),
                    "source_id_ref": (clean(row.get("id")), "string"),
                }
            })
            
        candidates = bounded(candidates, args.limit)
        print(f"  {len(candidates)} puntos WiFi dentro de {args.scope}.")

        if not candidates:
            print("  Sin candidatos para insertar.")
            return

        if not args.write:
            print("Validación completada; usar --write para persistir.")
            return
            
        # Ingesta en lote
        entity_records = [
            {
                "name": c["name"],
                "entity_type": c["entity_type"],
                "subtype": c["subtype"],
                "lat": c["lat"],
                "lng": c["lng"],
                "origin_url": c["origin_url"]
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
                    "origins": [WIFI_CSV_URL]
                })
                
        await bulk_upsert_properties(conn, prop_records, source_id)
        await mark_source_synced(conn, source_id)
        print(f"  [OK] Ingesta WiFi Publico completada: {len(candidates)} puntos.")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
