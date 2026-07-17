from fastapi import APIRouter, Query as Q
from api.db import get_pool
from api.query_log import log_query

router = APIRouter(tags=["query"])


@router.get("/query")
async def knowledge_query(
    entity_type: str | None = None,
    subtype:     str | None = None,
    tag:         str | None = None,
    source:      str | None = None,
    historical:  bool | None = None,
    limit:       int = Q(default=20, ge=1, le=100),
    offset:      int = Q(default=0, ge=0),
):
    """
    JSON tabular estructurado. Filtra entidades canónicas activas.
    Parámetros: entity_type, subtype, tag, limit, offset.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = ["e.is_active = true", "e.canonical_id IS NULL"]
        params = []

        if entity_type:
            params.append(entity_type)
            conditions.append(f"e.entity_type = ${len(params)}")

        if subtype:
            params.append(subtype)
            conditions.append(f"e.subtype = ${len(params)}")

        if source or historical is not None:
            joins = " JOIN properties sp ON sp.entity_id = e.id JOIN sources ss ON ss.id = sp.source_id "
            if source:
                params.append(source); conditions.append(f"ss.source_name = ${len(params)}")
            if historical is not None:
                params.append(historical)
                conditions.append(f"(${len(params)} OR (sp.valid_until IS NULL AND ss.source_name != 'sinca'))")
        else:
            joins = ""

        where = " AND ".join(conditions)

        if tag:
            params.append(tag)
            sql = f"""
                SELECT DISTINCT e.id, e.name, e.entity_type, e.subtype,
                       e.lat, e.lng, e.importance, e.description
                FROM entities e {joins}
                JOIN tags t ON t.entity_id = e.id
                WHERE {where} AND t.tag = ${len(params)}
                ORDER BY e.importance DESC
                LIMIT {limit} OFFSET {offset}
            """
        else:
            sql = f"""
                SELECT e.id, e.name, e.entity_type, e.subtype,
                       e.lat, e.lng, e.importance, e.description
                FROM entities e {joins}
                WHERE {where}
                ORDER BY e.importance DESC
                LIMIT {limit} OFFSET {offset}
            """

        rows = await conn.fetch(sql, *params)

    await log_query(
        query_mode="query",
        query_text=None,
        entity_type=entity_type,
        subtype=subtype,
        tag=tag,
        result_count=len(rows),
        entity_types_returned=sorted({r["entity_type"] for r in rows}),
    )

    return {
        "total":  len(rows),
        "limit":  limit,
        "offset": offset,
        "rows":   [dict(r) for r in rows],
    }
