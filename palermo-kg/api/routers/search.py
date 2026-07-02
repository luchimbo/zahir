from fastapi import APIRouter, Query
from api.db import get_pool
from api.query_log import log_query

router = APIRouter(tags=["search"])


# Palabras muy comunes que no deberian dar peso por si solas
STOP_WORDS = {"en", "de", "la", "el", "los", "las", "un", "una", "y", "o",
              "palermo", "caba", "buenos", "aires"}

TYPE_BOOST = {
    "farmacia": ("Facility", "farmacia"),
    "farmacia de turno": ("Facility", "farmacia"),
    "hospital": ("Facility", "hospital"),
    "escuela": ("Facility", "escuela"),
    "subte": ("Transport", None),
    "colectivo": ("Transport", None),
    "ecobici": ("Transport", "ecobici"),
    "restaurante": ("Organization", "restaurant"),
    "restaurant": ("Organization", "restaurant"),
    "bar": ("Organization", "bar"),
    "cafe": ("Organization", "cafe"),
    "cajero": ("Facility", "cajero_atm"),
    "atm": ("Facility", "cajero_atm"),
}


def normalize(text: str) -> str:
    return "".join(
        c if c.isalnum() else " "
        for c in text.lower().strip()
    )


def tokenize(text: str) -> set[str]:
    tokens = []
    for t in normalize(text).split():
        if not t or t in STOP_WORDS:
            continue
        # Stemming muy simple para espanol
        if t.endswith("es") and len(t) > 3:
            tokens.append(t[:-2])
        elif t.endswith("s") and len(t) > 3:
            tokens.append(t[:-1])
        else:
            tokens.append(t)
        tokens.append(t)
    return set(tokens)


def type_boost(query: str, entity_type: str, subtype: str | None) -> float:
    q = query.lower()
    for keyword, (et, st) in TYPE_BOOST.items():
        if keyword in q and entity_type == et and (st is None or subtype == st):
            return 0.18
        if keyword in q and entity_type == et and st is None:
            return 0.12
    return 0.0


def score_entity(query: str, name: str, entity_type: str, subtype: str | None,
                 description: str | None, importance: int | None) -> float:
    q_tokens = tokenize(query)
    name_tokens = tokenize(name)
    desc_tokens = tokenize(description or "")

    if not q_tokens:
        # Query solo de stop-words: usamos similaridad de texto plano.
        # Solo retornamos un score base; el caller puede aplicar threshold.
        return 0.0

    name_overlap = len(q_tokens & name_tokens)
    desc_overlap = len(q_tokens & desc_tokens)

    # Fraccion de palabras de la query presentes en el nombre
    name_coverage = name_overlap / len(q_tokens)

    # Penalizar si el nombre es muy corto respecto a la query
    length_penalty = min(1.0, len(name_tokens) / max(1, len(q_tokens)))

    # Boost por substring exacto
    exact_bonus = 0.0
    q_norm = normalize(query)
    n_norm = normalize(name)
    if q_norm and q_norm in n_norm:
        exact_bonus = 0.25
    if q_norm and n_norm.startswith(q_norm):
        exact_bonus = 0.35

    score = (
        name_coverage * 0.65
        + desc_overlap * 0.08
        + length_penalty * 0.05
        + exact_bonus
        + type_boost(query, entity_type, subtype)
    )

    # Ligerisimo boost por importancia del grafo
    if importance:
        score += min(importance, 100) / 1000.0

    return round(score, 4)


@router.get("/search")
async def knowledge_search(
    q: str = Query(..., min_length=2),
    min_score: float = Query(0.25, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Busqueda semantica endurecida: devuelve entidades canonicas activas
    ordenadas por relevancia. Permite ajustar el score minimo.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Recuperamos un pool amplio de candidatos con pg_trgm + ILIKE.
        # Si la query no tiene tokens utiles (solo stop-words), exigimos
        # una similaridad de pg_trgm mas alta para no inundar de resultados.
        q_tokens = tokenize(q)
        if q_tokens:
            rows = await conn.fetch(
                """
                SELECT e.id, e.name, e.entity_type, e.subtype,
                       e.description, e.importance, e.origin_url
                FROM entities e
                WHERE e.is_active = true
                  AND e.canonical_id IS NULL
                  AND (e.name % $1
                       OR e.name ILIKE '%' || $1 || '%'
                       OR e.description ILIKE '%' || $1 || '%'
                       OR e.all_names && ARRAY(SELECT unnest(string_to_array(lower($1), ' ')))
                      )
                ORDER BY GREATEST(similarity(e.name, $1),
                                  strict_word_similarity(e.name, $1)) DESC
                LIMIT 120
                """,
                q
            )
        else:
            rows = await conn.fetch(
                """
                SELECT e.id, e.name, e.entity_type, e.subtype,
                       e.description, e.importance, e.origin_url,
                       GREATEST(similarity(e.name, $1),
                                strict_word_similarity(e.name, $1)) AS pg_score
                FROM entities e
                WHERE e.is_active = true
                  AND e.canonical_id IS NULL
                  AND (e.name % $1 OR e.name ILIKE '%' || $1 || '%')
                  AND GREATEST(similarity(e.name, $1),
                               strict_word_similarity(e.name, $1)) >= 0.6
                ORDER BY pg_score DESC, e.importance DESC
                LIMIT 10
                """,
                q
            )

    scored = []
    for r in rows:
        score = score_entity(q, r["name"], r["entity_type"], r["subtype"],
                            r["description"], r["importance"])
        if score == 0 and q_tokens:
            continue
        if score >= min_score or (not q_tokens and r.get("pg_score", 0) >= 0.6):
            scored.append((score or float(r.get("pg_score", 0)), r))

    scored.sort(key=lambda x: (x[0], x[1]["importance"] or 0), reverse=True)
    top = scored[:limit]

    entity_ids = [str(r["id"]) for _, r in top]
    props = []
    if entity_ids:
        pool = await get_pool()
        async with pool.acquire() as conn:
            props = await conn.fetch(
                """
                SELECT p.entity_id, p.key, p.value, p.confidence, p.origins
                FROM active_properties p
                WHERE p.entity_id = ANY($1::uuid[])
                ORDER BY p.confidence DESC
                """,
                entity_ids
            )

    props_by_entity: dict = {}
    for p in props:
        eid = str(p["entity_id"])
        props_by_entity.setdefault(eid, []).append({
            "key": p["key"], "value": p["value"],
            "confidence": float(p["confidence"]), "origins": p["origins"],
        })

    results = []
    for score, e in top:
        eid = str(e["id"])
        row = dict(e)
        row["score"] = score
        row["properties"] = props_by_entity.get(eid, [])
        results.append(row)

    await log_query(
        query_mode="search",
        query_text=q,
        result_count=len(results),
        entity_types_returned=sorted({r["entity_type"] for r in results}),
    )

    return {"query": q, "min_score": min_score, "results": results}
