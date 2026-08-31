"""Centros de Integración Laboral de CABA desde GCBA."""
import argparse, asyncio, sys
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value

SUPPORTS_SOURCE_CONTRACT = True

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/centros-integracion-laboral/centros_integracion_laboral.geojson"


def parse_args():
    p = argparse.ArgumentParser(description="Scraper GCBA Centros de Integración Laboral (CABA)")
    add_source_arguments(p)
    return p.parse_args()


async def main():
    args = parse_args()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(URL)
        response.raise_for_status()
        features = response.json()["features"]

    candidates = []
    for feature in features:
        data = feature.get("properties") or {}
        neighborhood = str(data.get("barrio", "") or "").strip()
        commune = str(data.get("comuna", "") or "").strip()
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if not record_in_scope(lat=coords[1] if len(coords) > 1 else None, lng=coords[0] if coords else None,
                               row_neighborhood=neighborhood, row_commune=commune,
                               scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
            continue
        name = normalize_name(data.get("nombre", ""))
        if not name:
            continue
        candidates.append({
            "name": name, "entity_type": "Facility", "subtype": "labor_integration_center",
            "lat": coords[1] if len(coords) > 1 else None, "lng": coords[0] if coords else None,
            "origin_url": URL,
            "values": (("address", data.get("direccion", "")), ("phone", data.get("telefono", "")),
                       ("neighborhood", neighborhood), ("commune", commune)),
        })
    candidates = bounded(candidates, args.limit)
    print(f"Centros de integración laboral ({args.scope}): {len(candidates)}")
    if not args.write:
        return

    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        ids = await bulk_get_or_create_entities(conn, candidates)
        props = []
        for candidate in candidates:
            for key, value in candidate["values"]:
                if value:
                    props.append({"entity_id": ids[candidate["name"]], "key": key,
                                  "value": normalize_value(value), "value_type": "string",
                                  "confidence": 0.95, "origins": [URL]})
        await bulk_upsert_properties(conn, props, source_id)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
