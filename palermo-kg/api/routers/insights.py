from fastapi import APIRouter, Query
from api.db import get_pool

router = APIRouter(tags=["insights"])


@router.get("/insights/operations")
async def operations_overview():
    """Resumen para operar fuentes sin inspeccionar tablas manualmente."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        totals = await conn.fetchrow("""SELECT
            (SELECT COUNT(*) FROM entities WHERE is_active=TRUE AND canonical_id IS NULL) AS entities,
            (SELECT COUNT(*) FROM active_properties) AS active_properties,
            (SELECT COUNT(*) FROM sources WHERE scraped_at IS NOT NULL) AS synced_sources,
            (SELECT COUNT(*) FROM sources) AS sources""")
        runs = await conn.fetch("""SELECT s.source_name, r.status, r.started_at, r.completed_at, r.error_message
            FROM source_sync_runs r JOIN sources s ON s.id=r.source_id
            WHERE r.id=(SELECT r2.id FROM source_sync_runs r2 WHERE r2.source_id=s.id ORDER BY r2.started_at DESC LIMIT 1)
            ORDER BY r.started_at DESC LIMIT 20""")
    return {"totals": dict(totals), "latest_runs": [dict(row) for row in runs]}


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
                   COUNT(DISTINCT CASE WHEN e.lat IS NOT NULL AND e.lng IS NOT NULL THEN p.entity_id END) AS geocoded_entities
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
              (SELECT COUNT(*) FROM (
                 SELECT 1 FROM entities WHERE is_active=TRUE AND canonical_id IS NULL
                 GROUP BY LOWER(name), entity_type HAVING COUNT(*) > 1
               ) AS unresolved_duplicates) AS duplicates,
              (SELECT COUNT(*) FROM entities WHERE canonical_id IS NOT NULL) AS canonicalized_duplicates,
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
            SELECT query_mode, COUNT(*) AS total, SUM(CASE WHEN is_gap THEN 1 ELSE 0 END) AS gaps
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
