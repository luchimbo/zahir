"""
Scraper: BA Data GCBA - Obras Públicas y Privadas
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV sin autenticacion.

Datasets:
  - Obras Registradas (Obras privadas registradas / DGROC)
  - BA Obras (Obras públicas / Observatorio)
"""

import asyncio
import csv
import io
import re
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
    mark_source_synced,
)
from scrapers.shared.normalizer import normalize_name, normalize_value

OBRAS_REGISTRADAS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/obras-registradas/obrasregistradas-acumulado.csv"
BA_OBRAS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-legal-y-tecnica/ba-obras/dataset_ba_obras_actualizado.csv"

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


def parse_wkt_point(wkt: str) -> tuple[float | None, float | None]:
    """Extrae lat y lng de un WKT tipo POINT(lng lat)."""
    if not wkt:
        return None, None
    m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", wkt, re.IGNORECASE)
    if m:
        lng = parse_float(m.group(1))
        lat = parse_float(m.group(2))
        return lat, lng
    return None, None


# ── Ingesta: Obras Registradas (Privadas) ────────────────────────────────────

async def scrape_obras_privadas(conn, source_id: str, client: httpx.AsyncClient, limit: int = 1000) -> int:
    print("-> Procesando Obras Registradas (Privadas)...")
    try:
        r = await client.get(OBRAS_REGISTRADAS_URL)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig", "replace")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    except Exception as exc:
        print(f"  ERROR descargando obras registradas: {exc}")
        return 0

    print(f"  {len(rows)} filas leídas.")
    candidates = []
    
    for row in rows:
        lat = None
        lng = None
        
        # Intentar sacar lat/lng de wkt_2 o wkt_1
        wkt = row.get("wkt_2") or row.get("wkt_1") or ""
        if wkt:
            lat, lng = parse_wkt_point(wkt)
            
        barrio = clean(row.get("barrio", "")).upper()
        comuna = clean(row.get("comuna", "")).upper()
        
        is_p = "PALERMO" in barrio or "14" in comuna
        if not is_p and not valid_lat_lng(lat, lng):
            continue
            
        expediente = clean(row.get("expediente"))
        ubicacion = clean(row.get("ubicacion"))
        if not expediente or not ubicacion:
            continue
            
        name = normalize_name(f"Obra Registrada - {ubicacion} ({expediente})")
        candidates.append({
            "name": name,
            "entity_type": "Facility",
            "subtype": "obra_privada",
            "lat": lat,
            "lng": lng,
            "origin_url": OBRAS_REGISTRADAS_URL,
            "props": {
                "address": (ubicacion, "string"),
                "permit_number": (expediente, "string"),
                "description": (clean(row.get("descripcio")), "string"),
                "neighborhood": (clean(row.get("barrio")), "string"),
                "commune": (clean(row.get("comuna")), "string"),
                "smp": (clean(row.get("smp")), "string"),
                "date": (clean(row.get("fecha")), "string"),
            }
        })
        
    total_found = len(candidates)
    print(f"  {total_found} obras privadas encontradas en Palermo.")
    if limit and total_found > limit:
        print(f"  Limitando carga a {limit} obras privadas.")
        candidates = candidates[:limit]

    if not candidates:
        return 0

    # Ingestar por lotes
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
                    "origins": [OBRAS_REGISTRADAS_URL]
                })
        await bulk_upsert_properties(conn, prop_records, source_id)
        print(f"    Ingestadas {i + len(chunk)}/{len(candidates)} privadas...")
        await asyncio.sleep(0.1)

    return len(candidates)


# ── Ingesta: BA Obras (Públicas) ─────────────────────────────────────────────

async def scrape_obras_publicas(conn, source_id: str, client: httpx.AsyncClient, limit: int = 1000) -> int:
    print("-> Procesando BA Obras (Públicas)...")
    try:
        r = await client.get(BA_OBRAS_URL)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig", "replace")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    except Exception as exc:
        print(f"  ERROR descargando ba obras: {exc}")
        return 0

    print(f"  {len(rows)} filas leídas.")
    candidates = []
    
    for row in rows:
        lat = parse_float(row.get("LATITUD"))
        lng = parse_float(row.get("LONGITUD"))
        
        obra_nombre = clean(row.get("\ufeffOBRA_NOMBRE") or row.get("OBRA_NOMBRE"))
        calle = clean(row.get("CALLE"))
        
        # Filtro de pertenencia a Palermo
        is_p = (
            valid_lat_lng(lat, lng)
            or "PALERMO" in obra_nombre.upper()
            or "PALERMO" in calle.upper()
        )
        if not is_p:
            continue
            
        if not obra_nombre:
            continue
            
        name = normalize_name(f"Obra Publica - {obra_nombre}")
        
        # Dirección armada
        numero = clean(row.get("NUMERO"))
        direccion = f"{calle} {numero}".strip() if calle and numero else calle
        
        candidates.append({
            "name": name,
            "entity_type": "Facility",
            "subtype": "obra_publica",
            "lat": lat,
            "lng": lng,
            "origin_url": BA_OBRAS_URL,
            "props": {
                "address": (direccion, "string"),
                "status": (clean(row.get("ESTADO_OBRA")), "string"),
                "progress": (clean(row.get("AVANCE_FISICO_PCT")), "string"),
                "budget": (clean(row.get("MONTO_DEFINITIVO")), "string"),
                "contractor": (clean(row.get("RAZON_SOCIAL")), "string"),
                "contractor_cuit": (clean(row.get("CUIT")), "string"),
                "start_date": (clean(row.get("FECHA_INICIO")), "string"),
                "end_date": (clean(row.get("FECHA_FIN")), "string"),
                "jurisdiction": (clean(row.get("NOMBRE_JURISDICCION")), "string"),
                "permit_number": (clean(row.get("NUMERO_EXPEDIENTE")), "string"),
            }
        })
        
    total_found = len(candidates)
    print(f"  {total_found} obras públicas encontradas en Palermo.")
    if limit and total_found > limit:
        print(f"  Limitando carga a {limit} obras públicas.")
        candidates = candidates[:limit]

    if not candidates:
        return 0

    # Ingestar por lotes
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
                    "origins": [BA_OBRAS_URL]
                })
        await bulk_upsert_properties(conn, prop_records, source_id)
        print(f"    Ingestadas {i + len(chunk)}/{len(candidates)} públicas...")
        await asyncio.sleep(0.1)

    return len(candidates)


# ── Main Execution ──────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scraper GCBA Obras")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Límite de registros a cargar por cada dataset (default: 1000)")
    args = parser.parse_args()

    print("=== Scraper GCBA Obras ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            total_priv = await scrape_obras_privadas(conn, source_id, client, limit=args.limit)
            await asyncio.sleep(1)
            total_pub = await scrape_obras_publicas(conn, source_id, client, limit=args.limit)
        await mark_source_synced(conn, source_id)
            
        print(f"\n[OK] Scraper Obras finalizado con éxito. Total: {total_priv + total_pub} obras.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
