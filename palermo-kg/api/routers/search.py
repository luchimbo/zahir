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
    "habilitacion": ("Organization", "comercio_habilitado"),
    "habilitaciones": ("Organization", "comercio_habilitado"),
    "comercio habilitado": ("Organization", "comercio_habilitado"),
    "deck": ("Location", "deck_gastronomico"),
    "decks": ("Location", "deck_gastronomico"),
    "gastronomico": ("Organization", "permiso_gastronomico"),
    "gastronómico": ("Organization", "permiso_gastronomico"),
    "moc": ("Location", "moc_zona_comercial"),
    "oportunidades comerciales": ("Location", "moc_zona_comercial"),
    "monumento": ("Facility", "monumento"),
    "mural": ("Facility", "mural"),
    "feria": ("Facility", "feria"),
    "calesita": ("Facility", "calesita"),
    "ruido": ("Facility", "zona_ruido"),
    "arbol": ("Facility", "arbol"),
    "árbol": ("Facility", "arbol"),
}

SEARCHABLE_PROPERTY_KEYS = {
    "address", "street", "neighborhood", "commune", "business_activity",
    "legal_name", "predominant_activity", "least_predominant_activity",
    "applicant", "sidewalk_status", "disposition", "resolution",
    "function", "subcategory", "authors", "material", "symbolizes",
    "days", "type", "species", "park_name", "classification",
    "rango", "periodo", "line", "bus_lines", "cuisine_type",
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
        if t in {"cafe", "café"}:
            tokens.extend(["cafe", "caf"])
            continue
        # Stemming muy simple para español
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
    intent_subtypes = {
        "habilitacion": "comercio_habilitado",
        "habilitaciones": "comercio_habilitado",
        "comercio habilitado": "comercio_habilitado",
        "deck": "deck_gastronomico",
        "decks": "deck_gastronomico",
        "moc": "moc_zona_comercial",
        "oportunidades comerciales": "moc_zona_comercial",
        "ruido": "zona_ruido",
        "monumento": "monumento",
        "monumentos": "monumento",
        "mural": "mural",
        "murales": "mural",
        "feria": "feria",
        "ferias": "feria",
        "calesita": "calesita",
        "calesitas": "calesita",
    }
    for keyword, intended_subtype in intent_subtypes.items():
        if keyword in q and subtype == intended_subtype:
            return 0.35
        if keyword in q and subtype != intended_subtype:
            return -0.35
    for keyword, (et, st) in TYPE_BOOST.items():
        if keyword in q and entity_type == et and (st is None or subtype == st):
            return 0.18
        if keyword in q and entity_type == et and st is None:
            return 0.12
    return 0.0


def score_entity(query: str, name: str, entity_type: str, subtype: str | None,
                 description: str | None, importance: int | None,
                 properties_text: str | None = None,
                 property_hits: int = 0) -> float:
    q_tokens = tokenize(query)
    name_tokens = tokenize(name)
    desc_tokens = tokenize(description or "")
    prop_tokens = tokenize(properties_text or "")

    if not q_tokens:
        # Query solo de stop-words: usamos similaridad de texto plano.
        # Solo retornamos un score base; el caller puede aplicar threshold.
        return 0.0

    name_overlap = len(q_tokens & name_tokens)
    desc_overlap = len(q_tokens & desc_tokens)
    prop_overlap = len(q_tokens & prop_tokens)

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
        + min(0.28, prop_overlap / len(q_tokens) * 0.22)
        + min(0.12, property_hits * 0.04)
        + length_penalty * 0.05
        + exact_bonus
        + type_boost(query, entity_type, subtype)
    )

    # Ligerisimo boost por importancia del grafo
    if importance:
        score += min(importance, 100) / 1000.0

    return round(max(0.0, min(score, 1.0)), 4)


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
            q_token_list = sorted(q_tokens)
            rows = await conn.fetch(
                """
                WITH candidates AS (
                    SELECT e.id, e.name, e.entity_type, e.subtype,
                           e.description, e.importance, e.origin_url,
                           e.lat, e.lng,
                           GREATEST(similarity(e.name, $1),
                                    strict_word_similarity(e.name, $1)) AS pg_score,
                           COALESCE((
                               SELECT COUNT(*)
                               FROM active_properties p
                               WHERE p.entity_id = e.id
                                 AND p.key = ANY($2::text[])
                                 AND (p.value ILIKE '%' || $1 || '%'
                                      OR p.key ILIKE '%' || $1 || '%'
                                      OR EXISTS (
                                          SELECT 1
                                          FROM unnest($3::text[]) AS tok
                                          WHERE p.value ILIKE '%' || tok || '%'
                                             OR p.key ILIKE '%' || tok || '%'
                                      ))
                           ), 0) AS property_hits,
                           COALESCE((
                               SELECT string_agg(p.key || ': ' || p.value, ' | ')
                               FROM active_properties p
                               WHERE p.entity_id = e.id
                                 AND p.key = ANY($2::text[])
                           ), '') AS properties_text
                    FROM entities e
                    WHERE e.is_active = true
                      AND e.canonical_id IS NULL
                      AND (e.name % $1
                           OR e.name ILIKE '%' || $1 || '%'
                           OR e.description ILIKE '%' || $1 || '%'
                           OR e.subtype ILIKE '%' || $1 || '%'
                           OR e.all_names && ARRAY(SELECT unnest(string_to_array(lower($1), ' ')))
                           OR EXISTS (
                               SELECT 1
                               FROM unnest($3::text[]) AS tok
                               WHERE e.name ILIKE '%' || tok || '%'
                                  OR e.description ILIKE '%' || tok || '%'
                                  OR e.subtype ILIKE '%' || tok || '%'
                           )
                           OR EXISTS (
                               SELECT 1
                               FROM active_properties p
                               WHERE p.entity_id = e.id
                                 AND p.key = ANY($2::text[])
                                 AND (p.value ILIKE '%' || $1 || '%'
                                      OR p.key ILIKE '%' || $1 || '%'
                                      OR EXISTS (
                                          SELECT 1
                                          FROM unnest($3::text[]) AS tok
                                          WHERE p.value ILIKE '%' || tok || '%'
                                             OR p.key ILIKE '%' || tok || '%'
                                      ))
                           )
                          )
                )
                SELECT *
                FROM candidates
                ORDER BY property_hits DESC, pg_score DESC, importance DESC
                LIMIT 240
                """,
                q, list(SEARCHABLE_PROPERTY_KEYS), q_token_list
            )
        else:
            rows = await conn.fetch(
                """
                SELECT e.id, e.name, e.entity_type, e.subtype,
                       e.description, e.importance, e.origin_url,
                       e.lat, e.lng,
                       GREATEST(similarity(e.name, $1),
                                strict_word_similarity(e.name, $1)) AS pg_score,
                       0::bigint AS property_hits,
                       ''::text AS properties_text
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
                            r["description"], r["importance"],
                            r["properties_text"], int(r["property_hits"] or 0))
        if score == 0 and q_tokens:
            continue
        pg_score = float(r["pg_score"] or 0)
        if score >= min_score or (not q_tokens and pg_score >= 0.6):
            scored.append((score or pg_score, r))

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
        row.pop("properties_text", None)
        row["property_hits"] = int(row.get("property_hits") or 0)
        row["properties"] = props_by_entity.get(eid, [])
        results.append(row)

    await log_query(
        query_mode="search",
        query_text=q,
        result_count=len(results),
        entity_types_returned=sorted({r["entity_type"] for r in results}),
    )

    return {"query": q, "min_score": min_score, "results": results}
