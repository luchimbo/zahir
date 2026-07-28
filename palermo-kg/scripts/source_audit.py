"""Reporte operativo, de solo lectura, para las fuentes del knowledge graph.

Muestra cobertura, frescura de las propiedades y calidad geográfica por fuente.
No modifica entidades, propiedades ni fuentes.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.db import close_pool, get_pool


SQL = """
SELECT
    s.source_name,
    s.tier,
    s.scraped_at,
    COUNT(DISTINCT p.entity_id) AS entities,
    COUNT(p.id) AS properties,
    MAX(p.last_seen_at) AS last_property_seen_at,
    COUNT(DISTINCT CASE WHEN e.lat IS NOT NULL AND e.lng IS NOT NULL THEN p.entity_id END)
        AS geocoded_entities
FROM sources s
LEFT JOIN properties p ON p.source_id = s.id
LEFT JOIN entities e ON e.id = p.entity_id
GROUP BY s.id, s.source_name, s.tier, s.scraped_at
ORDER BY properties DESC, s.source_name
"""


def age_label(value: datetime | None) -> str:
    if value is None:
        return "sin registro"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    days = max(0, (datetime.now(timezone.utc) - value).days)
    return f"{days} d"


async def main():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(SQL)
    finally:
        await close_pool()

    print("\nAuditoría de fuentes — Palermo Knowledge Graph\n")
    print(
        f"{'Fuente':<22} {'Tier':>4} {'Entidades':>10} {'Props':>10} "
        f"{'Geo':>8} {'Última prop.':>15} {'Último sync':>14}"
    )
    print("-" * 103)
    for row in rows:
        entities = row["entities"]
        geocoded = row["geocoded_entities"]
        geo = "-" if not entities else f"{geocoded / entities:.0%}"
        print(
            f"{row['source_name']:<22} {row['tier']:>4} {entities:>10} "
            f"{row['properties']:>10} {geo:>8} "
            f"{age_label(row['last_property_seen_at']):>15} "
            f"{age_label(row['scraped_at']):>14}"
        )


if __name__ == "__main__":
    asyncio.run(main())
