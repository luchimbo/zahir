import json
from api.db import get_pool


async def log_query(
    *,
    query_mode: str,
    result_count: int,
    query_text: str | None = None,
    entity_type: str | None = None,
    subtype: str | None = None,
    tag: str | None = None,
    entity_types_returned: list[str] | None = None,
    source: str = "api",
) -> None:
    """Best-effort query logging. Never break user-facing endpoints."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO query_log (
                    query_text, query_mode, entity_type, subtype, tag,
                    result_count, entity_types_returned, source
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                query_text,
                query_mode,
                entity_type,
                subtype,
                tag,
                result_count,
                json.dumps(entity_types_returned or []),
                source,
            )
    except Exception:
        return
