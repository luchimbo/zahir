"""Estado actual de la DB."""
import asyncio, os
import asyncpg
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(dsn=os.getenv("DATABASE_URL"))
    total = await conn.fetchval("SELECT COUNT(*) FROM entities WHERE canonical_id IS NULL")
    rows = await conn.fetch(
        "SELECT entity_type, subtype, COUNT(*) as n FROM entities "
        "WHERE canonical_id IS NULL GROUP BY entity_type, subtype ORDER BY n DESC LIMIT 25"
    )
    sources = await conn.fetch(
        "SELECT s.source_name, COUNT(p.id) as props FROM sources s "
        "LEFT JOIN properties p ON p.source_id = s.id "
        "GROUP BY s.source_name ORDER BY props DESC LIMIT 15"
    )
    await conn.close()

    print(f"\nTotal entidades canonicas: {total}\n")
    print(f"{'Tipo':<16} {'Subtype':<22} {'Count':>6}")
    print("-" * 46)
    for r in rows:
        print(f"{r['entity_type']:<16} {(r['subtype'] or ''):<22} {r['n']:>6}")

    print(f"\n{'Fuente':<25} {'Propiedades':>12}")
    print("-" * 38)
    for r in sources:
        print(f"{r['source_name']:<25} {r['props']:>12}")

asyncio.run(main())
