import json

from fastapi import APIRouter, HTTPException, Query
from api.db import get_pool

router = APIRouter(tags=["entity"])


def decode_json(row: dict) -> dict:
    for key in ("all_names", "types", "origins", "payload"):
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])
    return row


@router.get("/entity/search")
async def entity_search(name: str = Query(..., min_length=2)):
    pool = await get_pool()
    pattern = f"%{name}%"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, name, entity_type, subtype, importance
               FROM entities WHERE is_active = TRUE AND canonical_id IS NULL
               AND (name LIKE $1 OR JSON_SEARCH(COALESCE(all_names, JSON_ARRAY()), 'one', $2) IS NOT NULL)
               ORDER BY importance DESC, name LIMIT 10""", pattern, name)
    return {"entities": [dict(row) for row in rows]}


@router.get("/entity/{entity_id}")
async def retrieve_entity(entity_id: str, include_history: bool = False, source: str | None = None,
                          historical: bool | None = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        entity = await conn.fetchrow("SELECT * FROM entities WHERE id = $1 AND is_active = TRUE AND canonical_id IS NULL", entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entidad no encontrada")
        conditions, params = ["p.entity_id = $1"], [entity_id]
        if not include_history:
            conditions.append("(p.valid_until IS NULL OR p.valid_until > CURRENT_DATE())")
        if source:
            params.append(source); conditions.append(f"s.source_name = ${len(params)}")
        if historical is True:
            conditions.append("(p.valid_until IS NOT NULL OR s.source_name = 'sinca')")
        elif historical is False:
            conditions.append("p.valid_until IS NULL AND COALESCE(s.source_name, '') <> 'sinca'")
        props = await conn.fetch(f"""SELECT p.`key`, p.value, p.value_type, p.valid_from, p.valid_until,
            p.confidence, p.origins, p.last_seen_at, s.source_name, s.source_url FROM properties p
            LEFT JOIN sources s ON s.id = p.source_id WHERE {' AND '.join(conditions)}
            ORDER BY p.`key`, p.valid_from DESC""", *params)
        rels = await conn.fetch("""SELECT r.relationship_type, r.direction, r.weight, r.confidence,
            e.id AS related_id, e.name AS related_name, e.entity_type AS related_type,
            CASE WHEN r.from_entity_id = $1 THEN 'outgoing' ELSE 'incoming' END AS relation_side
            FROM relationships r JOIN entities e ON e.id = CASE WHEN r.from_entity_id = $2 THEN r.to_entity_id ELSE r.from_entity_id END
            WHERE r.from_entity_id = $3 OR r.to_entity_id = $4""", entity_id, entity_id, entity_id, entity_id)
        tags = await conn.fetch("SELECT tag FROM tags WHERE entity_id = $1", entity_id)
        legal_summary = await conn.fetch("""SELECT record_type, COUNT(*) AS total,
            MIN(observed_period) AS first_period, MAX(observed_period) AS last_period
            FROM legal_entity_records WHERE entity_id=$1 GROUP BY record_type ORDER BY record_type""", entity_id)
    return {"entity": decode_json(dict(entity)), "properties": [decode_json(dict(p)) for p in props],
            "relationships": [dict(r) for r in rels], "tags": [t["tag"] for t in tags],
            "legal_records_summary": [dict(row) for row in legal_summary]}


@router.get("/entity/{entity_id}/legal-records")
async def legal_records(entity_id: str, record_type: str | None = Query(None, pattern="^(domicile|authority|assembly|balance)$"),
                        period: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Hechos IGJ históricos, paginados y filtrables sin perder su origen."""
    conditions, params = ["r.entity_id=$1"], [entity_id]
    if record_type:
        params.append(record_type); conditions.append(f"r.record_type=${len(params)}")
    if period:
        params.append(period); conditions.append(f"r.observed_period=${len(params)}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        entity = await conn.fetchval("SELECT id FROM entities WHERE id=$1 AND canonical_id IS NULL", entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entidad no encontrada")
        total = await conn.fetchval(f"SELECT COUNT(*) FROM legal_entity_records r WHERE {' AND '.join(conditions)}", *params)
        rows = await conn.fetch(f"""SELECT r.record_type,r.observed_period,r.event_date,r.payload,r.origins,
            r.first_seen_at,r.last_seen_at,s.source_name,s.source_url
            FROM legal_entity_records r JOIN sources s ON s.id=r.source_id
            WHERE {' AND '.join(conditions)} ORDER BY r.observed_period,r.record_type,r.event_date
            LIMIT {limit} OFFSET {offset}""", *params)
    return {"total": total, "limit": limit, "offset": offset,
            "records": [decode_json(dict(row)) for row in rows]}


@router.get("/entity/{entity_id}/{key}")
async def entity_dot_notation(entity_id: str, key: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""SELECT value, value_type, confidence, valid_from, valid_until, origins
            FROM active_properties WHERE entity_id = $1 AND `key` = $2 ORDER BY confidence DESC LIMIT 1""", entity_id, key)
    if not row:
        raise HTTPException(status_code=404, detail=f"Propiedad '{key}' no encontrada")
    return decode_json(dict(row))
