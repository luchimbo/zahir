"""
Scraper: OpenStreetMap — Overpass API
Fuente: https://overpass-api.de
Tier 1 — libre, sin autenticacion.

Extrae POIs de Palermo BA en 5 queries separadas para evitar timeout.
"""

import asyncio
import urllib.parse
import httpx
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id, mark_source_synced
)
from scrapers.shared.normalizer import normalize_name, normalize_value

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PALERMO_BBOX = "-34.610,-58.450,-34.558,-58.395"
UA = "PalermoKGBot/1.0 (luciotambo@gmail.com)"

OVERPASS_QUERIES = [
    f'[out:json][timeout:30];node["amenity"~"restaurant|bar|cafe|pharmacy|hospital|clinic|school|university|bank|atm|museum|theatre|cinema|gym|veterinary|beauty|nightclub|pub|fast_food|library|police|post_office|spa"]({PALERMO_BBOX});out body;',
    f'[out:json][timeout:30];node["tourism"~"hotel|hostel|guest_house|museum|attraction|gallery|artwork"]({PALERMO_BBOX});out body;',
    f'[out:json][timeout:30];node["shop"~"supermarket|bakery|butcher|clothes|hairdresser|laundry|optician|bookshop|pet|hardware|florist"]({PALERMO_BBOX});out body;',
    f'[out:json][timeout:30];node["leisure"~"fitness_centre|sports_centre|swimming_pool|park|playground|pitch"]({PALERMO_BBOX});out body;',
    f'[out:json][timeout:30];node["healthcare"~"doctor|dentist|physiotherapist|psychologist"]({PALERMO_BBOX});out body;',
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


def resolve_type(tags):
    for tag_key, mapping in [
        ("amenity", AMENITY_MAP), ("tourism", TOURISM_MAP),
        ("shop", SHOP_MAP), ("leisure", LEISURE_MAP), ("healthcare", HEALTHCARE_MAP),
    ]:
        val = tags.get(tag_key)
        if val and val in mapping:
            return mapping[val]
    return None


async def post_query(client, query):
    payload = urllib.parse.urlencode({"data": query})
    r = await client.post(
        OVERPASS_URL,
        content=payload.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA},
    )
    r.raise_for_status()
    return r.json().get("elements", [])


async def scrape(conn, source_id):
    all_elements = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i, query in enumerate(OVERPASS_QUERIES):
            print(f"-> Overpass query {i+1}/{len(OVERPASS_QUERIES)}...")
            try:
                elements = await post_query(client, query)
                all_elements.extend(elements)
                print(f"  {len(elements)} nodos")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"  ERROR: {e}")
                await asyncio.sleep(10)

    print(f"  Total OSM: {len(all_elements)} nodos")

    count = skipped = 0
    for el in all_elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:es")
        if not name:
            skipped += 1
            continue

        name = normalize_name(name)
        resolved = resolve_type(tags)
        if not resolved:
            skipped += 1
            continue

        entity_type, subtype = resolved
        entity_id = await get_or_create_entity(
            conn, name=name, entity_type=entity_type, subtype=subtype,
            lat=el.get("lat"), lng=el.get("lon"),
            origin_url=f"https://www.openstreetmap.org/node/{el['id']}",
            source_id=source_id, external_id=f"node/{el['id']}",
        )

        for key, value, vtype in [
            ("osm_id", str(el["id"]), "string"),
            ("address", tags.get("addr:street", ""), "string"),
            ("phone", tags.get("phone") or tags.get("contact:phone", ""), "string"),
            ("website", tags.get("website") or tags.get("contact:website", ""), "url"),
            ("hours_open", tags.get("opening_hours", ""), "string"),
            ("cuisine_type", tags.get("cuisine", ""), "string"),
            ("instagram", tags.get("contact:instagram", ""), "string"),
        ]:
            if value:
                await upsert_property(conn, entity_id, key,
                                      normalize_value(value) if vtype == "string" else value,
                                      vtype, source_id, confidence=0.5)
        count += 1
        if count % 100 == 0:
            print(f"  {count} entidades procesadas...")

    print(f"  OK OSM: {count} entidades insertadas/actualizadas, {skipped} saltadas")


async def main():
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "osm")
        await scrape(conn, source_id)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
