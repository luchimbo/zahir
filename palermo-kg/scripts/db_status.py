"""Estado operativo de TiDB para el Knowledge Graph."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.db import close_pool, get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM entities WHERE canonical_id IS NULL")
        rows = await conn.fetch("""SELECT entity_type, subtype, COUNT(*) AS n FROM entities
            WHERE canonical_id IS NULL GROUP BY entity_type, subtype ORDER BY n DESC LIMIT 25""")
        sources = await conn.fetch("""SELECT s.source_name, COUNT(p.id) AS props, s.scraped_at
            FROM sources s LEFT JOIN properties p ON p.source_id=s.id
            GROUP BY s.id, s.source_name, s.scraped_at ORDER BY props DESC LIMIT 15""")
    await close_pool()
    print(f"\nTotal entidades canónicas: {total}\n")
    for row in rows:
        print(f"{row['entity_type']:<16} {(row['subtype'] or ''):<22} {row['n']:>6}")
    print("\nFuentes:")
    for row in sources:
        print(f"{row['source_name']:<25} {row['props']:>6}  {row['scraped_at'] or 'pendiente'}")


if __name__ == "__main__":
    asyncio.run(main())
