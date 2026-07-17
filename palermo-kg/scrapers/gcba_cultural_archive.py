"""Ingesta actividades culturales históricas de Palermo como HistoricalRecord."""
import argparse
import asyncio
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-cultura/actividades-culturales/actividades-culturales-2022.geojson"


def clean(value) -> str:
    return "" if value is None else str(value).strip()


def coordinate(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.get(URL)
        response.raise_for_status()
        features = response.json().get("features", [])

    candidates = []
    for feature in features:
        data = feature.get("properties") or {}
        if clean(data.get("barrio")).upper() != "PALERMO":
            continue
        record_id = clean(data.get("id"))
        title = normalize_name(clean(data.get("actividad")))
        if not record_id or not title:
            continue
        candidates.append({
            "name": f"Actividad Cultural {title} (GCBA {record_id})",
            "entity_type": "HistoricalRecord",
            "subtype": "cultural_activity_archive",
            "lat": coordinate(data.get("lat")),
            "lng": coordinate(data.get("long")),
            "origin_url": URL,
            "values": (
                ("title", title, "string"), ("venue", clean(data.get("lugar")), "string"),
                ("address", clean(data.get("direccion")), "string"), ("neighborhood", "Palermo", "string"),
                ("start_date", clean(data.get("fecha_ini")), "date"), ("end_date", clean(data.get("fecha_fin")), "date"),
                ("activity_type", clean(data.get("tipo_actividad")), "string"),
                ("discipline", clean(data.get("disciplina")), "string"),
                ("is_free", clean(data.get("Gratuita")).lower(), "boolean"),
                ("source_url", clean(data.get("Links")), "url"),
            ),
        })
    print(f"Actividades culturales históricas de Palermo: {len(candidates)}")
    if not args.write:
        return
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        ids = await bulk_get_or_create_entities(conn, candidates)
        props = []
        for candidate in candidates:
            for key, value, value_type in candidate["values"]:
                if value:
                    props.append({"entity_id": ids[candidate["name"]], "key": key,
                                  "value": value if value_type != "string" else normalize_value(value),
                                  "value_type": value_type, "confidence": 0.95, "origins": [URL]})
        await bulk_upsert_properties(conn, props, source_id)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
