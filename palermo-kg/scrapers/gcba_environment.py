"""
Scraper: BA Data GCBA - datos ambientales y de arbolado
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV/GeoJSON sin autenticacion.

Datasets:
  - Estaciones de calidad de aire
  - Sitios posibles de anegamiento
  - Mapa de ruido (diurno / nocturno)
  - Arbolado publico lineal (filtrado por Comuna 14)
  - Arbolado en espacios verdes (filtrado por bounding box)
"""

import asyncio
import csv
import io
import re
import sys
from pathlib import Path
from typing import Any

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

LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390

def clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "s/d", "sd", "n/a", "nan", "-"}:
        return ""
    return value

def parse_float(value: Any) -> float | None:
    val = clean(value).replace(",", ".")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None

def valid_lat_lng(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None
        and lng is not None
        and LAT_MIN <= lat <= LAT_MAX
        and LNG_MIN <= lng <= LNG_MAX
    )

def parse_wkt_centroid(wkt: str) -> tuple[float | None, float | None]:
    if not wkt:
        return None, None
    coords = re.findall(r"([-\d.]+)\s+([-\d.]+)", wkt)
    if not coords:
        return None, None
    lats = []
    lngs = []
    for lng_str, lat_str in coords:
        lat = parse_float(lat_str)
        lng = parse_float(lng_str)
        if lat is not None and lng is not None:
            lats.append(lat)
            lngs.append(lng)
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lngs) / len(lngs)

def parse_geojson_centroid(geometry: dict) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coords = geometry.get("coordinates", [])
    
    # Flatten geometry to find all points
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

async def fetch_csv(client: httpx.AsyncClient, url: str, delimiter: str = ",") -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))

async def fetch_geojson(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()

# ─── 1. Ingesta: Estaciones de Calidad de Aire ──────────────────────────────
async def ingest_air_stations(conn, source_id: str, client: httpx.AsyncClient):
    print("-> Procesando Estaciones de Calidad de Aire...")
    url = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/calidad-aire/estaciones-ambientales.csv"
    try:
        rows = await fetch_csv(client, url, delimiter=";")
    except Exception as exc:
        print(f"  ERROR descargando calidad de aire: {exc}")
        return 0

    candidates = []
    for row in rows:
        lat = parse_float(row.get("lat"))
        lng = parse_float(row.get("long"))
        nombre = clean(row.get("nombre"))
        
        # Filtro por bounding box o nombre
        if not (valid_lat_lng(lat, lng) or "PALERMO" in nombre.upper()):
            continue
            
        candidates.append({
            "name": f"Estación de Monitoreo Calidad del Aire - {nombre.title()}",
            "entity_type": "Facility",
            "subtype": "estacion_ambiental",
            "lat": lat,
            "lng": lng,
            "origin_url": url,
            "props": {
                "address": clean(row.get("direccion")),
                "status": "Activa" if clean(row.get("en_red")) else "Inactiva",
                "parameters_measured": clean(row.get("parametrios_medidos")),
                "comuna": "14" if "PALERMO" in nombre.upper() else clean(row.get("comuna")),
                "start_date": clean(row.get("inicio_de_actividad"))
            }
        })

    if not candidates:
        print("  Sin estaciones en Palermo.")
        return 0

    entity_records = [{k: c[k] for k in ["name", "entity_type", "subtype", "lat", "lng", "origin_url"]} for c in candidates]
    ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

    prop_records = []
    for c in candidates:
        entity_id = ids_by_name.get(c["name"])
        if not entity_id:
            continue
        for key, val in c["props"].items():
            if not val:
                continue
            prop_records.append({
                "entity_id": entity_id,
                "key": key,
                "value": normalize_value(val),
                "value_type": "number" if key in ("comuna",) else "string",
                "confidence": 0.95,
                "origins": [url]
            })

    await bulk_upsert_properties(conn, prop_records, source_id)
    print(f"  OK: {len(candidates)} estaciones de calidad de aire ingresadas.")
    return len(candidates)

# ─── 2. Ingesta: Sitios Posibles de Anegamiento ──────────────────────────────
async def ingest_floods(conn, source_id: str, client: httpx.AsyncClient):
    print("-> Procesando Sitios de Anegamiento...")
    url = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/sitios-posibles-anegamiento/sitios-pasibles-de-anegamiento-por-precipitacion-2019.csv"
    try:
        rows = await fetch_csv(client, url, delimiter=",")
    except Exception as exc:
        print(f"  ERROR descargando anegamiento: {exc}")
        return 0

    candidates = []
    for row in rows:
        comuna = clean(row.get("Comuna"))
        if comuna != "14":  # Palermo es Comuna 14
            continue
            
        wkt = row.get("WKT", "")
        lat, lng = parse_wkt_centroid(wkt)
        fid = clean(row.get("Id"))
        clasif = clean(row.get("Clasif"))
        
        name = f"Área de Anegamiento {fid} ({clasif})"
        candidates.append({
            "name": name,
            "entity_type": "Location",
            "subtype": "punto_anegamiento",
            "lat": lat,
            "lng": lng,
            "origin_url": url,
            "props": {
                "comuna": "14",
                "classification": clasif,
                "source_id_ref": fid
            }
        })

    if not candidates:
        print("  Sin zonas de anegamiento en Palermo.")
        return 0

    entity_records = [{k: c[k] for k in ["name", "entity_type", "subtype", "lat", "lng", "origin_url"]} for c in candidates]
    ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

    prop_records = []
    for c in candidates:
        entity_id = ids_by_name.get(c["name"])
        if not entity_id:
            continue
        for key, val in c["props"].items():
            if not val:
                continue
            prop_records.append({
                "entity_id": entity_id,
                "key": key,
                "value": normalize_value(val),
                "value_type": "number" if key in ("comuna", "source_id_ref") else "string",
                "confidence": 0.95,
                "origins": [url]
            })

    await bulk_upsert_properties(conn, prop_records, source_id)
    print(f"  OK: {len(candidates)} zonas de anegamiento ingresadas.")
    return len(candidates)

# ─── 3. Ingesta: Mapa de Ruido ───────────────────────────────────────────────
async def ingest_noise_map(conn, source_id: str, client: httpx.AsyncClient):
    print("-> Procesando Mapa de Ruido...")
    datasets = [
        {"periodo": "Diurno", "url": "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_diurno.geojson"},
        {"periodo": "Nocturno", "url": "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_nocturno.geojson"}
    ]

    total = 0
    for ds in datasets:
        periodo = ds["periodo"]
        url = ds["url"]
        print(f"  Descargando ruido {periodo.lower()}...")
        try:
            geojson = await fetch_geojson(client, url)
        except Exception as exc:
            print(f"    ERROR descargando mapa de ruido ({periodo}): {exc}")
            continue

        features = geojson.get("features", [])
        candidates = []
        for feat in features:
            props = feat.get("properties") or {}
            comuna = clean(props.get("comuna", ""))
            
            # Filtrar por Comuna 14 (Palermo)
            if "14" not in comuna:
                continue
                
            lat, lng = parse_geojson_centroid(feat.get("geometry"))
            fid = clean(props.get("id"))
            rango = clean(props.get("rango"))
            
            name = f"Zona de Ruido {periodo} {rango} (ID: {fid}) - Comuna 14"
            candidates.append({
                "name": name,
                "entity_type": "Facility",
                "subtype": "zona_ruido",
                "lat": lat,
                "lng": lng,
                "origin_url": url,
                "props": {
                    "dba_low": clean(props.get("dba_low")),
                    "dba_high": clean(props.get("dba_high")),
                    "rango": rango,
                    "periodo": periodo,
                    "comuna": "14",
                    "color": clean(props.get("color"))
                }
            })

        if not candidates:
            print(f"    Sin zonas de ruido {periodo.lower()} en Palermo.")
            continue

        entity_records = [{k: c[k] for k in ["name", "entity_type", "subtype", "lat", "lng", "origin_url"]} for c in candidates]
        ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

        prop_records = []
        for c in candidates:
            entity_id = ids_by_name.get(c["name"])
            if not entity_id:
                continue
            for key, val in c["props"].items():
                if not val:
                    continue
                prop_records.append({
                    "entity_id": entity_id,
                    "key": key,
                    "value": normalize_value(val),
                    "value_type": "number" if key in ("dba_low", "dba_high", "comuna") else "string",
                    "confidence": 0.95,
                    "origins": [url]
                })

        await bulk_upsert_properties(conn, prop_records, source_id)
        print(f"    OK: {len(candidates)} zonas de ruido {periodo.lower()} ingresadas.")
        total += len(candidates)
        await asyncio.sleep(0.5)

    return total

# ─── 4. Ingesta: Arbolado Publico Lineal ─────────────────────────────────────
async def ingest_street_trees(conn, source_id: str, client: httpx.AsyncClient, limit: int = None):
    print("-> Procesando Arbolado Público Lineal...")
    url = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/atencion-ciudadana/arbolado-publico-lineal/arbolado-publico-lineal-2017-2018.csv"
    try:
        rows = await fetch_csv(client, url, delimiter=",")
    except Exception as exc:
        print(f"  ERROR descargando arbolado lineal: {exc}")
        return 0

    print(f"  {len(rows)} filas totales leídas. Filtrando Comuna 14...")
    
    candidates = []
    for row in rows:
        comuna = clean(row.get("comuna"))
        if comuna != "14":
            continue
            
        lat = parse_float(row.get("lat"))
        lng = parse_float(row.get("long"))
        nro_registro = clean(row.get("nro_registro"))
        species = clean(row.get("nombre_cientifico"))
        
        if not nro_registro or not species:
            continue

        name = f"Árbol {nro_registro} - {species}"
        candidates.append({
            "name": name,
            "entity_type": "Facility",
            "subtype": "arbol",
            "lat": lat,
            "lng": lng,
            "origin_url": url,
            "props": {
                "species": species,
                "address": clean(row.get("direccion_normalizada")),
                "street": clean(row.get("calle_nombre")),
                "street_number": clean(row.get("calle_chapa")),
                "diameter": clean(row.get("diametro_altura_pecho")),
                "height": clean(row.get("altura_arbol")),
                "comuna": "14"
            }
        })

    total_palermo = len(candidates)
    print(f"  {total_palermo} árboles encontrados en Palermo (Comuna 14).")
    
    if limit and total_palermo > limit:
        print(f"  Limitando carga a {limit} árboles para evitar saturación.")
        candidates = candidates[:limit]

    if not candidates:
        return 0

    # Ingestar en lotes de 500 para evitar queries gigantescas
    chunk_size = 500
    total_loaded = 0
    
    for i in range(0, len(candidates), chunk_size):
        chunk = candidates[i:i+chunk_size]
        entity_records = [{k: c[k] for k in ["name", "entity_type", "subtype", "lat", "lng", "origin_url"]} for c in chunk]
        ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

        prop_records = []
        for c in chunk:
            entity_id = ids_by_name.get(c["name"])
            if not entity_id:
                continue
            for key, val in c["props"].items():
                if not val:
                    continue
                prop_records.append({
                    "entity_id": entity_id,
                    "key": key,
                    "value": normalize_value(val),
                    "value_type": "number" if key in ("diameter", "height", "comuna", "street_number") else "string",
                    "confidence": 0.95,
                    "origins": [url]
                })

        await bulk_upsert_properties(conn, prop_records, source_id)
        total_loaded += len(chunk)
        print(f"    Cargados {total_loaded}/{len(candidates)} árboles lineales...")
        await asyncio.sleep(0.1)

    print(f"  OK: {total_loaded} árboles lineales ingresados.")
    return total_loaded

# ─── 5. Ingesta: Arbolado en Espacios Verdes ─────────────────────────────────
async def ingest_park_trees(conn, source_id: str, client: httpx.AsyncClient, limit: int = None):
    print("-> Procesando Arbolado en Espacios Verdes...")
    url = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/arbolado-espacios-verdes/arbolado-en-espacios-verdes.csv"
    try:
        rows = await fetch_csv(client, url, delimiter=",")
    except Exception as exc:
        print(f"  ERROR descargando arbolado de espacios verdes: {exc}")
        return 0

    print(f"  {len(rows)} filas totales leídas. Filtrando por Bounding Box...")

    candidates = []
    for row in rows:
        lat = parse_float(row.get("lat"))
        lng = parse_float(row.get("long"))
        
        # Filtrar por bounding box de Palermo
        if not valid_lat_lng(lat, lng):
            continue
            
        id_arbol = clean(row.get("id_arbol"))
        species = clean(row.get("nombre_cie"))
        espacio_verde = clean(row.get("espacio_ve"))
        
        if not id_arbol or not species:
            continue

        name = f"Árbol Espacio Verde {id_arbol} - {species} ({espacio_verde})"
        candidates.append({
            "name": name,
            "entity_type": "Facility",
            "subtype": "arbol_espacio_verde",
            "lat": lat,
            "lng": lng,
            "origin_url": url,
            "props": {
                "species": species,
                "common_name": clean(row.get("nombre_com")),
                "park_name": espacio_verde,
                "height": clean(row.get("altura_tot")),
                "diameter": clean(row.get("diametro")),
                "origin": clean(row.get("origen")),
                "comuna": "14"  # Por bounding box sabemos que cae en Palermo
            }
        })

    total_palermo = len(candidates)
    print(f"  {total_palermo} árboles de espacio verde encontrados en Palermo.")
    
    if limit and total_palermo > limit:
        print(f"  Limitando carga a {limit} árboles de parque para evitar saturación.")
        candidates = candidates[:limit]

    if not candidates:
        return 0

    # Ingestar en lotes de 500
    chunk_size = 500
    total_loaded = 0
    
    for i in range(0, len(candidates), chunk_size):
        chunk = candidates[i:i+chunk_size]
        entity_records = [{k: c[k] for k in ["name", "entity_type", "subtype", "lat", "lng", "origin_url"]} for c in chunk]
        ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

        prop_records = []
        for c in chunk:
            entity_id = ids_by_name.get(c["name"])
            if not entity_id:
                continue
            for key, val in c["props"].items():
                if not val:
                    continue
                prop_records.append({
                    "entity_id": entity_id,
                    "key": key,
                    "value": normalize_value(val),
                    "value_type": "number" if key in ("diameter", "height", "comuna") else "string",
                    "confidence": 0.95,
                    "origins": [url]
                })

        await bulk_upsert_properties(conn, prop_records, source_id)
        total_loaded += len(chunk)
        print(f"    Cargados {total_loaded}/{len(candidates)} árboles de espacio verde...")
        await asyncio.sleep(0.1)

    print(f"  OK: {total_loaded} árboles de espacio verde ingresados.")
    return total_loaded

# ─── Main Execution ──────────────────────────────────────────────────────────
async def main():
    print("=== Scraper GCBA Ambiente y Calidad Urbana ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        total = 0
        
        # Usamos un timeout más largo para soportar descargas de archivos grandes
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            # 1. Calidad de aire
            total += await ingest_air_stations(conn, source_id, client)
            await asyncio.sleep(1)
            
            # 2. Anegamiento
            total += await ingest_floods(conn, source_id, client)
            await asyncio.sleep(1)
            
            # 3. Ruido
            total += await ingest_noise_map(conn, source_id, client)
            await asyncio.sleep(1)
            
            # 4 y 5. Arbolado
            # NOTA: Limitamos la ingesta de árboles a 2000 por set para prevenir
            # saturación de almacenamiento y tiempo en la base de datos Neon (Plan Free).
            total += await ingest_street_trees(conn, source_id, client, limit=2000)
            await asyncio.sleep(1)
            total += await ingest_park_trees(conn, source_id, client, limit=2000)
            
        print(f"\n[OK] Scraper finalizado con exito. Total de registros procesados/cargados: {total}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
