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
    get_conn, get_or_create_entity, upsert_property, get_source_id
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


async def scrape_google_places(conn, source_id: str):
    print("→ Scrapeando Google Places...")
    seen_ids = set()
    total = 0

    async with httpx.AsyncClient() as client:
        for place_type in PLACE_TYPES:
            try:
                places = await fetch_places(client, place_type)
                print(f"  → {place_type}: {len(places)} resultados")
            except Exception as e:
                print(f"  [warn] {place_type}: {e}")
                continue

            for place in places:
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
                types = place.get("types", [])

                subtype = place_type

                entity_id = await get_or_create_entity(
                    conn, name=name, entity_type="Organization",
                    subtype=subtype, lat=lat, lng=lng,
                    description=summary or None,
                    origin_url=f"https://maps.google.com/?cid={gid}",
                    all_names=[]
                )

                origin = [f"https://maps.google.com/?cid={gid}"]

                if address:
                    await upsert_property(conn, entity_id, "address", address,
                                          "string", source_id, origins=origin)
                if phone:
                    await upsert_property(conn, entity_id, "phone", phone,
                                          "string", source_id, origins=origin)
                if website:
                    await upsert_property(conn, entity_id, "website", website,
                                          "url", source_id, origins=origin)
                if rating is not None:
                    await upsert_property(conn, entity_id, "rating", str(rating),
                                          "number", source_id, origins=origin)
                if review_count is not None:
                    await upsert_property(conn, entity_id, "review_count", str(review_count),
                                          "number", source_id, origins=origin)
                if price_level:
                    await upsert_property(conn, entity_id, "price_range", price_level,
                                          "string", source_id, origins=origin)
                if place.get("delivery") is not None:
                    await upsert_property(conn, entity_id, "has_delivery",
                                          str(place["delivery"]).lower(),
                                          "boolean", source_id, origins=origin)
                if place.get("reservable") is not None:
                    await upsert_property(conn, entity_id, "accepts_reservations",
                                          str(place["reservable"]).lower(),
                                          "boolean", source_id, origins=origin)
                if place.get("servesVegetarianFood") is not None:
                    await upsert_property(conn, entity_id, "serves_vegetarian",
                                          str(place["servesVegetarianFood"]).lower(),
                                          "boolean", source_id, origins=origin)

                # Horarios
                hours = place.get("regularOpeningHours", {})
                weekday_text = hours.get("weekdayDescriptions", [])
                if weekday_text:
                    await upsert_property(conn, entity_id, "hours_text",
                                          " | ".join(weekday_text),
                                          "string", source_id, origins=origin)

                total += 1

            await asyncio.sleep(0.05)

    print(f"  ✓ {total} lugares de Palermo procesados")


async def main():
    print("=== Scraper Google Places ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "google_places")
        await scrape_google_places(conn, source_id)
        print("\n✓ Scraper finalizado exitosamente")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
