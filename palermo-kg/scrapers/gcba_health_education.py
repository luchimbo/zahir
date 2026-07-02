"""
Scraper: BA Data GCBA - salud y educacion
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV/GeoJSON sin autenticacion.

Datasets:
  - Farmacias
  - Hospitales
  - Centros de Salud y Accion Comunitaria (CESAC)
  - Centros de salud privados
  - Establecimientos educativos

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


DATASETS = [
    {
        "name": "farmacias",
        "kind": "geojson",
        "url": f"{CDN}/ministerio-de-salud/farmacias/farmacias.geojson",
        "entity_type": "Facility",
        "subtype": "farmacia",
        "name_keys": ["objeto"],
        "props": {
            "address": ["calle_nomb"],
            "street_number": ["altura"],
            "phone": ["telefono"],
            "neighborhood": ["barrio"],
            "commune": ["comuna"],
            "postal_code": ["codigo_pos", "codigo_p_1"],
        },
    },
    {
        "name": "hospitales",
        "kind": "geojson",
        "url": f"{CDN}/ministerio-de-salud/hospitales/hospitales.geojson",
        "entity_type": "Facility",
        "subtype": "hospital",
        "name_keys": ["nam", "fna"],
        "props": {
            "address": ["dir"],
            "neighborhood": ["bar"],
            "commune": ["com"],
            "phone": ["tel"],
            "website": ["web"],
            "specialty": ["esp"],
            "care_type": ["ate"],
        },
    },
    {
        "name": "cesac",
        "kind": "geojson",
        "url": f"{CDN}/ministerio-de-salud/centros-salud-accion-comunitaria-cesac/centros_salud_nivel_1_cesac.geojson",
        "entity_type": "Facility",
        "subtype": "cesac",
        "name_keys": ["nombre"],
        "props": {
            "address": ["direccion"],
            "neighborhood": ["barrio"],
            "commune": ["comuna"],
            "phone": ["telefono"],
            "website": ["web"],
            "program_area": ["area_progr"],
            "specialty": ["especialid"],
        },
    },
    {
        "name": "centros_salud_privados",
        "kind": "csv",
        "delimiter": ";",
        "url": f"{CDN}/ministerio-de-salud/centros-salud-privados/centros_de_salud_privado.csv",
        "entity_type": "Facility",
        "subtype": "centro_salud_privado",
        "name_keys": ["nombre"],
        "lat_keys": ["lat"],
        "lng_keys": ["long"],
        "props": {
            "address": ["calle"],
            "street_number": ["altura"],
            "floor": ["piso"],
            "phone": ["telefonos"],
            "neighborhood": ["barrio"],
            "commune": ["comuna"],
            "postal_code": ["codigo_postal", "codigo_postal_argentino"],
        },
    },
    {
        "name": "establecimientos_educativos",
        "kind": "geojson",
        "url": f"{CDN}/ministerio-de-educacion/establecimientos-educativos/establecimientos_educativos.geojson",
        "entity_type": "Facility",
        "subtype": "escuela",
        "name_keys": ["nam", "fna"],
        "subtype_key": "nen_mde",
        "props": {
            "address": ["dir"],
            "neighborhood": ["bar"],
            "commune": ["com"],
            "management": ["ges"],
            "education_level": ["nen_mde"],
            "institution_type": ["tip"],
            "department": ["dep"],
            "school_cui": ["cui"],
            "school_cue": ["cue"],
            "annex": ["anx"],
        },
    },
]

NUMBER_KEYS = {"commune", "street_number", "school_cui", "school_cue"}
URL_KEYS = {"website"}


def clean(value) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "s/d", "sd", "n/a", "nan"}:
        return ""
    return value


def first_value(row: dict, keys: list[str]) -> str:
    for key in keys:
        value = clean(row.get(key))
        if value:
            return value
    return ""


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


def is_palermo(row: dict, lat=None, lng=None) -> bool:
    raw_barrio = first_value(row, ["barrio", "bar", "neighborhood"])
    if raw_barrio:
        barrio = (
            raw_barrio.upper()
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )
        return "PALERMO" in barrio
    return valid_lat_lng(lat, lng)


def coords_from_feature(feature: dict):
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


def coords_from_row(row: dict, dataset: dict):
    lat = parse_float(first_value(row, dataset.get("lat_keys", ["lat"])))
    lng = parse_float(first_value(row, dataset.get("lng_keys", ["long", "lon", "lng"])))
    if valid_lat_lng(lat, lng):
        return lat, lng
    return None, None


def infer_education_subtype(level: str) -> str:
    value = level.lower()
    if "univers" in value:
        return "universidad"
    if "superior" in value or "terci" in value:
        return "instituto_educativo"
    if "secund" in value or "media" in value:
        return "escuela_secundaria"
    if "prim" in value:
        return "escuela_primaria"
    if "inicial" in value or "jardin" in value:
        return "jardin_infantes"
    return "escuela"


async def fetch_geojson(client: httpx.AsyncClient, url: str) -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    return response.json().get("features", [])


async def fetch_csv(client: httpx.AsyncClient, url: str, delimiter: str = ",") -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


async def load_rows(client: httpx.AsyncClient, dataset: dict) -> list[tuple[dict, float | None, float | None]]:
    if dataset["kind"] == "geojson":
        rows = []
        for feature in await fetch_geojson(client, dataset["url"]):
            props = feature.get("properties") or {}
            lat, lng = coords_from_feature(feature)
            rows.append((props, lat, lng))
        return rows

    rows = []
    for row in await fetch_csv(client, dataset["url"], dataset.get("delimiter", ",")):
        lat, lng = coords_from_row(row, dataset)
        rows.append((row, lat, lng))
    return rows


def property_value_type(key: str, value: str):
    if key in URL_KEYS:
        return "url", value
    if key in NUMBER_KEYS:
        number = parse_float(value)
        if number is None:
            return None, ""
        return "number", str(int(number)) if number == int(number) else str(number)
    return "string", normalize_value(value)


async def scrape_dataset(conn, source_id: str, client: httpx.AsyncClient, dataset: dict) -> int:
    print(f"-> {dataset['name']}...")
    try:
        rows = await load_rows(client, dataset)
    except Exception as exc:
        print(f"  ERROR descargando dataset: {exc}")
        return 0

    candidates = [(row, lat, lng) for row, lat, lng in rows if is_palermo(row, lat, lng)]
    offset = int(dataset.get("offset") or 0)
    total_candidates = len(candidates)
    if offset:
        candidates = candidates[offset:]
    print(
        f"  {len(rows)} filas descargadas | {total_candidates} candidatas Palermo"
        + (f" | retomando desde {offset}" if offset else "")
    )

    count = skipped = 0
    for row, lat, lng in candidates:
        raw_name = first_value(row, dataset["name_keys"])
        if not raw_name:
            skipped += 1
            continue
        name = normalize_name(raw_name)

        subtype = dataset["subtype"]
        if dataset.get("subtype_key") == "nen_mde":
            subtype = infer_education_subtype(first_value(row, ["nen_mde", "tip"]))

        entity_id = await get_or_create_entity(
            conn,
            name=name,
            entity_type=dataset["entity_type"],
            subtype=subtype,
            lat=lat,
            lng=lng,
            origin_url=dataset["url"],
            all_names=[raw_name] if raw_name != name else [],
        )

        origins = [dataset["url"]]
        for prop_key, source_keys in dataset.get("props", {}).items():
            raw_value = first_value(row, source_keys)
            if not raw_value:
                continue

            value_type, value = property_value_type(prop_key, raw_value)
            if not value_type or not value:
                continue

            await upsert_property(
                conn,
                entity_id,
                prop_key,
                value,
                value_type,
                source_id,
                origins=origins,
                confidence=0.95,
            )
        count += 1
        if count % 25 == 0:
            print(f"  {count}/{len(candidates)} procesadas...")

    print(f"  OK: {count} entidades de Palermo ({skipped} filas saltadas)")
    return count


async def main():
    print("=== Scraper GCBA Salud + Educacion ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        total = 0
        async with httpx.AsyncClient(follow_redirects=True, timeout=90) as client:
            selected = {arg for arg in sys.argv[1:] if not arg.isdigit()}
            offset = next((int(arg) for arg in sys.argv[1:] if arg.isdigit()), 0)
            for dataset in DATASETS:
                if selected and dataset["name"] not in selected:
                    continue
                if offset:
                    dataset = {**dataset, "offset": offset}
                total += await scrape_dataset(conn, source_id, client, dataset)
                await asyncio.sleep(0.5)
        print(f"\nTotal: {total} entidades insertadas/actualizadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
