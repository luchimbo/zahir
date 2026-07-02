from fastapi import APIRouter, HTTPException, Query
from api.db import get_pool

router = APIRouter(tags=["entity"])


@router.get("/entity/search")
async def entity_search(name: str = Query(..., min_length=2)):
    """Buscar entidad por nombre (fuzzy). Devuelve entidades canónicas activas."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM search_entities($1, $2)",
            name, 10
        )
    return {"entities": [dict(r) for r in rows]}


@router.get("/entity/{entity_id}")
async def retrieve_entity(entity_id: str):
    """Entidad completa por UUID: datos, propiedades activas y relaciones."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        entity = await conn.fetchrow(
            """
            SELECT * FROM entities
            WHERE id = $1 AND is_active = true AND canonical_id IS NULL
            """,
            entity_id
        )
        if not entity:
            raise HTTPException(status_code=404, detail="Entidad no encontrada")

        props = await conn.fetch(
            """
            SELECT key, value, value_type, valid_from, valid_until,
                   confidence, origins, last_seen_at
            FROM active_properties
            WHERE entity_id = $1
            ORDER BY key
            """,
            entity_id
        )

        rels = await conn.fetch(
            """
            SELECT r.relationship_type, r.direction, r.weight, r.confidence,
                   e.id AS related_id, e.name AS related_name, e.entity_type AS related_type
            FROM relationships r
            JOIN entities e ON e.id = r.to_entity_id
            WHERE r.from_entity_id = $1
            """,
            entity_id
        )

        tags = await conn.fetch(
            "SELECT tag FROM tags WHERE entity_id = $1",
            entity_id
        )

    return {
        "entity":        dict(entity),
        "properties":    [dict(p) for p in props],
        "relationships": [dict(r) for r in rels],
        "tags":          [t["tag"] for t in tags],
    }


@router.get("/entity/{entity_id}/{key}")
async def entity_dot_notation(entity_id: str, key: str):
    """Dot-notation: devuelve el valor de una propiedad específica de una entidad."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT value, value_type, confidence, valid_from, valid_until, origins
            FROM active_properties
            WHERE entity_id = $1 AND key = $2
            ORDER BY confidence DESC
            LIMIT 1
            """,
            entity_id, key
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Propiedad '{key}' no encontrada")
    return dict(row)
