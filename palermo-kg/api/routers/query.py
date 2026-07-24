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
    min_rating:  float | None = Q(default=None, ge=0, le=5),
    price_range: str | None = None,
    accessible:  bool | None = None,
    delivery:    bool | None = None,
    outdoor:     bool | None = None,
    pet_friendly: bool | None = None,
    geocoded:    bool | None = None,
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

        if min_rating is not None:
            params.append(min_rating)
            conditions.append(f"""EXISTS (SELECT 1 FROM active_properties rating
                WHERE rating.entity_id=e.id AND rating.`key`='rating'
                AND CAST(rating.value AS DECIMAL(4,2)) >= ${len(params)})""")
        if price_range:
            params.append(price_range)
            conditions.append(f"""EXISTS (SELECT 1 FROM active_properties price
                WHERE price.entity_id=e.id AND price.`key`='price_range' AND price.value=${len(params)})""")
        if accessible is not None:
            params.append("true" if accessible else "false")
            conditions.append(f"""EXISTS (SELECT 1 FROM active_properties access
                WHERE access.entity_id=e.id AND access.`key`='is_wheelchair_accessible'
                AND LOWER(access.value)=${len(params)})""")
        for property_key, expected in (("has_delivery", delivery), ("has_outdoor_seating", outdoor), ("is_pet_friendly", pet_friendly)):
            if expected is not None:
                params.append("true" if expected else "false")
                conditions.append(f"""EXISTS (SELECT 1 FROM active_properties feature
                    WHERE feature.entity_id=e.id AND feature.`key`='{property_key}'
                    AND LOWER(feature.value)=${len(params)})""")
        if geocoded is not None:
            conditions.append("e.lat IS NOT NULL AND e.lng IS NOT NULL" if geocoded else "(e.lat IS NULL OR e.lng IS NULL)")

        where = " AND ".join(conditions)

        if tag:
            params.append(tag)
            tagged_where = f"{where} AND t.tag = ${len(params)}"
            sql = f"""
                SELECT DISTINCT e.id, e.name, e.entity_type, e.subtype,
                       e.lat, e.lng, e.importance, e.description
                FROM entities e {joins}
                JOIN tags t ON t.entity_id = e.id
                WHERE {tagged_where}
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
        total_sql = (
            f"SELECT COUNT(DISTINCT e.id) FROM entities e {joins} JOIN tags t ON t.entity_id=e.id WHERE {tagged_where}"
            if tag else f"SELECT COUNT(DISTINCT e.id) FROM entities e {joins} WHERE {where}"
        )
        total = await conn.fetchval(total_sql, *params)

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
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "rows":   [dict(r) for r in rows],
    }
