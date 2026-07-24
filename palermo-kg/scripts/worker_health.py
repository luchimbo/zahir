"""Healthcheck de worker para Railway: detecta fuentes bloqueadas o atrasadas."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.db import get_pool, close_pool


async def main():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            running = await conn.fetchval("SELECT COUNT(*) FROM source_sync_runs WHERE status='running'")
            overdue = await conn.fetchval("""SELECT COUNT(*) FROM source_checkpoints
                WHERE next_attempt_at IS NOT NULL AND next_attempt_at < CURRENT_TIMESTAMP""")
        print({"running_sources": running, "retry_ready": overdue})
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
