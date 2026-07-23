"""
Scraper: Google Places API
Fuente: Google Maps Platform - Places API (New)
Tier 2 — Requiere API key.

Busca comercios, restaurantes y servicios en Palermo, Buenos Aires.
Usa Nearby Search para cubrir el área geográfica de Palermo.
"""

import asyncio
import os
import httpx
from dotenv import load_dotenv
from scrapers.shared.db_helpers import (
    bulk_get_or_create_entities, bulk_link_external_ids, bulk_upsert_properties,
    get_conn, get_source_id, mark_source_synced
)

load_dotenv()

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

# Nearby Search v1 endpoint
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Centro de Palermo y radio en metros
PALERMO_LAT = -34.5875
PALERMO_LNG = -58.4220
RADIO_M = 2500

# Tipos de lugar que nos interesan
PLACE_TYPES = [
    "restaurant",
    "bar",
    "cafe",
    "bakery",
    "supermarket",
    "pharmacy",
    "gym",
    "clothing_store",
    "beauty_salon",
    "hotel",
    "museum",
    "park",
    "night_club",
]

# Límite duro por corrida: evita costos inesperados. Puede elevarse mediante env.
MAX_TYPES_PER_RUN = max(1, min(int(os.getenv("GOOGLE_PLACES_MAX_TYPES", "3")), len(PLACE_TYPES)))

# Campos que pedimos a la API (reduce costo de requests)
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.regularOpeningHours",
    "places.priceLevel",
    "places.types",
    "places.editorialSummary",
    "places.delivery",
    "places.dineIn",
    "places.takeout",
    "places.reservable",
    "places.servesVegetarianFood",
])

PRICE_MAP = {
    "PRICE_LEVEL_FREE":         "$",
    "PRICE_LEVEL_INEXPENSIVE":  "$",
    "PRICE_LEVEL_MODERATE":     "$$",
    "PRICE_LEVEL_EXPENSIVE":    "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}


async def fetch_places(client: httpx.AsyncClient, place_type: str) -> list:
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": PALERMO_LAT, "longitude": PALERMO_LNG},
                "radius": RADIO_M,
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    r = await client.post(NEARBY_URL, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("places", [])


async def scrape_google_places(source_id: str):
    print("-> Scrapeando Google Places...")
    seen_ids = set()
    total = 0
    all_collected = []

    async with httpx.AsyncClient() as client:
        completed = True
        for place_type in PLACE_TYPES[:MAX_TYPES_PER_RUN]:
            try:
                places = await fetch_places(client, place_type)
                print(f"  -> {place_type}: {len(places)} resultados")
                for p in places:
                    all_collected.append((place_type, p))
            except Exception as e:
                print(f"  [warn] {place_type}: {e}")
                completed = False
                continue

    if not all_collected:
        print("  No se recolectaron lugares de Google Places.")
        return False

    conn = await get_conn()
    try:
        entity_records, property_records, external_links = [], [], []
        for place_type, place in all_collected:
            gid = place.get("id", "")
            if gid in seen_ids:
                continue
            seen_ids.add(gid)

            name = place.get("displayName", {}).get("text", "").strip()
            if not name:
                continue

            loc = place.get("location", {})
            lat = loc.get("latitude")
            lng = loc.get("longitude")

            address = place.get("formattedAddress", "")
            phone = place.get("nationalPhoneNumber", "")
            website = place.get("websiteUri", "")
            rating = place.get("rating")
            review_count = place.get("userRatingCount")
            price_level = PRICE_MAP.get(place.get("priceLevel", ""), "")
            summary = place.get("editorialSummary", {}).get("text", "")

            subtype = place_type

            entity_records.append({
                "name": name, "entity_type": "Organization", "subtype": subtype,
                "lat": lat, "lng": lng, "description": summary or None,
                "origin_url": f"https://maps.google.com/?cid={gid}", "all_names": [],
            })

            origin = [f"https://maps.google.com/?cid={gid}"]

            values = [
                ("address", address, "string"), ("phone", phone, "string"),
                ("website", website, "url"), ("rating", rating, "number"),
                ("review_count", review_count, "number"), ("price_range", price_level, "string"),
                ("has_delivery", str(place["delivery"]).lower() if place.get("delivery") is not None else "", "boolean"),
                ("accepts_reservations", str(place["reservable"]).lower() if place.get("reservable") is not None else "", "boolean"),
                ("serves_vegetarian", str(place["servesVegetarianFood"]).lower() if place.get("servesVegetarianFood") is not None else "", "boolean"),
            ]

            # Horarios
            hours = place.get("regularOpeningHours", {})
            weekday_text = hours.get("weekdayDescriptions", [])
            if weekday_text:
                values.append(("hours_text", " | ".join(weekday_text), "string"))
            for key, value, value_type in values:
                if value not in (None, ""):
                    property_records.append({"entity_name": name, "key": key, "value": str(value),
                                             "value_type": value_type, "origins": origin, "confidence": 0.75})
            external_links.append((name, gid))

            total += 1
            if total % 20 == 0:
                print(f"    Procesados {total}/{len(all_collected)} lugares...")
            await asyncio.sleep(0.05)
        entity_ids = await bulk_get_or_create_entities(conn, entity_records)
        await bulk_link_external_ids(conn, [(entity_ids[name], source_id, gid) for name, gid in external_links])
        for record in property_records:
            record["entity_id"] = entity_ids[record.pop("entity_name")]
        await bulk_upsert_properties(conn, property_records, source_id)
    finally:
        await conn.close()

    print(f"  [OK] {total} lugares de Palermo procesados")
    return completed


async def main():
    print("=== Scraper Google Places ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "google_places")
    finally:
        await conn.close()
        
    completed = await scrape_google_places(source_id)
    if completed:
        conn = await get_conn()
        try:
            await mark_source_synced(conn, source_id)
        finally:
            await conn.close()
    else:
        print("Google Places incompleto: la fuente queda pendiente.")
    print("\n[OK] Scraper finalizado exitosamente")


if __name__ == "__main__":
    asyncio.run(main())
