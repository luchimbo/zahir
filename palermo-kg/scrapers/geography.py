"""Carga la jerarquía oficial CABA y vincula entidades geocodificadas.

Uso seguro: primero ejecutar sin ``--write`` para inspeccionar cobertura; con
``--write`` crea/actualiza sólo entidades y relaciones idempotentes, nunca borra.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import os

import httpx

from geography_catalog import CITY_NAME, COMMUNES, NEIGHBORHOOD_TO_COMMUNE, SUBAREA_ALIASES, geography_rows, resolve_neighborhood
from scrapers.shared.db_helpers import (ensure_source, get_conn, get_or_create_entity,
                                        upsert_property, upsert_relationship)

BARRIOS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/barrios/barrios.geojson"


def feature_value(properties: dict, *keys: str) -> str:
    values = {str(key).lower(): value for key, value in (properties or {}).items()}
    for key in keys:
        value = values.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def contains_point(point: tuple[float, float], geometry: dict) -> bool:
    """Ray casting WGS84, incluido para no exigir PostGIS en TiDB."""
    x, y = point

    def in_ring(ring):
        inside = False
        for index, current in enumerate(ring):
            previous = ring[index - 1]
            x1, y1 = previous[0], previous[1]
            x2, y2 = current[0], current[1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        return inside

    polygons = [geometry.get("coordinates", [])] if geometry.get("type") == "Polygon" else geometry.get("coordinates", [])
    return any(polygon and in_ring(polygon[0]) and not any(in_ring(hole) for hole in polygon[1:]) for polygon in polygons)


async def fetch_boundaries() -> dict[str, dict]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(BARRIOS_URL)
        response.raise_for_status()
    boundaries = {}
    for feature in response.json().get("features", []):
        name = resolve_neighborhood(feature_value(feature.get("properties", {}), "barrio", "nombre", "name"))
        if name and feature.get("geometry"):
            boundaries[name] = feature["geometry"]
    missing = set(NEIGHBORHOOD_TO_COMMUNE) - set(boundaries)
    if missing:
        raise RuntimeError(f"GeoJSON GCBA incompleto; faltan: {', '.join(sorted(missing))}")
    return boundaries


async def seed_hierarchy(conn, source_id: str, write: bool) -> dict[str, str]:
    entities = {}
    for row in geography_rows():
        if not write:
            continue
        entity_id = await get_or_create_entity(conn, row["name"], "Location", subtype=row["level"], origin_url=BARRIOS_URL)
        entities[row["name"]] = entity_id
        await upsert_property(conn, entity_id, "geography_level", row["level"], "string", source_id, [BARRIOS_URL], 1.0)
        await upsert_property(conn, entity_id, "slug", row["slug"], "string", source_id, [BARRIOS_URL], 1.0)
        if row["commune"]:
            await upsert_property(conn, entity_id, "commune_code", str(row["commune"]), "number", source_id, [BARRIOS_URL], 1.0)
    if not write:
        return entities
    city_id = entities[CITY_NAME]
    for commune, neighborhoods in COMMUNES.items():
        commune_id = entities[f"Comuna {commune}"]
        await upsert_relationship(conn, commune_id, "PART_OF", city_id, origins=[BARRIOS_URL], confidence=1.0)
        for neighborhood in neighborhoods:
            await upsert_relationship(conn, entities[neighborhood], "PART_OF", commune_id, origins=[BARRIOS_URL], confidence=1.0)
    # Informal places are navigable aliases, but never advertised as official barrios.
    for alias, parent in SUBAREA_ALIASES.items():
        name = alias.title().replace("Soho", "Soho").replace("Hollywood", "Hollywood")
        subarea_id = await get_or_create_entity(conn, name, "Location", subtype="informal_area", origin_url=BARRIOS_URL)
        await upsert_property(conn, subarea_id, "official_geography", "false", "boolean", source_id, [BARRIOS_URL], 1.0)
        await upsert_relationship(conn, subarea_id, "PART_OF", entities[parent], origins=[BARRIOS_URL], confidence=0.8)
    return entities


async def assign_existing(conn, boundaries: dict[str, dict], locations: dict[str, str], write: bool) -> Counter:
    rows = await conn.fetch("""SELECT id,lat,lng FROM entities
        WHERE is_active=TRUE AND canonical_id IS NULL AND entity_type <> 'Location'
          AND lat IS NOT NULL AND lng IS NOT NULL""")
    coverage = Counter(seen=len(rows))
    for row in rows:
        neighborhood = next((name for name, geometry in boundaries.items()
                             if contains_point((float(row["lng"]), float(row["lat"])), geometry)), None)
        if not neighborhood:
            coverage["outside_caba"] += 1
            continue
        coverage["assigned"] += 1
        coverage[f"neighborhood:{neighborhood}"] += 1
        if write:
            await upsert_relationship(conn, str(row["id"]), "LOCATED_IN", locations[neighborhood], origins=[BARRIOS_URL], confidence=1.0)
    return coverage


async def main():
    parser = argparse.ArgumentParser(description="Carga y aplica geografía oficial CABA")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--skip-assignment", action="store_true")
    parser.add_argument("--allow-production", action="store_true", help="Requiere confirmación adicional fuera de staging.")
    args = parser.parse_args()
    if args.write and os.getenv("KG_ENV", "").lower() != "staging" and not args.allow_production:
        raise RuntimeError("La escritura geográfica se habilita sólo con KG_ENV=staging o --allow-production")
    boundaries = await fetch_boundaries()
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, "gcba_geography", BARRIOS_URL, 1) if args.write else ""
        locations = await seed_hierarchy(conn, source_id, args.write)
        coverage = Counter(neighborhoods=len(boundaries), communes=15)
        if not args.skip_assignment:
            coverage.update(await assign_existing(conn, boundaries, locations, args.write))
        print(dict(coverage))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
