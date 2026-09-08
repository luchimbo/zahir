"""Serie histórica diaria oficial de YPFD en BYMA Open Data."""
import argparse
import asyncio
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.byma_client import chart_history, make_client, parse_chart_history
from scrapers.shared.contract import SourceResult, add_source_arguments, bounded
from scrapers.shared.db_helpers import (bulk_upsert_observations, ensure_source, get_conn,
    get_or_create_entity, latest_observation_date, mark_source_synced, upsert_property,
    upsert_relationship)

SOURCE_NAME = "byma_ypf"
SOURCE_URL = "https://open.bymadata.com.ar"
HISTORY_PATH = "chart/historical-series/history"
SYMBOL = "YPFD 24hs"
SERIES = (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))


def parse_history_payload(payload: dict) -> list[dict]:
    return parse_chart_history(payload)


async def link_to_legal_entity(conn, security_id: str):
    row = await conn.fetchrow("""SELECT id FROM entities WHERE entity_type='LegalEntity'
        AND canonical_id IS NULL AND (name LIKE $1 OR name='Ypf S.A.') LIMIT 1""", "YPF S.A.%")
    if row:
        await upsert_relationship(conn, security_id, "RELATED_TO", str(row["id"]),
                                  confidence=0.9, origins=[SOURCE_URL])


async def main():
    parser = argparse.ArgumentParser(description="BYMA Open Data — histórico YPFD")
    add_source_arguments(parser)
    args = parser.parse_args()
    if args.neighborhood or args.commune:
        return SourceResult(skipped=1, errors=["Fuente nacional: no admite acotar por barrio/comuna."])

    result = SourceResult()
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, SOURCE_NAME, SOURCE_URL, 1)
        since = date.fromisoformat(args.since) if args.since else await latest_observation_date(
            conn, source_id, "byma_ypfd_close")
        start = int(datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc).timestamp()) if since else 0
        async with make_client() as client:
            payload, origin = await chart_history(client, HISTORY_PATH, SYMBOL, start, int(time.time()))
        all_points = parse_history_payload(payload)
        points = bounded(all_points, args.limit)
        result.seen, result.accepted = len(all_points), len(points)
        if not args.write:
            return result

        entity_id = await get_or_create_entity(conn, "YPF S.A. (YPFD)", "Security", subtype="equity",
            origin_url=SOURCE_URL, source_id=source_id, external_id="YPFD")
        for key, value in (("ticker", "YPFD"), ("market", "BYMA"), ("currency", "ARS"),
                           ("issuer_name", "YPF S.A.")):
            await upsert_property(conn, entity_id, key, value, "string", source_id, origins=[origin])
        await link_to_legal_entity(conn, entity_id)
        observations = [
            {"entity_id": entity_id, "series_key": f"byma_ypfd_{name}", "observed_at": row["date"],
             "observed_period": row["date"].isoformat(), "frequency": "daily", "value": row[field],
             "unit": "shares" if name == "volume" else "ARS",
             "payload": {**row, "date": row["date"].isoformat()}, "origins": [origin]}
            for row in points for name, field in SERIES if row.get(field) is not None
        ]
        result.written = await bulk_upsert_observations(conn, observations, source_id)
        result.checkpoint = max((row["date"].isoformat() for row in points), default=None)
        if result.ok:
            await mark_source_synced(conn, source_id)
        return result
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
