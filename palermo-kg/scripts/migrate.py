"""Aplica migraciones SQL idempotentes."""
import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS = [
    Path("db/11_query_log.sql"),
]


async def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no configurada")

    conn = await asyncpg.connect(dsn=database_url)
    try:
        for migration in MIGRATIONS:
            sql = migration.read_text(encoding="utf-8")
            print(f"Aplicando {migration}...")
            await conn.execute(sql)
        print("OK migraciones aplicadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
