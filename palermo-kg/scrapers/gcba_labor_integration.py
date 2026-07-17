"""Centros de Integración Laboral de Palermo desde GCBA."""
import argparse, asyncio, sys
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/centros-integracion-laboral/centros_integracion_laboral.geojson"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(URL)
        response.raise_for_status()
        features = response.json()["features"]

    candidates = []
    for feature in features:
        data = feature.get("properties") or {}
        if str(data.get("barrio", "")).upper() != "PALERMO":
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        name = normalize_name(data.get("nombre", ""))
        if not name:
            continue
        candidates.append({
            "name": name, "entity_type": "Facility", "subtype": "labor_integration_center",
            "lat": coords[1] if len(coords) > 1 else None, "lng": coords[0] if coords else None,
            "origin_url": URL,
            "values": (("address", data.get("direccion", "")), ("phone", data.get("telefono", "")),
                       ("neighborhood", "Palermo"), ("commune", str(data.get("comuna", "")))),
        })
    print(f"Centros de integración laboral de Palermo: {len(candidates)}")
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
