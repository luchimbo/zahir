"""Carga fiscalizaciones AGC sólo cuando la dirección coincide exactamente con Palermo KG."""
import argparse
import asyncio
import csv
import io
import re
import sys
import unicodedata
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name
from scrapers.shared.contract import add_source_arguments, bounded

SUPPORTS_SOURCE_CONTRACT = True

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/fiscalizaciones/inspecciones_realizadas_2024.csv"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", value)


async def main():
    parser = argparse.ArgumentParser()
    add_source_arguments(parser)
    args = parser.parse_args()
    conn = await get_conn()
    try:
        addresses = await conn.fetch(
            "SELECT DISTINCT p.value FROM properties p JOIN entities e ON e.id=p.entity_id "
            "WHERE p.key='address' AND e.canonical_id IS NULL"
        )
        known = {norm(row["value"]) for row in addresses if row["value"]}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(URL)
            response.raise_for_status()
        rows = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig", "replace")), delimiter=";")
        matches = [row for row in rows if norm(row.get("EntidadInspeccionable")) in known]
        matches = bounded(matches, args.limit)
        print(f"Fiscalizaciones con dirección ya verificada en el KG: {len(matches)} | scope={args.scope} | write={args.write}")
        if not args.write:
            return
        source_id = await get_source_id(conn, "ba_data")
        candidates = []
        for row in matches:
            ticket = row.get("N� ticket") or row.get("Nº ticket") or "sin-ticket"
            address = row.get("EntidadInspeccionable", "").strip()
            candidates.append({"name": normalize_name(f"Fiscalización AGC {ticket} - {address}"),
                               "entity_type": "HistoricalRecord", "subtype": "agc_inspection", "origin_url": URL,
                               "values": (("inspection_ticket", ticket), ("address", address),
                                          ("inspection_area", row.get("Area", "")),
                                          ("inspection_date", row.get("Fecha de inspecci�n") or row.get("Fecha de inspección") or ""))})
        ids = await bulk_get_or_create_entities(conn, candidates)
        properties = []
        for candidate in candidates:
            for key, value in candidate["values"]:
                if value:
                    properties.append({"entity_id": ids[candidate["name"]], "key": key, "value": value,
                                       "value_type": "string", "confidence": 0.95, "origins": [URL]})
        await bulk_upsert_properties(conn, properties, source_id)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
