import json
from fastapi import APIRouter, Query
from api.db import get_pool
from api.query_log import log_query

router = APIRouter(tags=["search"])
STOP_WORDS = {"en", "de", "la", "el", "los", "las", "un", "una", "y", "o", "palermo", "caba", "buenos", "aires"}


def tokenize(text: str) -> set[str]:
    return {word for word in "".join(c if c.isalnum() else " " for c in text.lower()).split() if word not in STOP_WORDS}


def score_entity(query_tokens: set[str], item: dict) -> tuple[float, int]:
    """Score a retrieved candidate locally so ordering is deterministic on TiDB."""
    if not query_tokens:
        return 0.0, 0

    name = str(item.get("name") or "")
    name_tokens = tokenize(name)
    subtype_tokens = tokenize(str(item.get("subtype") or ""))
    description_tokens = tokenize(str(item.get("description") or ""))
    properties = item.get("properties", [])
    legal_records = item.get("legal_records", [])
    property_text = " ".join(
        f"{prop.get('key', '')} {prop.get('value', '')}" for prop in properties
    ) + " " + " ".join(f"{record.get('record_type', '')} {record.get('payload', '')}" for record in legal_records)
    property_tokens = tokenize(property_text)

    name_matches = len(query_tokens & name_tokens)
    subtype_matches = len(query_tokens & subtype_tokens)
    description_matches = len(query_tokens & description_tokens)
    property_matches = len(query_tokens & property_tokens)
    coverage = len(query_tokens)
    property_hits = sum(
        1 for prop in properties
        if query_tokens & tokenize(f"{prop.get('key', '')} {prop.get('value', '')}")
    )

    score = (
        0.62 * name_matches / coverage
        + 0.30 * subtype_matches / coverage
        + 0.10 * description_matches / coverage
        + 0.16 * property_matches / coverage
        + min(float(item.get("importance") or 0), 100) / 2500
    )
    normalized_name = " ".join(name.lower().split())
    normalized_query = " ".join(sorted(query_tokens))
    if normalized_name == normalized_query or name_matches == coverage == len(name_tokens):
        score += 0.12
    return min(round(score, 4), 1.0), property_hits


@router.get("/search")
async def knowledge_search(q: str = Query(..., min_length=2), min_score: float = Query(0.25, ge=0, le=1),
                           limit: int = Query(10, ge=1, le=50)):
    """Búsqueda portable para TiDB: nombres, descripciones y propiedades activas."""
    tokens = tokenize(q) or {q.lower()}
    patterns = [f"%{token}%" for token in tokens]
    predicates = []
    params = []
    for pattern in patterns:
        predicates.append("(LOWER(e.name) LIKE $%d OR LOWER(e.description) LIKE $%d OR LOWER(e.subtype) LIKE $%d OR EXISTS (SELECT 1 FROM active_properties p WHERE p.entity_id=e.id AND (LOWER(p.`key`) LIKE $%d OR LOWER(p.value) LIKE $%d)) OR EXISTS (SELECT 1 FROM legal_entity_records lr WHERE lr.entity_id=e.id AND LOWER(CAST(lr.payload AS CHAR)) LIKE $%d))" % tuple([len(params)+1] * 6))
        params.extend([pattern] * 6)
    candidate_limit = min(limit * 20, 300)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""SELECT DISTINCT e.id, e.name, e.entity_type, e.subtype, e.description,
            e.importance, e.origin_url, e.lat, e.lng FROM entities e
            WHERE e.is_active=TRUE AND e.canonical_id IS NULL AND ({' OR '.join(predicates)})
            ORDER BY e.importance DESC, e.name LIMIT {candidate_limit}""", *params)
        ids = [row["id"] for row in rows]
        props = []
        records = []
        if ids:
            placeholders = ", ".join(f"${i+1}" for i in range(len(ids)))
            props = await conn.fetch(f"SELECT entity_id, `key`, value, confidence, origins FROM active_properties WHERE entity_id IN ({placeholders}) ORDER BY confidence DESC", *ids)
            records = await conn.fetch(f"SELECT entity_id,record_type,payload FROM legal_entity_records WHERE entity_id IN ({placeholders})", *ids)
    grouped = {}
    for prop in props:
        item = dict(prop)
        if isinstance(item.get("origins"), str): item["origins"] = json.loads(item["origins"])
        grouped.setdefault(item["entity_id"], []).append(item)
    grouped_records = {}
    for record in records:
        item = dict(record)
        if isinstance(item.get("payload"), str):
            item["payload"] = json.loads(item["payload"])
        grouped_records.setdefault(item["entity_id"], []).append(item)
    results = []
    for row in rows:
        item = dict(row)
        item["properties"] = grouped.get(item["id"], [])
        item["legal_records"] = grouped_records.get(item["id"], [])
        item["score"], item["property_hits"] = score_entity(tokens, item)
        if item["score"] < min_score:
            continue
        results.append(item)
    results.sort(key=lambda item: (item["score"], item["property_hits"], item.get("importance") or 0, item["name"].lower()), reverse=True)
    results = results[:limit]
    await log_query(query_mode="search", query_text=q, result_count=len(results), entity_types_returned=sorted({r["entity_type"] for r in results}))
    return {"query": q, "min_score": min_score, "results": results}
