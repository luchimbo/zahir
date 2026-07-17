"""Enriquece SMP ya conocidos con edificabilidad oficial GCBA/CUR3D."""
import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import bulk_upsert_properties, get_conn, get_source_id, mark_source_synced

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/superficie-edificable-en-planta/superficie_edificable.csv"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT entity_id::text, upper(value) AS smp FROM properties WHERE key='smp'")
        entity_ids = defaultdict(set)
        for row in rows:
            entity_ids[row["smp"]].add(row["entity_id"])
        aggregates = defaultdict(lambda: {"codes": set(), "types": set(), "heights": []})
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("GET", URL) as response:
                response.raise_for_status()
                lines = [line async for line in response.aiter_lines()]
        for row in csv.DictReader(lines):
            smp = (row.get("smp") or "").upper()
            if smp not in entity_ids:
                continue
            data = aggregates[smp]
            if row.get("edificabil"):
                data["codes"].add(row["edificabil"])
            if row.get("tipo"):
                data["types"].add(row["tipo"])
            data["heights"].extend(x for x in (number(row.get("altura_ini")), number(row.get("altura_fin"))) if x is not None)
        print(f"SMP enriquecibles: {len(aggregates)}")
        if not args.write:
            return
        source_id = await get_source_id(conn, "ba_data")
        props = []
        for smp, data in aggregates.items():
            values = [("urban_building_code", ", ".join(sorted(data["codes"])), "string"),
                      ("buildable_segment_types", ", ".join(sorted(data["types"])), "string")]
            if data["heights"]:
                values += [("buildable_height_min_m", str(min(data["heights"])), "number"),
                           ("buildable_height_max_m", str(max(data["heights"])), "number")]
            for entity_id in entity_ids[smp]:
                for key, value, value_type in values:
                    if value:
                        props.append({"entity_id": entity_id, "key": key, "value": value, "value_type": value_type,
                                      "confidence": 0.95, "origins": [URL]})
        await bulk_upsert_properties(conn, props, source_id)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
