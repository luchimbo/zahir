"""
Scraper: BA Data GCBA - movilidad
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV/GeoJSON sin autenticacion.

Datasets:
  - Estaciones Ecobici
  - Estaciones de subte
  - Bocas de subte
  - Paradas de colectivo
  - Recorridos de colectivo que pasan por Palermo

No toca datos inmobiliarios.
"""

import asyncio
import csv
import io
import sys

import httpx

from scrapers.shared.db_helpers import (
    get_conn,
    get_or_create_entity,
    get_source_id,
    upsert_property,
)
from scrapers.shared.normalizer import normalize_name, normalize_value

CDN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets"

LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390

DATASETS = {
    "ecobici": {
        "kind": "csv",
        "url": f"{CDN}/transporte-y-obras-publicas/estaciones-bicicletas-publicas/nuevas-estaciones-bicicletas-publicas.csv",
    },
    "subte_estaciones": {
        "kind": "geojson",
        "url": f"{CDN}/sbase/subte-estaciones/estaciones_de_subte.geojson",
    },
    "bocas_subte": {
        "kind": "geojson",
        "url": f"{CDN}/sbase/bocas-subte/bocas-de-subte.geojson",
    },
    "colectivos_paradas": {
        "kind": "geojson",
        "url": f"{CDN}/transporte-y-obras-publicas/colectivos-paradas/paradas-de-colectivo.geojson",
    },
    "colectivos_recorridos": {
        "kind": "geojson",
        "url": f"{CDN}/transporte-y-obras-publicas/colectivos-recorridos/recorrido-colectivos.geojson",
    },
}

OFFSET = 0


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


def is_palermo_barrio(value: str) -> bool:
    barrio = (
        clean(value)
        .upper()
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
    )
    return "PALERMO" in barrio


def is_palermo_with_barrio_fallback(barrio_value: str, lat=None, lng=None) -> bool:
    barrio = clean(barrio_value)
    if barrio:
        return is_palermo_barrio(barrio)
    return valid_lat_lng(lat, lng)


def point_from_geometry(feature: dict):
    geometry = feature.get("geometry") or {}
    if geometry.get("type") != "Point":
        return None, None
    coords = geometry.get("coordinates") or []
    if len(coords) < 2:
        return None, None
    lng = parse_float(coords[0])
    lat = parse_float(coords[1])
    if valid_lat_lng(lat, lng):
        return lat, lng
    return None, None


def iter_line_points(coords):
    for item in coords or []:
        if not item:
            continue
        if isinstance(item[0], (int, float)) and len(item) >= 2:
            yield item
        else:
            yield from iter_line_points(item)


def first_palermo_point(feature: dict):
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"LineString", "MultiLineString"}:
        return None, None
    for lng_raw, lat_raw, *_ in iter_line_points(geometry.get("coordinates")):
        lng = parse_float(lng_raw)
        lat = parse_float(lat_raw)
        if valid_lat_lng(lat, lng):
            return lat, lng
    return None, None


async def fetch_csv(client: httpx.AsyncClient, url: str) -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text)))


async def fetch_features(client: httpx.AsyncClient, url: str) -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    return response.json().get("features", [])


async def set_props(conn, entity_id: str, source_id: str, origins: list[str], props: list[tuple[str, str, str]]):
    for key, value, value_type in props:
        value = clean(value)
        if not value:
            continue
        if value_type == "string":
            value = normalize_value(value)
        await upsert_property(
            conn,
            entity_id,
            key,
            value,
            value_type,
            source_id,
            origins=origins,
            confidence=0.95,
        )


async def scrape_ecobici(conn, source_id: str, client: httpx.AsyncClient) -> int:
    dataset = DATASETS["ecobici"]
    rows = await fetch_csv(client, dataset["url"])
    count = 0
    print(f"-> ecobici... {len(rows)} filas")
    for row in rows:
        lat = parse_float(row.get("latitud"))
        lng = parse_float(row.get("longitud"))
        if not is_palermo_with_barrio_fallback(row.get("barrio", ""), lat, lng):
            continue
        name = normalize_name(row.get("nombre", ""))
        if not name:
            continue
        entity_id = await get_or_create_entity(
            conn,
            name=f"Ecobici {name}",
            entity_type="Transport",
            subtype="ecobici",
            lat=lat,
            lng=lng,
            origin_url=dataset["url"],
        )
        await set_props(conn, entity_id, source_id, [dataset["url"]], [
            ("station_id", row.get("id", ""), "string"),
            ("station_number", row.get("numero_de_estacion", ""), "string"),
            ("address", row.get("direccion", ""), "string"),
            ("neighborhood", row.get("barrio", ""), "string"),
            ("commune", row.get("comuna", ""), "string"),
            ("placement", row.get("emplazamiento", ""), "string"),
        ])
        count += 1
    print(f"  OK: {count} estaciones Ecobici")
    return count


async def scrape_subte_estaciones(conn, source_id: str, client: httpx.AsyncClient) -> int:
    dataset = DATASETS["subte_estaciones"]
    features = await fetch_features(client, dataset["url"])
    count = 0
    print(f"-> subte_estaciones... {len(features)} features")
    for feature in features:
        props = feature.get("properties") or {}
        lat, lng = point_from_geometry(feature)
        if not valid_lat_lng(lat, lng):
            continue
        station = normalize_name(props.get("estacion", ""))
        line = clean(props.get("linea"))
        if not station or not line:
            continue
        entity_id = await get_or_create_entity(
            conn,
            name=f"Estacion {station} (Linea {line})",
            entity_type="Transport",
            subtype="estacion_subte",
            lat=lat,
            lng=lng,
            origin_url=dataset["url"],
            all_names=[station, f"Subte {station}"],
        )
        await set_props(conn, entity_id, source_id, [dataset["url"]], [
            ("station_id", props.get("id", ""), "string"),
            ("line", line, "string"),
        ])
        count += 1
    print(f"  OK: {count} estaciones de subte en Palermo")
    return count


async def scrape_bocas_subte(conn, source_id: str, client: httpx.AsyncClient) -> int:
    dataset = DATASETS["bocas_subte"]
    features = await fetch_features(client, dataset["url"])
    candidates = []
    for feature in features:
        props = feature.get("properties") or {}
        lat, lng = point_from_geometry(feature)
        if is_palermo_with_barrio_fallback(props.get("barrio", ""), lat, lng):
            candidates.append((feature, lat, lng))

    count = 0
    print(f"-> bocas_subte... {len(features)} features")
    print(f"  {len(candidates)} candidatas Palermo")
    if OFFSET:
        candidates = candidates[OFFSET:]
        print(f"  retomando desde {OFFSET}")
    for feature, lat, lng in candidates:
        props = feature.get("properties") or {}
        station = normalize_name(props.get("estacion", ""))
        line = clean(props.get("linea"))
        number = clean(props.get("numero_de_"))
        if not station:
            continue
        name = f"Boca Subte {station}" + (f" {number}" if number else "")
        entity_id = await get_or_create_entity(
            conn,
            name=name,
            entity_type="Transport",
            subtype="boca_subte",
            lat=lat,
            lng=lng,
            origin_url=dataset["url"],
        )
        address = " ".join(part for part in [clean(props.get("calle")), clean(props.get("altura"))] if part)
        await set_props(conn, entity_id, source_id, [dataset["url"]], [
            ("line", line, "string"),
            ("station", station, "string"),
            ("address", address, "string"),
            ("neighborhood", props.get("barrio", ""), "string"),
            ("commune", props.get("comuna", ""), "string"),
            ("destination", props.get("destino_bo", ""), "string"),
            ("has_escalator", props.get("escalera_m", ""), "string"),
            ("has_elevator", props.get("ascensor", ""), "string"),
            ("has_ramp", props.get("rampa", ""), "string"),
        ])
        count += 1
        if count % 25 == 0:
            print(f"  {count}/{len(candidates)} bocas procesadas...")
    print(f"  OK: {count} bocas de subte")
    return count


def collect_bus_lines(props: dict) -> list[str]:
    lines = []
    for i in range(1, 7):
        line = clean(props.get(f"L{i}"))
        direction = clean(props.get(f"l{i}_sen"))
        if line:
            lines.append(f"{line} {direction}".strip())
    return lines


async def scrape_colectivos_paradas(conn, source_id: str, client: httpx.AsyncClient) -> int:
    dataset = DATASETS["colectivos_paradas"]
    features = await fetch_features(client, dataset["url"])
    candidates = []
    for feature in features:
        props = feature.get("properties") or {}
        lat, lng = point_from_geometry(feature)
        if is_palermo_with_barrio_fallback(props.get("BARRIO", ""), lat, lng):
            candidates.append((feature, lat, lng))

    count = 0
    print(f"-> colectivos_paradas... {len(features)} features")
    print(f"  {len(candidates)} candidatas Palermo")
    if OFFSET:
        candidates = candidates[OFFSET:]
        print(f"  retomando desde {OFFSET}")
    for feature, lat, lng in candidates:
        props = feature.get("properties") or {}
        address = clean(props.get("DIRECCION"))
        lines = collect_bus_lines(props)
        if not address and not lines:
            continue
        line_label = ", ".join(line.split()[0] for line in lines[:3]) if lines else ""
        name = normalize_name(f"Parada Colectivo {line_label} - {address}".strip(" -"))
        entity_id = await get_or_create_entity(
            conn,
            name=name,
            entity_type="Transport",
            subtype="parada_colectivo",
            lat=lat,
            lng=lng,
            origin_url=dataset["url"],
        )
        await set_props(conn, entity_id, source_id, [dataset["url"]], [
            ("address", address, "string"),
            ("neighborhood", props.get("BARRIO", ""), "string"),
            ("commune", props.get("COMUNA", ""), "string"),
            ("bus_lines", " | ".join(lines), "string"),
            ("street", props.get("CALLE", ""), "string"),
            ("street_number", props.get("ALT PLANO", ""), "string"),
        ])
        count += 1
        if count % 100 == 0:
            print(f"  {count} paradas procesadas...")
    print(f"  OK: {count} paradas de colectivo")
    return count


async def scrape_colectivos_recorridos(conn, source_id: str, client: httpx.AsyncClient) -> int:
    dataset = DATASETS["colectivos_recorridos"]
    features = await fetch_features(client, dataset["url"])
    candidates = []
    for feature in features:
        lat, lng = first_palermo_point(feature)
        if valid_lat_lng(lat, lng):
            candidates.append((feature, lat, lng))

    count = 0
    print(f"-> colectivos_recorridos... {len(features)} features")
    print(f"  {len(candidates)} recorridos pasan por Palermo")
    if OFFSET:
        candidates = candidates[OFFSET:]
        print(f"  retomando desde {OFFSET}")
    for feature, lat, lng in candidates:
        props = feature.get("properties") or {}
        line = clean(props.get("linea"))
        route = clean(props.get("recorrido"))
        direction = clean(props.get("sentido"))
        if not line:
            continue
        name = normalize_name(f"Colectivo {line} {route} {direction}".strip())
        entity_id = await get_or_create_entity(
            conn,
            name=name,
            entity_type="Transport",
            subtype="recorrido_colectivo",
            lat=lat,
            lng=lng,
            origin_url=dataset["url"],
        )
        await set_props(conn, entity_id, source_id, [dataset["url"]], [
            ("line", line, "string"),
            ("route", route, "string"),
            ("direction", direction, "string"),
            ("modality", props.get("modalidad", ""), "string"),
            ("jurisdiction", props.get("jurisdicci", ""), "string"),
            ("from", props.get("desde", ""), "string"),
            ("to", props.get("hasta", ""), "string"),
        ])
        count += 1
        if count % 50 == 0:
            print(f"  {count}/{len(candidates)} recorridos procesados...")
    print(f"  OK: {count} recorridos que pasan por Palermo")
    return count


SCRAPERS = {
    "ecobici": scrape_ecobici,
    "subte_estaciones": scrape_subte_estaciones,
    "bocas_subte": scrape_bocas_subte,
    "colectivos_paradas": scrape_colectivos_paradas,
    "colectivos_recorridos": scrape_colectivos_recorridos,
}


async def main():
    global OFFSET
    print("=== Scraper GCBA Movilidad ===")
    selected = {arg for arg in sys.argv[1:] if not arg.isdigit()}
    OFFSET = next((int(arg) for arg in sys.argv[1:] if arg.isdigit()), 0)
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        total = 0
        async with httpx.AsyncClient(follow_redirects=True, timeout=90) as client:
            for name, scraper in SCRAPERS.items():
                if selected and name not in selected:
                    continue
                total += await scraper(conn, source_id, client)
                await asyncio.sleep(0.5)
        print(f"\nTotal: {total} entidades insertadas/actualizadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
