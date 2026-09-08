"""Consultas trazables de series temporales nacionales."""
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from api.db import get_pool
from api.routers.entity import decode_json

router = APIRouter(tags=["observations"])


def _series_conditions(alias: str, series_key: str | None = None, source: str | None = None,
                       from_date: date | None = None, to_date: date | None = None):
    conditions, params = [], []
    if series_key:
        params.append(series_key)
        conditions.append(f"{alias}.series_key=${len(params)}")
    if source:
        params.append(source)
        conditions.append(f"s.source_name=${len(params)}")
    if from_date:
        params.append(from_date)
        conditions.append(f"{alias}.observed_at>=${len(params)}")
    if to_date:
        params.append(to_date)
        conditions.append(f"{alias}.observed_at<=${len(params)}")
    return conditions, params


async def latest_series_points(conn, series_key: str, source: str | None = None,
                               from_date: date | None = None, to_date: date | None = None,
                               limit: int = 200, offset: int = 0) -> list[dict]:
    """Devuelve una sola revisión: la última vista para cada período/fuente."""
    conditions, params = _series_conditions("r", series_key, source, from_date, to_date)
    # source sólo se usa en el subquery para que el join mantenga los mismos
    # placeholders; `s` está disponible allí mediante el JOIN.
    if source:
        conditions = [condition.replace("s.source_name", "rs.source_name") for condition in conditions]
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = await conn.fetch(f"""
        SELECT o.series_key,o.observed_at,o.observed_period,o.frequency,o.value,o.value_text,o.unit,
               o.payload,o.origins,o.confidence,o.first_seen_at,o.last_seen_at,
               e.id AS entity_id,e.name AS entity_name,e.entity_type,s.source_name,s.source_url
        FROM observations o
        JOIN sources s ON s.id=o.source_id
        JOIN entities e ON e.id=o.entity_id
        JOIN (
            SELECT r.source_id,r.series_key,r.observed_period,MAX(r.first_seen_at) AS latest_first_seen
            FROM observations r
            JOIN sources rs ON rs.id=r.source_id
            WHERE {where}
            GROUP BY r.source_id,r.series_key,r.observed_period
        ) latest ON latest.source_id=o.source_id AND latest.series_key=o.series_key
            AND latest.observed_period=o.observed_period AND latest.latest_first_seen=o.first_seen_at
        WHERE e.canonical_id IS NULL
        ORDER BY o.observed_at ASC,o.first_seen_at ASC
        LIMIT {limit} OFFSET {offset}
        """, *params)
    return [decode_json(dict(row)) for row in rows]


@router.get("/series")
async def series_catalog(source: str | None = None, q: str | None = Query(None, min_length=2),
                         limit: int = Query(100, ge=1, le=250)):
    conditions, params = ["e.canonical_id IS NULL"], []
    if source:
        params.append(source)
        conditions.append(f"s.source_name=${len(params)}")
    if q:
        params.extend([f"%{q}%", f"%{q}%"])
        conditions.append(f"(o.series_key LIKE ${len(params)-1} OR e.name LIKE ${len(params)})")
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT o.series_key,o.frequency,o.unit,e.id AS entity_id,e.name AS entity_name,e.entity_type,
                   s.source_name,s.source_url,COUNT(*) AS points,MIN(o.observed_at) AS first_at,
                   MAX(o.observed_at) AS last_at
            FROM observations o JOIN entities e ON e.id=o.entity_id JOIN sources s ON s.id=o.source_id
            WHERE {' AND '.join(conditions)}
            GROUP BY o.series_key,o.frequency,o.unit,e.id,e.name,e.entity_type,s.source_name,s.source_url
            ORDER BY o.series_key,s.source_name LIMIT {limit}
            """, *params)
    result = [dict(row) for row in rows]
    return {"total": len(result), "rows": result}


@router.get("/series/{series_key}")
async def series_points(series_key: str, source: str | None = None,
                        from_date: date | None = Query(None, alias="from"),
                        to_date: date | None = Query(None, alias="to"),
                        limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await latest_series_points(conn, series_key, source, from_date, to_date, limit, offset)
    return {"total": len(rows), "limit": limit, "offset": offset, "points": rows}

