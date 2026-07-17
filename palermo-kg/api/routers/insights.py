from fastapi import APIRouter, Query
from api.db import get_pool

router = APIRouter(tags=["insights"])


@router.get("/insights/source-health")
async def source_health():
    """Frescura y cobertura por fuente, para operación manual."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.source_name, s.tier, s.scraped_at,
                   COUNT(p.id) AS properties,
                   COUNT(DISTINCT p.entity_id) AS entities,
                   MAX(p.last_seen_at) AS last_seen_at,
                   COUNT(DISTINCT p.entity_id) FILTER (WHERE e.lat IS NOT NULL AND e.lng IS NOT NULL) AS geocoded_entities
            FROM sources s
            LEFT JOIN properties p ON p.source_id = s.id
            LEFT JOIN entities e ON e.id = p.entity_id
            GROUP BY s.id
            ORDER BY properties DESC, s.source_name
            """
        )
    return {"rows": [dict(row) for row in rows]}


@router.get("/insights/data-quality")
async def data_quality():
    """Indicadores accionables para limpieza y priorización."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM entities WHERE canonical_id IS NOT NULL) AS duplicates,
              (SELECT COUNT(*) FROM entities WHERE canonical_id IS NULL AND is_active AND (lat IS NULL OR lng IS NULL)) AS canonical_without_coordinates,
              (SELECT COUNT(*) FROM properties WHERE valid_until IS NOT NULL AND valid_until <= CURRENT_DATE) AS expired_properties,
              (SELECT COUNT(*) FROM relationships WHERE confidence < 0.75) AS low_confidence_relationships
            """
        )
    return dict(result)


@router.get("/insights/query-gaps")
async def query_gaps(limit: int = Query(default=25, ge=1, le=100)):
    """Consultas sin resultados, agrupadas por texto/filtros."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                COALESCE(NULLIF(query_text, ''), query_mode || ':' ||
                    COALESCE(entity_type, '*') || '/' || COALESCE(subtype, '*') ||
                    '/' || COALESCE(tag, '*')) AS gap,
                query_mode,
                entity_type,
                subtype,
                tag,
                COUNT(*) AS hits,
                MAX(created_at) AS last_seen_at
            FROM query_log
            WHERE is_gap = true
            GROUP BY gap, query_mode, entity_type, subtype, tag
            ORDER BY hits DESC, last_seen_at DESC
            LIMIT $1
            """,
            limit,
        )
    return {"rows": [dict(row) for row in rows], "total": len(rows)}


@router.get("/insights/query-summary")
async def query_summary():
    """Resumen operativo de consultas y gaps."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM query_log")
        gaps = await conn.fetchval("SELECT COUNT(*) FROM query_log WHERE is_gap = true")
        by_mode = await conn.fetch(
            """
            SELECT query_mode, COUNT(*) AS total, COUNT(*) FILTER (WHERE is_gap) AS gaps
            FROM query_log
            GROUP BY query_mode
            ORDER BY total DESC
            """
        )
    return {
        "total": total,
        "gaps": gaps,
        "gap_rate": float(gaps / total) if total else 0,
        "by_mode": [dict(row) for row in by_mode],
    }
