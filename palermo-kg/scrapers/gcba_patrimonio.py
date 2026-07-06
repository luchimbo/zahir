"""
Scraper: BA Data GCBA - Patrimonio Histórico y Edificios Catalogados
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales GeoJSON sin autenticacion.

Dataset: areas-proteccion-historica
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import (
    get_conn,
    get_source_id,
    bulk_get_or_create_entities,
    bulk_upsert_properties,
)
from scrapers.shared.normalizer import normalize_name, normalize_value

APH_GEOJSON_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/areas-proteccion-historica/areas-proteccion-historica.geojson"

LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390  # Bounding box de Palermo


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


def valid_lat_lng(lat, lng) -> bool:
    return (
        lat is not None
        and lng is not None
        and LAT_MIN <= lat <= LAT_MAX
        and LNG_MIN <= lng <= LNG_MAX
    )


def parse_geojson_centroid(geometry: dict) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coords = geometry.get("coordinates", [])
    
    # Aplanar geometria para encontrar todos los puntos
    def extract_points(lst):
        pts = []
        if not lst:
            return pts
        if isinstance(lst[0], (int, float)):
            pts.append(lst)
        else:
            for item in lst:
                pts.extend(extract_points(item))
        return pts

    points = extract_points(coords)
    if not points:
        return None, None
    lats = [pt[1] for pt in points if len(pt) >= 2]
    lngs = [pt[0] for pt in points if len(pt) >= 2]
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def is_palermo(props: dict, lat, lng) -> bool:
    barrio = clean(props.get("BARRIOS", "")).upper()
    comuna = clean(props.get("COMUNA", ""))
    if "PALERMO" in barrio or comuna == "14" or comuna == "Comuna 14":
        return True
    return valid_lat_lng(lat, lng)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scraper Patrimonio Histórico CABA")
    parser.add_argument("--limit", type=int, default=2000,
                        help="Límite de registros a cargar para evitar saturar Neon (default: 2000)")
    args = parser.parse_args()

    print("=== Scraper GCBA Patrimonio Historico ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        
        print("-> Descargando GeoJSON de Patrimonio Historico...")
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(APH_GEOJSON_URL)
            r.raise_for_status()
            data = r.json()
            
        features = data.get("features", [])
        print(f"  {len(features)} total features en CABA.")
        
        candidates = []
        for feat in features:
            props = feat.get("properties") or {}
            geometry = feat.get("geometry") or {}
            
            lat, lng = parse_geojson_centroid(geometry)
            if not is_palermo(props, lat, lng):
                continue
                
            direccion = clean(props.get("1_DIRECCIO") or "")
            if not direccion:
                calle = clean(props.get("1_CALLE") or "")
                altura = clean(props.get("1_ALTURA") or "")
                direccion = f"{calle} {altura}".strip()
                
            if not direccion:
                continue
                
            denom = clean(props.get("DENOMINACI") or "")
            
            # Nombre descriptivo canonico
            if denom:
                nombre_canonico = normalize_name(f"Patrimonio - {denom} ({direccion})")
            else:
                nombre_canonico = normalize_name(f"Patrimonio - {direccion}")
                
            candidates.append({
                "name": nombre_canonico,
                "entity_type": "Facility",
                "subtype": "edificio_catalogado",
                "lat": lat,
                "lng": lng,
                "origin_url": APH_GEOJSON_URL,
                "props": {
                    "address": (direccion, "string"),
                    "neighborhood": (clean(props.get("BARRIOS")), "string"),
                    "commune": (clean(props.get("COMUNA")), "string"),
                    "smp": (clean(props.get("SMP")), "string"),
                    "denomination": (denom, "string"),
                    "cataloging": (clean(props.get("CATALOGACI")), "string"),
                    "aph_area": (clean(props.get("APH_NRO_Y_")), "string"),
                    "protection_level": (clean(props.get("PROTECCION")), "string"),
                    "status": (clean(props.get("ESTADO")), "string"),
                    "law_3056": (clean(props.get("LEY_3056")), "string"),
                }
            })
            
        total_found = len(candidates)
        print(f"  {total_found} edificios patrimoniales encontrados en Palermo.")
        
        if args.limit and total_found > args.limit:
            print(f"  Limitando la ingesta a los primeros {args.limit} registros para cuidar la DB.")
            candidates = candidates[:args.limit]
            
        if not candidates:
            print("  Sin registros para ingresar.")
            return
            
        # Ingesta por lotes
        chunk_size = 500
        for i in range(0, len(candidates), chunk_size):
            chunk = candidates[i : i + chunk_size]
            
            entity_records = [
                {
                    "name": c["name"],
                    "entity_type": c["entity_type"],
                    "subtype": c["subtype"],
                    "lat": c["lat"],
                    "lng": c["lng"],
                    "origin_url": c["origin_url"]
                }
                for c in chunk
            ]
            
            ids_by_name = await bulk_get_or_create_entities(conn, entity_records)
            
            prop_records = []
            for c in chunk:
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
                        "origins": [APH_GEOJSON_URL]
                    })
                    
            await bulk_upsert_properties(conn, prop_records, source_id)
            print(f"    Ingestados {i + len(chunk)}/{len(candidates)}...")
            await asyncio.sleep(0.1)
            
        print(f"  [OK] Ingesta Patrimonio Historico completada con éxito.")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
