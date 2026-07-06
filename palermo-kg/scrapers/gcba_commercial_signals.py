"""
Scraper: BA Data GCBA - senales comerciales no inmobiliarias
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV/GeoJSON sin autenticacion.

Datasets:
  - Habilitaciones aprobadas AGC 2026, filtradas por Comuna 14
  - Mapa de Oportunidades Comerciales (MOC), zonas por geometria Palermo
  - Calzada gastronomica, calles habilitadas para decks en Palermo
  - Permisos de uso de espacio publico gastronomico, filtrados por Palermo

No carga listings inmobiliarios ni precios residenciales.
"""

import asyncio
import csv
import io
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import (
    bulk_get_or_create_entities,
    bulk_upsert_properties,
    get_conn,
    get_source_id,
)
from scrapers.shared.normalizer import normalize_name, normalize_value

LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390

HABILITACIONES_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "agencia-gubernamental-de-control/habilitaciones-aprobadas/"
    "habilitaciones-aprobadas2026.csv"
)
MOC_ZONAS_GEOJSON_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "innovacion-transformacion-digital/mapa-oportunidades-comerciales-moc/"
    "zonas-moc.geojson"
)
MOC_ZONAS_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "innovacion-transformacion-digital/mapa-oportunidades-comerciales-moc/zonas.csv"
)
MOC_RUBROS_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "innovacion-transformacion-digital/mapa-oportunidades-comerciales-moc/rubros.csv"
)
MOC_DEMOGRAFIA_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "innovacion-transformacion-digital/mapa-oportunidades-comerciales-moc/demografia.csv"
)
DECKS_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "transporte-y-obras-publicas/calzada-gastronomica/"
    "decks_permitidos_WGS84.csv"
)
PERMISOS_GASTRO_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "atencion-ciudadana/permisos-uso-espacio-publico-area-gastronomica/"
    "permisos-uso-espacio-publico-gastronomicos.csv"
)


def clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "s/d", "sd", "n/a", "nan", "-", "NULL".lower()}:
        return ""
    return value


def strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def normalized_key(value: str) -> str:
    value = strip_accents(clean(value)).lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def parse_float(value: Any) -> float | None:
    value = clean(value).replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
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
    coords = re.findall(r"([-\d.]+)\s+([-\d.]+)", clean(wkt))
    if not coords:
        return None, None
    lats, lngs = [], []
    for lng_raw, lat_raw in coords:
        lat = parse_float(lat_raw)
        lng = parse_float(lng_raw)
        if lat is not None and lng is not None:
            lats.append(lat)
            lngs.append(lng)
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def geojson_centroid(geometry: dict) -> tuple[float | None, float | None]:
    coords = (geometry or {}).get("coordinates") or []

    def points(node):
        if not node:
            return []
        if isinstance(node[0], (int, float)):
            return [node]
        out = []
        for item in node:
            out.extend(points(item))
        return out

    pts = points(coords)
    lats = [p[1] for p in pts if len(p) >= 2]
    lngs = [p[0] for p in pts if len(p) >= 2]
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def value_type_for(key: str, value: str) -> tuple[str, str]:
    if key.endswith("_url"):
        return "url", value
    number = parse_float(value)
    numeric_markers = (
        "cantidad", "precio", "superficie", "indice", "nivel", "poblacion",
        "facturacion", "hogares", "comuna", "altura", "partida",
    )
    if number is not None and any(marker in key for marker in numeric_markers):
        return "number", str(int(number)) if number == int(number) else str(number)
    return "string", normalize_value(value)


async def fetch_csv(client: httpx.AsyncClient, url: str, delimiter: str = ";") -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


async def fetch_geojson(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def upsert_candidates(conn, source_id: str, candidates: list[dict], chunk_size: int = 500) -> int:
    total = 0
    for i in range(0, len(candidates), chunk_size):
        chunk = candidates[i:i + chunk_size]
        entity_records = [
            {
                "name": c["name"],
                "entity_type": c["entity_type"],
                "subtype": c["subtype"],
                "lat": c.get("lat"),
                "lng": c.get("lng"),
                "origin_url": c["origin_url"],
            }
            for c in chunk
        ]
        ids_by_name = await bulk_get_or_create_entities(conn, entity_records)
        prop_records = []
        for c in chunk:
            entity_id = ids_by_name.get(c["name"])
            if not entity_id:
                continue
            for key, raw_value in c["props"].items():
                raw_value = clean(raw_value)
                if not raw_value:
                    continue
                vtype, value = value_type_for(key, raw_value)
                prop_records.append({
                    "entity_id": entity_id,
                    "key": key,
                    "value": value,
                    "value_type": vtype,
                    "confidence": 0.95,
                    "origins": [c["origin_url"]],
                })
        await bulk_upsert_properties(conn, prop_records, source_id)
        total += len(chunk)
        if len(candidates) > chunk_size:
            print(f"    Cargadas {total}/{len(candidates)} entidades...")
    return total


async def ingest_habilitaciones(conn, source_id: str, client: httpx.AsyncClient) -> int:
    print("-> Habilitaciones aprobadas AGC 2026...")
    rows = await fetch_csv(client, HABILITACIONES_URL, delimiter=";")
    candidates = []
    seen = set()
    for row in rows:
        if clean(row.get("comuna")) != "14":
            continue
        razon = normalize_name(row.get("razon_social"))
        rubro = normalize_value(row.get("rubro"))
        domicilio = normalize_value(row.get("domicilio"))
        if not razon or not domicilio:
            continue
        key = (razon, rubro, domicilio, clean(row.get("disposicion")))
        if key in seen:
            continue
        seen.add(key)
        name = normalize_name(f"{razon} - {rubro[:70]} ({domicilio})")
        candidates.append({
            "name": name,
            "entity_type": "Organization",
            "subtype": "comercio_habilitado",
            "origin_url": HABILITACIONES_URL,
            "props": {
                "legal_name": razon,
                "business_activity": rubro,
                "address": domicilio,
                "commune": "14",
                "postal_code": clean(row.get("cod_postal_titular")),
                "property_parcel_id": clean(row.get("nropartidamatriz")),
                "phone": clean(row.get("telefono")),
                "disposition": clean(row.get("disposicion")),
                "comments": clean(row.get("comentarios"))[:1000],
            },
        })

    print(f"  {len(candidates)} habilitaciones de Comuna 14")
    return await upsert_candidates(conn, source_id, candidates, chunk_size=500)


async def ingest_moc(conn, source_id: str, client: httpx.AsyncClient) -> int:
    print("-> Mapa de Oportunidades Comerciales (MOC)...")
    geojson = await fetch_geojson(client, MOC_ZONAS_GEOJSON_URL)
    zone_coords = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        zone_id = clean(props.get("zone_id") or props.get("MOC_ZONAS_ID"))
        lat, lng = geojson_centroid(feature.get("geometry"))
        if zone_id and valid_lat_lng(lat, lng):
            zone_coords[zone_id] = (lat, lng)

    zonas = {clean(r.get("MOC_ZONAS_ID")): r for r in await fetch_csv(client, MOC_ZONAS_URL)}
    rubros = await fetch_csv(client, MOC_RUBROS_URL)
    demografia = await fetch_csv(client, MOC_DEMOGRAFIA_URL)

    rubros_by_zone: dict[str, list[dict]] = {}
    for row in rubros:
        zid = clean(row.get("MOC_ZONAS_ID"))
        if zid in zone_coords:
            rubros_by_zone.setdefault(zid, []).append(row)

    demo_by_zone: dict[str, dict[str, int]] = {}
    for row in demografia:
        zid = clean(row.get("MOC_ZONAS_ID"))
        if zid not in zone_coords:
            continue
        bucket = demo_by_zone.setdefault(zid, {"living": 0, "working": 0})
        bucket["living"] += int(parse_float(row.get("POBLACION_VIVIENTE")) or 0)
        bucket["working"] += int(parse_float(row.get("POBLACION_TRABAJADORA")) or 0)

    candidates = []
    for zone_id, (lat, lng) in zone_coords.items():
        row = zonas.get(zone_id, {})
        props = {
            "moc_zone_id": zone_id,
            "floating_population_level": clean(row.get("POBLACION_FLOTANTE")),
            "living_population": clean(row.get("POBLACION_VIVIENTE")) or str(demo_by_zone.get(zone_id, {}).get("living", "")),
            "working_population": clean(row.get("POBLACION_TRABAJADORA")) or str(demo_by_zone.get(zone_id, {}).get("working", "")),
            "households": clean(row.get("CANTIDAD_HOGARES")),
            "predominant_activity": clean(row.get("RUBRO_PREDOMINANTE")),
            "least_predominant_activity": clean(row.get("RUBRO_MENOS_PREDOMINANTE")),
            "avg_business_rent": clean(row.get("PRECIO_PROMEDIO_ALQUILER_LOCAL")),
            "avg_business_sale_price": clean(row.get("PRECIO_PROMEDIO_VENTA_LOCAL")),
            "avg_business_area_m2": clean(row.get("SUPERFICIE_M2_PROMEDIO_ALQUILER")),
            "snapshot_date": clean(row.get("FECHA")),
        }

        ranked = sorted(
            rubros_by_zone.get(zone_id, []),
            key=lambda r: parse_float(r.get("INDICE_CRECIMIENTO")) or -999,
            reverse=True,
        )
        for idx, rubro_row in enumerate(ranked[:5], start=1):
            prefix = f"top_growth_activity_{idx}"
            props[prefix] = clean(rubro_row.get("RUBRO"))
            props[f"{prefix}_growth_index"] = clean(rubro_row.get("INDICE_CRECIMIENTO"))
            props[f"{prefix}_risk_level"] = clean(rubro_row.get("NIVEL_RIESGO"))
            props[f"{prefix}_opening_index"] = clean(rubro_row.get("INDICE_APERTURA"))
            props[f"{prefix}_closing_index"] = clean(rubro_row.get("INDICE_CIERRE"))

        candidates.append({
            "name": f"Zona Comercial MOC {zone_id} - Palermo",
            "entity_type": "Location",
            "subtype": "moc_zona_comercial",
            "lat": lat,
            "lng": lng,
            "origin_url": MOC_ZONAS_GEOJSON_URL,
            "props": props,
        })

    print(f"  {len(candidates)} zonas MOC con centroide en Palermo")
    return await upsert_candidates(conn, source_id, candidates, chunk_size=200)


async def ingest_decks(conn, source_id: str, client: httpx.AsyncClient) -> int:
    print("-> Calzada gastronomica (decks permitidos)...")
    rows = await fetch_csv(client, DECKS_URL, delimiter=",")
    candidates = []
    for row in rows:
        barrio = strip_accents(clean(row.get("BARRIO"))).upper()
        comuna = strip_accents(clean(row.get("COMUNA"))).upper()
        if "PALERMO" not in barrio and comuna != "COMUNA 14":
            continue
        lat, lng = parse_wkt_centroid(row.get("WKT"))
        street = normalize_value(row.get("nomoficial"))
        if not street:
            continue
        alt_ini = clean(row.get("alt_derini") or row.get("alt_izqini"))
        alt_fin = clean(row.get("alt_derfin") or row.get("alt_izqfin"))
        name = normalize_name(f"Deck gastronómico permitido - {street} {alt_ini}-{alt_fin}")
        candidates.append({
            "name": name,
            "entity_type": "Location",
            "subtype": "deck_gastronomico",
            "lat": lat,
            "lng": lng,
            "origin_url": DECKS_URL,
            "props": {
                "street": street,
                "from_address_number": alt_ini,
                "to_address_number": alt_fin,
                "neighborhood": "Palermo",
                "commune": "14",
            },
        })

    print(f"  {len(candidates)} tramos habilitados para decks en Palermo")
    return await upsert_candidates(conn, source_id, candidates, chunk_size=500)


async def ingest_permisos_gastro(conn, source_id: str, client: httpx.AsyncClient) -> int:
    print("-> Permisos de uso de espacio publico gastronomico...")
    rows = await fetch_csv(client, PERMISOS_GASTRO_URL, delimiter=";")
    candidates = []
    seen = set()
    for row in rows:
        barrio = strip_accents(clean(row.get("Barrio"))).upper()
        comuna = clean(row.get("Comuna"))
        if "PALERMO" not in barrio and comuna != "14":
            continue
        solicitante = normalize_name(row.get("SOLICITANTE"))
        street = normalize_value(row.get("Direcci\uFFFDn") or row.get("Dirección"))
        altura = clean(row.get("Altura"))
        expediente = clean(row.get("Expediente"))
        if not solicitante or not street:
            continue
        key = (solicitante, street, altura, expediente)
        if key in seen:
            continue
        seen.add(key)
        name = normalize_name(f"Permiso gastronómico {solicitante} - {street} {altura}")
        candidates.append({
            "name": name,
            "entity_type": "Organization",
            "subtype": "permiso_gastronomico",
            "origin_url": PERMISOS_GASTRO_URL,
            "props": {
                "applicant": solicitante,
                "document_type": clean(row.get("TIPO_DOCUMENTO")),
                "document_id": clean(row.get("DNI/CUIT")),
                "address": f"{street} {altura}".strip(),
                "street": street,
                "street_number": altura,
                "neighborhood": "Palermo",
                "commune": "14",
                "sidewalk_status": clean(row.get("Estado Vereda")),
                "resolution": clean(row.get("N\uFFFD de Dispo / Reso") or row.get("N° de Dispo / Reso")),
                "start_date": clean(row.get("Fecha de Inicio")),
                "end_date": clean(row.get("Fecha de Vencimiento")),
                "year": clean(row.get("A\uFFFDO") or row.get("AÑO")),
                "case_number": expediente,
            },
        })

    print(f"  {len(candidates)} permisos gastronomicos en Palermo")
    return await upsert_candidates(conn, source_id, candidates, chunk_size=500)


async def main():
    print("=== Scraper GCBA Senales Comerciales ===")
    selected = set(sys.argv[1:])
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        total = 0
        async with httpx.AsyncClient(follow_redirects=True, timeout=180) as client:
            jobs = {
                "habilitaciones": ingest_habilitaciones,
                "moc": ingest_moc,
                "decks": ingest_decks,
                "permisos_gastro": ingest_permisos_gastro,
            }
            for name, func in jobs.items():
                if selected and name not in selected:
                    continue
                total += await func(conn, source_id, client)
                await asyncio.sleep(0.5)
        print(f"\nTotal: {total} entidades insertadas/actualizadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
