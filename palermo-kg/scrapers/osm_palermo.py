"""
Scraper: OpenStreetMap — Overpass API
Fuente: https://overpass-api.de
Tier 1 — libre, sin autenticacion.

Extrae POIs de CABA (o Palermo) en 5 queries separadas para evitar timeout.
"""

import argparse
import asyncio
import urllib.parse

import httpx

from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id, mark_source_synced
)
from scrapers.shared.geo_scope import CABA_BBOX, PALERMO_BBOX, record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value

SUPPORTS_SOURCE_CONTRACT = True

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
UA = "PalermoKGBot/1.0 (luciotambo@gmail.com)"

QUERY_FILTERS = [
    'node["amenity"~"restaurant|bar|cafe|pharmacy|hospital|clinic|school|university|bank|atm|museum|theatre|cinema|gym|veterinary|beauty|nightclub|pub|fast_food|library|police|post_office|spa"]',
    'node["tourism"~"hotel|hostel|guest_house|museum|attraction|gallery|artwork"]',
    'node["shop"~"supermarket|bakery|butcher|clothes|hairdresser|laundry|optician|bookshop|pet|hardware|florist"]',
    'node["leisure"~"fitness_centre|sports_centre|swimming_pool|park|playground|pitch"]',
    'node["healthcare"~"doctor|dentist|physiotherapist|psychologist"]',
]

AMENITY_MAP = {
    "restaurant": ("Organization", "restaurant"), "bar": ("Organization", "bar"),
    "cafe": ("Organization", "cafe"), "pub": ("Organization", "bar"),
    "nightclub": ("Organization", "nightclub"), "fast_food": ("Organization", "fast_food"),
    "pharmacy": ("Facility", "farmacia"), "hospital": ("Facility", "hospital"),
    "clinic": ("Facility", "clinica"), "school": ("Facility", "escuela"),
    "university": ("Facility", "universidad"), "library": ("Facility", "biblioteca"),
    "museum": ("Facility", "museo"), "theatre": ("Facility", "teatro"),
    "cinema": ("Facility", "cine"), "bank": ("Facility", "banco"),
    "atm": ("Facility", "cajero_atm"), "gym": ("Organization", "gimnasio"),
    "veterinary": ("Organization", "veterinaria"), "beauty": ("Organization", "beauty_salon"),
    "spa": ("Organization", "spa"), "police": ("Facility", "comisaria"),
    "post_office": ("Facility", "correo"),
}
TOURISM_MAP = {
    "hotel": ("Organization", "hotel"), "hostel": ("Organization", "hostel"),
    "guest_house": ("Organization", "hotel"), "museum": ("Facility", "museo"),
    "attraction": ("Facility", "atraccion"), "gallery": ("Facility", "galeria"),
    "artwork": ("Facility", "obra_de_arte"),
}
SHOP_MAP = {
    "supermarket": ("Organization", "supermercado"), "bakery": ("Organization", "panaderia"),
    "butcher": ("Organization", "carniceria"), "clothes": ("Organization", "ropa"),
    "hairdresser": ("Organization", "peluqueria"), "laundry": ("Organization", "lavanderia"),
    "optician": ("Organization", "optica"), "bookshop": ("Organization", "libreria"),
    "pet": ("Organization", "veterinaria"), "hardware": ("Organization", "ferreteria"),
    "florist": ("Organization", "floreria"),
}
LEISURE_MAP = {
    "fitness_centre": ("Organization", "gimnasio"), "sports_centre": ("Facility", "polideportivo"),
    "swimming_pool": ("Facility", "pileta"), "park": ("Facility", "parque"),
    "playground": ("Facility", "plaza"), "pitch": ("Facility", "cancha"),
}
HEALTHCARE_MAP = {
    "doctor": ("Facility", "consultorio_medico"), "dentist": ("Facility", "consultorio_dental"),
    "physiotherapist": ("Facility", "kinesiologia"), "psychologist": ("Facility", "consultorio_psicologia"),
}

PROP_KEYS = [
    ("osm_id", lambda el: str(el["id"]), "string"),
    ("address", lambda t: t.get("addr:street", ""), "string"),
    ("phone", lambda t: t.get("phone") or t.get("contact:phone", ""), "string"),
    ("website", lambda t: t.get("website") or t.get("contact:website", ""), "url"),
    ("hours_open", lambda t: t.get("opening_hours", ""), "string"),
    ("cuisine_type", lambda t: t.get("cuisine", ""), "string"),
    ("instagram", lambda t: t.get("contact:instagram", ""), "string"),
]


def parse_args():
    parser = argparse.ArgumentParser()
    add_source_arguments(parser)
    return parser.parse_args()


def resolve_type(tags):
    for tag_key, mapping in [
        ("amenity", AMENITY_MAP), ("tourism", TOURISM_MAP),
        ("shop", SHOP_MAP), ("leisure", LEISURE_MAP), ("healthcare", HEALTHCARE_MAP),
    ]:
        val = tags.get(tag_key)
        if val and val in mapping:
            return mapping[val]
    return None


def build_queries(bbox: str):
    return [
        f'[out:json][timeout:30];{f}({bbox});out body;'
        for f in QUERY_FILTERS
    ]


async def post_query(client, query):
    payload = urllib.parse.urlencode({"data": query})
    r = await client.post(
        OVERPASS_URL,
        content=payload.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA},
    )
    r.raise_for_status()
    return r.json().get("elements", [])


async def fetch_elements(queries):
    all_elements = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i, query in enumerate(queries):
            print(f"-> Overpass query {i + 1}/{len(queries)}...")
            try:
                elements = await post_query(client, query)
                all_elements.extend(elements)
                print(f"  {len(elements)} nodos")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"  ERROR: {e}")
                await asyncio.sleep(10)
    return all_elements


def to_candidate(el, scope, neighborhood, commune):
    tags = el.get("tags", {})
    name = tags.get("name") or tags.get("name:es")
    if not name:
        return None
    resolved = resolve_type(tags)
    if not resolved:
        return None
    lat, lng = el.get("lat"), el.get("lon")
    if lat is None or lng is None:
        return None
    if not record_in_scope(lat=lat, lng=lng, scope=scope,
                            neighborhood=neighborhood, commune=commune):
        return None
    props = []
    for key, getter, _vtype in PROP_KEYS:
        val = getter(el) if key == "osm_id" else getter(tags)
        if val:
            props.append((key, normalize_value(val) if _vtype == "string" else val))
    return {
        "name": normalize_name(name),
        "entity_type": resolved[0],
        "subtype": resolved[1],
        "lat": lat,
        "lng": lng,
        "origin_url": f"https://www.openstreetmap.org/node/{el['id']}",
        "props": props,
    }


async def write_candidates(candidates, source_name="osm"):
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, source_name)
        count = 0
        for c in candidates:
            entity_id = await get_or_create_entity(
                conn, name=c["name"], entity_type=c["entity_type"], subtype=c["subtype"],
                lat=c["lat"], lng=c["lng"], origin_url=c["origin_url"],
                source_id=source_id,
            )
            for key, value in c["props"]:
                await upsert_property(conn, entity_id, key, value,
                                     "string" if isinstance(value, str) else "url",
                                     source_id, confidence=0.5)
            count += 1
            if count % 100 == 0:
                print(f"  {count} entidades insertadas/actualizadas...")
        await mark_source_synced(conn, source_id)
        print(f"  OK OSM: {count} entidades")
    finally:
        await conn.close()


async def main():
    args = parse_args()
    bbox = CABA_BBOX if args.scope == "caba" else PALERMO_BBOX
    bbox_str = f"{bbox[0]},{bbox[2]},{bbox[1]},{bbox[3]}"
    print(f"OSM scope={args.scope} bbox={bbox_str}")

    queries = build_queries(bbox_str)
    elements = await fetch_elements(queries)
    print(f"  Total OSM: {len(elements)} nodos crudos")

    candidates = []
    skipped = 0
    for el in elements:
        c = to_candidate(el, args.scope, args.neighborhood, args.commune)
        if c:
            candidates.append(c)
        else:
            skipped += 1

    candidates = bounded(candidates, args.limit)
    print(f"OSM: {len(candidates)} entidades | scope={args.scope} | write={args.write} | skipped={skipped}")
    if not args.write:
        return
    await write_candidates(candidates)


if __name__ == "__main__":
    asyncio.run(main())
