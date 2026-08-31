"""Reporte de corte CABA: cobertura territorial y datos pendientes, sólo lectura."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.db import close_pool, get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        hierarchy = await conn.fetch("""SELECT e.name, e.subtype, COUNT(r.id) links
            FROM entities e LEFT JOIN relationships r ON r.to_entity_id=e.id
            WHERE e.entity_type='Location' AND (e.name='Ciudad Autónoma de Buenos Aires'
              OR e.name LIKE 'Comuna %' OR EXISTS (SELECT 1 FROM properties p WHERE p.entity_id=e.id AND p.`key`='geography_level' AND p.value='neighborhood'))
            GROUP BY e.id,e.name,e.subtype ORDER BY e.name""")
        outside = await conn.fetchval("""SELECT COUNT(*) FROM entities e WHERE e.is_active=TRUE
            AND e.canonical_id IS NULL AND e.entity_type <> 'Location' AND e.lat IS NOT NULL AND NOT EXISTS
            (SELECT 1 FROM relationships r JOIN entities n ON n.id=r.to_entity_id
             WHERE r.from_entity_id=e.id AND r.relationship_type='LOCATED_IN' AND n.entity_type='Location'
             AND n.name NOT LIKE 'Comuna %' AND n.name <> 'Ciudad Autónoma de Buenos Aires')""")
        source_rows = await conn.fetch("""SELECT s.source_name, COALESCE(m.coverage, JSON_OBJECT()) coverage
            FROM sources s LEFT JOIN source_sync_runs r ON r.source_id=s.id
              AND r.id=(SELECT x.id FROM source_sync_runs x WHERE x.source_id=s.id ORDER BY x.started_at DESC LIMIT 1)
            LEFT JOIN source_run_metrics m ON m.run_id=r.id ORDER BY s.source_name""")
    await close_pool()
    print(json.dumps({"locations": [dict(row) for row in hierarchy], "unassigned_geocoded_entities": outside,
                      "source_coverage": [dict(row) for row in source_rows]}, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
