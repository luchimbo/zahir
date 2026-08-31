"""
Scraper: BA Data GCBA - cultura y espacio publico
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV sin autenticacion.

Datasets:
  - Espacios culturales
  - Ferias y mercados
  - Monumentos
  - Murales
  - Calesitas

No toca datos inmobiliarios.
"""

import argparse
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

CDN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets"


def clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "s/d", "sd", "n/a", "nan", "-"}:
        return ""
    return value


def parse_float(value: Any):
    value = clean(value).replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


CABA_LAT_MIN, CABA_LAT_MAX = -34.706, -34.526
CABA_LNG_MIN, CABA_LNG_MAX = -58.531, -58.335


def valid_lat_lng(lat, lng) -> bool:
    return (
        lat is not None
        and lng is not None
        and CABA_LAT_MIN <= lat <= CABA_LAT_MAX
        and CABA_LNG_MIN <= lng <= CABA_LNG_MAX
    )


def parse_wkt_point(wkt: str):
    """Parsea WKT POINT(lng lat) a (lat, lng)."""
    if not wkt:
        return None, None
    m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", str(wkt), re.I)
    if not m:
        return None, None
    lng = parse_float(m.group(1))
    lat = parse_float(m.group(2))
    if valid_lat_lng(lat, lng):
        return lat, lng
    return None, None


def address_from(row: dict, *keys: str) -> str:
    parts = [clean(row.get(k)) for k in keys]
    return " ".join(p for p in parts if p).strip()


def build_name(*parts: str) -> str:
    return " ".join(clean(p) for p in parts if clean(p)).strip()


def fetch_csv(url: str, delimiter: str = ",") -> list[dict]:
    r = httpx.get(url, follow_redirects=True, timeout=60)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


NUMBER_KEYS = {"cantidad_salas", "capacidad_total", "cantidad_objetos"}
URL_KEYS = {"website", "web", "facebook", "twitter", "instagram", "mail"}


def property_value_type(key: str, value: str):
    if key in URL_KEYS:
        return "url", value
    if key in NUMBER_KEYS:
        number = parse_float(value)
        if number is None:
            return None, ""
        return "number", str(int(number)) if number == int(number) else str(number)
    return "string", normalize_value(value)


def collect_props(row: dict, mapping: dict[str, str | list[str]]) -> dict[str, str]:
    """mapping: key_destino -> source_key(s)"""
    collected: dict[str, str] = {}
    for dest_key, src_keys in mapping.items():
        if isinstance(src_keys, str):
            src_keys = [src_keys]
        for sk in src_keys:
            v = clean(row.get(sk))
            if v:
                collected[dest_key] = v
                break
    return collected


def field_by_key(row: dict, *needles: str) -> str:
    """Devuelve el primer valor no vacio cuya columna contenga todas las aguja."""
    for k in row:
        if k and all(n in k.lower() for n in needles):
            v = clean(row.get(k))
            if v:
                return v
    return ""


def collect_candidates(rows: list[dict], dataset: dict, args) -> list[dict]:
    """Filtra territorialmente y arma candidatos segun la definicion del dataset."""
    candidates = []
    for row in rows:
        lat, lng = dataset["coords"](row)
        if not record_in_scope(
            lat=lat,
            lng=lng,
            row_neighborhood=field_by_key(row, "barrio"),
            row_commune=field_by_key(row, "comuna"),
            scope=args.scope,
            neighborhood=args.neighborhood,
            commune=args.commune,
        ):
            continue

        name = normalize_name(dataset["name_builder"](row))
        if not name:
            continue

        final_subtype = dataset["subtype"]
        if dataset.get("subtype_extractor"):
            final_subtype = dataset["subtype_extractor"](row, dataset["subtype"])

        candidates.append({
            "name": name,
            "entity_type": dataset["entity_type"],
            "subtype": final_subtype,
            "lat": lat,
            "lng": lng,
            "origin_url": dataset["url"],
            "props": collect_props(row, dataset["prop_map"]),
        })
    return candidates


async def write_candidates(conn, source_id: str, dataset: dict, candidates: list[dict]) -> None:
    """Escribe entidades y propiedades de un dataset ya filtrado y acotado."""

    entity_records = [
        {
            "name": c["name"],
            "entity_type": c["entity_type"],
            "subtype": c["subtype"],
            "lat": c["lat"],
            "lng": c["lng"],
            "origin_url": None,
        }
        for c in candidates
    ]
    ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

    prop_records = []
    for c in candidates:
        entity_id = ids_by_name.get(c["name"])
        if not entity_id:
            continue
        for key, raw_value in c["props"].items():
            if not raw_value:
                continue
            vtype, value = property_value_type(key, raw_value)
            if not value:
                continue
            prop_records.append({
                "entity_id": entity_id,
                "key": key,
                "value": value,
                "value_type": vtype,
                "confidence": 0.95,
                "origins": [dataset["url"]],
            })

    await bulk_upsert_properties(conn, prop_records, source_id)
    entity_ids = list({p["entity_id"] for p in prop_records})
    if entity_ids:
        await conn.execute(
            """
            UPDATE entities
            SET origin_url = COALESCE(origin_url, $1)
            WHERE id = ANY($2::uuid[])
            """,
            dataset["url"],
            entity_ids,
        )
        await conn.executemany(
            """
            UPDATE properties
            SET origins = $4, last_seen_at = now()
            WHERE entity_id = $1::uuid
              AND key = $2
              AND source_id = $3::uuid
              AND valid_until IS NULL
              AND (origins IS NULL OR cardinality(origins) = 0)
            """,
            [
                (p["entity_id"], p["key"], source_id, p["origins"])
                for p in prop_records
            ],
        )
    print(f"  OK: {len(candidates)} entidades de {dataset['name']}")


# ── Dataset: espacios culturales ─────────────────────────────────────────────

ESPACIOS_CULTURALES_URL = f"{CDN}/ministerio-de-cultura/espacios-culturales/espacios-culturales.csv"

ESPACIOS_PROP_MAP = {
    "function": "FUNCION_PRINCIPAL",
    "subcategory": "SUBCATEGORIA",
    "programming": "PROGRAMACION",
    "branch": "SUCURSAL",
    "room": "SALA",
    "address": "DIRECCION",
    "street": "CALLE",
    "street_number": "ALTURA",
    "neighborhood": "BARRIO",
    "commune": "COMUNA",
    "phone": "TELEFONO",
    "email": "MAIL",
    "website": "WEB",
    "facebook": "FACEBOOK",
    "twitter": "TWITTER",
    "instagram": "INSTAGRAM",
    "rooms": "CANTIDAD_SALAS",
    "capacity": "CAPACIDAD_TOTAL",
    "tag": "TAG",
}


def espacios_name(row: dict) -> str:
    establecimiento = clean(row.get("ESTABLECIMIENTO"))
    sucursal = clean(row.get("SUCURSAL"))
    if establecimiento and sucursal:
        return f"{establecimiento} - {sucursal}"
    return establecimiento or sucursal


def espacios_subtype(row: dict, default: str | None) -> str:
    func = clean(row.get("FUNCION_PRINCIPAL", "")).lower()
    mapping = {
        "anfiteatro": "anfiteatro",
        "biblioteca": "biblioteca",
        "centro cultural": "centro_cultural",
        "cine": "cine",
        "espacio cultural": "espacio_cultural",
        "galeria de arte": "galeria_arte",
        "museo": "museo",
        "sala de concierto": "sala_concierto",
        "sala de ensayo": "sala_ensayo",
        "sala de exposicion": "sala_exposicion",
        "teatro": "teatro",
    }
    for k, v in mapping.items():
        if k in func:
            return v
    return default or "espacio_cultural"


def espacios_coords(row: dict):
    lat = parse_float(row.get("LATITUD"))
    lng = parse_float(row.get("LONGITUD"))
    return lat, lng


# ── Dataset: ferias y mercados ───────────────────────────────────────────────

FERIAS_URL = f"{CDN}/ministerio-de-espacio-publico-e-higiene-urbana/ferias-mercados/ferias.csv"

FERIAS_PROP_MAP = {
    "type": "tipo",
    "days": "dias",
    "observations": "observacio",
    "address": "direccion",
    "street": "calle",
    "corner": "cruce",
    "neighborhood": "barrio",
    "commune": "comuna",
}


def ferias_name(row: dict) -> str:
    return build_name(row.get("tipo"), row.get("nombre"))


def ferias_coords(row: dict):
    return parse_float(row.get("lat")), parse_float(row.get("lng"))


# ── Dataset: monumentos ──────────────────────────────────────────────────────

MONUMENTOS_URL = f"{CDN}/ministerio-de-espacio-publico-e-higiene-urbana/monumentos/monumentos.csv"

MONUMENTOS_PROP_MAP = {
    "object_type": "OBJETO_OBRA",
    "object_count": "CANTIDAD_OBJETOS",
    "material": "MATERIAL",
    "symbolizes": "DENOMINACION_SIMBOLIZA",
    "authors": "AUTORES",
    "location_detail": "UBICACION",
    "observations": "OBSERVACIONES",
    "address": "DIRECCION_NORMALIZADA",
    "street": "CALLE",
    "street_number": "ALTURA",
    "neighborhood": "BARRIO",
    "commune": "COMUNA",
    "postal_code": "CODIGA_POSTAL",
}


def monumentos_name(row: dict) -> str:
    denom = clean(row.get("DENOMINACION_SIMBOLIZA"))
    obj = clean(row.get("OBJETO_OBRA"))
    if denom:
        return f"{obj} {denom}".strip() if obj else denom
    return obj or "Monumento"


def monumentos_coords(row: dict):
    return parse_float(row.get("LATITUD")), parse_float(row.get("LONGITUD"))


# ── Dataset: murales ─────────────────────────────────────────────────────────

MURALES_URL = f"{CDN}/ministerio-de-cultura/murales/murales.csv"

MURALES_PROP_MAP = {
    "site_characteristics": "caract_sit",
    "authors": "autores",
    "technique": "tecnica",
    "year": "f_e",
    "size": "tama�o_ts",
    "location_detail": "ubicacion",
    "address": "direccion",
    "street": "calle",
    "street_number": "altura",
    "neighborhood": "barrio",
    "commune": "comuna",
}


def murales_name(row: dict) -> str:
    nombre = clean(row.get("nombre"))
    if nombre:
        return f"Mural {nombre}"
    ubicacion = clean(row.get("ubicacion"))
    if ubicacion:
        return f"Mural en {ubicacion}"
    return "Mural"


def murales_coords(row: dict):
    return parse_wkt_point(row.get("wkt"))


# ── Dataset: calesitas ───────────────────────────────────────────────────────

CALESITAS_URL = f"{CDN}/atencion-ciudadana/calesitas/permisos_calesitas.csv"

CALESITAS_PROP_MAP = {
    "year": "A�O",
    "file_number": "N� DE EXPEDIENTE",
    "holder": "TITULAR",
    "id_number": "DNI",
    "street": "CALLE",
    "street_number": "ALTURA",
    "plaza": "PLAZA",
    "neighborhood": "BARRIO",
    "commune": "Comuna",
    "resolution": "N� de Dispo / Reso",
    "start_date": "Fecha de Inicio",
    "end_date": "Fecha de Vencimiento",
    "status": "Estado",
}


def calesitas_name(row: dict) -> str:
    plaza = clean(row.get("PLAZA"))
    street = clean(row.get("CALLE"))
    if plaza:
        return f"Calesita {plaza}"
    if street:
        return f"Calesita {street}"
    return "Calesita"


def calesitas_coords(row: dict):
    # El dataset de calesitas no tiene coordenadas.
    return None, None


DATASETS = [
    {
        "name": "espacios_culturales",
        "url": ESPACIOS_CULTURALES_URL,
        "delimiter": ",",
        "name_builder": espacios_name,
        "entity_type": "Facility",
        "subtype": "espacio_cultural",
        "prop_map": ESPACIOS_PROP_MAP,
        "coords": espacios_coords,
        "subtype_extractor": espacios_subtype,
    },
    {
        "name": "ferias",
        "url": FERIAS_URL,
        "delimiter": ",",
        "name_builder": ferias_name,
        "entity_type": "Facility",
        "subtype": "feria",
        "prop_map": FERIAS_PROP_MAP,
        "coords": ferias_coords,
    },
    {
        "name": "monumentos",
        "url": MONUMENTOS_URL,
        "delimiter": ";",
        "name_builder": monumentos_name,
        "entity_type": "Facility",
        "subtype": "monumento",
        "prop_map": MONUMENTOS_PROP_MAP,
        "coords": monumentos_coords,
    },
    {
        "name": "murales",
        "url": MURALES_URL,
        "delimiter": ";",
        "name_builder": murales_name,
        "entity_type": "Facility",
        "subtype": "mural",
        "prop_map": MURALES_PROP_MAP,
        "coords": murales_coords,
    },
    {
        "name": "calesitas",
        "url": CALESITAS_URL,
        "delimiter": ";",
        "name_builder": calesitas_name,
        "entity_type": "Facility",
        "subtype": "calesita",
        "prop_map": CALESITAS_PROP_MAP,
        "coords": calesitas_coords,
    },
]


async def main():
    parser = argparse.ArgumentParser(description="BA Data cultura y espacio publico")
    add_source_arguments(parser)
    args, unknown = parser.parse_known_args()
    selected = set(unknown)
    print("=== Scraper GCBA Cultura y Espacio Publico ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        total = 0
        for dataset in DATASETS:
            if selected and dataset["name"] not in selected:
                continue
            rows = fetch_csv(dataset["url"], dataset["delimiter"])
            candidates = collect_candidates(rows, dataset, args)
            candidates = bounded(candidates, args.limit)
            if candidates:
                if not args.write:
                    print(f"  [dry-run] {len(candidates)} entidades de {dataset['name']}")
                else:
                    await write_candidates(conn, source_id, dataset, candidates)
            total += len(candidates)
            await asyncio.sleep(0.5)
        if args.write:
            await mark_source_synced(conn, source_id)
        print(f"\nTotal: {total} entidades insertadas/actualizadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
