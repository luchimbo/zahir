"""
Scraper: Wikidata SPARQL
Fuente: https://query.wikidata.org
Tier 1 — libre, sin autenticacion.

Consulta entidades estructuradas de Buenos Aires:
  - Museos, teatros, universidades, monumentos -> Facility
  - Parques y reservas -> Facility
  - Hospitales y clinicas -> Facility
  - Estadios, bibliotecas -> Facility
"""

import asyncio
import traceback
import httpx
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id
)
from scrapers.shared.normalizer import normalize_name, normalize_value

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "PalermoKGBot/1.0 (https://github.com/luciotambo/palermo-kg; luciotambo@gmail.com) python-httpx/0.27",
}

# QID de Buenos Aires en Wikidata
BA_QID = "Q1486"

# Usamos wdt:P131 wd:Q1486 (directo) en lugar de P131* (recursivo) para evitar timeout.
# Buenos Aires (Q1486) cubre la mayoria de entidades directamente.
QUERIES = {
    "museos": (
        "Facility", "museo",
        """SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31 wd:Q33506 ; wdt:P131 wd:Q1486 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} LIMIT 200"""
    ),
    "teatros": (
        "Facility", "teatro",
        """SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31 wd:Q24354 ; wdt:P131 wd:Q1486 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} LIMIT 200"""
    ),
    "universidades": (
        "Facility", "universidad",
        """SELECT ?item ?itemLabel ?coord ?website ?founded WHERE {
  ?item wdt:P31 wd:Q3918 ; wdt:P131 wd:Q1486 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P856 ?website . }
  OPTIONAL { ?item wdt:P571 ?founded . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} LIMIT 100"""
    ),
    "hospitales": (
        "Facility", "hospital",
        """SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31 wd:Q16917 ; wdt:P131 wd:Q1486 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} LIMIT 100"""
    ),
    "estadios": (
        "Facility", "estadio",
        """SELECT ?item ?itemLabel ?coord ?website ?capacity WHERE {
  ?item wdt:P31 wd:Q483110 ; wdt:P131 wd:Q1486 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P856 ?website . }
  OPTIONAL { ?item wdt:P1083 ?capacity . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} LIMIT 50"""
    ),
    "bibliotecas": (
        "Facility", "biblioteca",
        """SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31 wd:Q7075 ; wdt:P131 wd:Q1486 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} LIMIT 100"""
    ),
}


def parse_coord(coord_str: str):
    if not coord_str:
        return None, None
    try:
        inner = coord_str.replace("Point(", "").replace(")", "").strip()
        parts = inner.split()
        return float(parts[1]), float(parts[0])  # lat, lng
    except Exception:
        return None, None


async def run_query(client: httpx.AsyncClient, sparql: str) -> list:
    r = await client.get(
        SPARQL_URL,
        params={"query": sparql},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("results", {}).get("bindings", [])


async def scrape(conn, source_id: str):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for category, (entity_type, subtype, sparql) in QUERIES.items():
            print(f"-> Wikidata: {category}...")
            try:
                rows = await run_query(client, sparql)
            except Exception as e:
                print(f"  ERROR {category}: {type(e).__name__}: {e}")
                traceback.print_exc()
                continue

            count = 0
            for row in rows:
                label = row.get("itemLabel", {}).get("value", "")
                if not label or label.startswith("Q"):
                    continue

                name = normalize_name(label)
                qid = row.get("item", {}).get("value", "").split("/")[-1]
                lat, lng = parse_coord(row.get("coord", {}).get("value", ""))
                website = row.get("website", {}).get("value", "")
                desc = row.get("desc", {}).get("value", "")
                founded = row.get("founded", {}).get("value", "")
                capacity = row.get("capacity", {}).get("value", "")

                entity_id = await get_or_create_entity(
                    conn,
                    name=name,
                    entity_type=entity_type,
                    subtype=subtype,
                    lat=lat,
                    lng=lng,
                    description=desc or None,
                    origin_url=f"https://www.wikidata.org/wiki/{qid}" if qid else None,
                )

                props = {
                    "wikidata_id": (qid, "string"),
                    "website": (website, "url"),
                    "founded_year": (founded[:4] if founded else "", "string"),
                    "capacity": (str(int(float(capacity))) if capacity else "", "number"),
                }

                for key, (value, vtype) in props.items():
                    if value:
                        await upsert_property(conn, entity_id, key, value, vtype,
                                              source_id, confidence=0.85)
                count += 1

            print(f"  OK {category}: {count} entidades")
            await asyncio.sleep(1)


async def main():
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "wikidata")
        await scrape(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
