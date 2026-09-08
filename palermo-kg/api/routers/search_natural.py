"""
Endpoint de busqueda natural con citas reales.
Usa el knowledge search interno para traer entidades y luego un LLM
(OpenRouter) para generar una respuesta en lenguaje natural con fuentes.
"""

import os
import re
import unicodedata
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from openai import AsyncOpenAI

from api.db import get_pool
from api.query_log import log_query
from api.routers.search import knowledge_search
from api.routers.observations import latest_series_points
from geography_catalog import NEIGHBORHOOD_TO_COMMUNE, normalize_geography, resolve_neighborhood

router = APIRouter(tags=["search"])

OR_MODEL = os.getenv("OR_MODEL", "deepseek/deepseek-v4-flash")
LLM = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

CITABLE_KEYS = {
    "address", "phone", "website", "instagram", "rating", "review_count",
    "hours_open", "hours_close", "price_range", "cuisine_type",
    "line", "station", "bus_lines", "route", "direction",
    "banco_nombre", "red_cajero", "atm_terminals",
    "estado", "cuit", "tipo_sociedad", "fecha_constitucion",
    "neighborhood", "commune",
    "business_activity", "legal_name", "disposition", "applicant",
    "sidewalk_status", "resolution", "start_date", "end_date",
    "predominant_activity", "least_predominant_activity",
    "floating_population_level", "living_population", "working_population",
    "households", "top_growth_activity_1", "top_growth_activity_1_growth_index",
    "street", "from_address_number", "to_address_number", "days",
    "function", "subcategory", "authors", "material", "symbolizes",
    "species", "park_name", "rango", "periodo", "dba_low", "dba_high",
    "classification",
}

PROPERTY_LABELS = {
    "address": "direccion",
    "street": "calle",
    "business_activity": "rubro",
    "legal_name": "razon social",
    "disposition": "disposicion",
    "applicant": "solicitante",
    "sidewalk_status": "estado de vereda",
    "resolution": "resolucion",
    "predominant_activity": "rubro predominante",
    "least_predominant_activity": "rubro menos predominante",
    "top_growth_activity_1": "rubro con mayor crecimiento",
    "top_growth_activity_1_growth_index": "indice de crecimiento",
    "from_address_number": "altura desde",
    "to_address_number": "altura hasta",
    "days": "dias",
    "function": "funcion",
    "subcategory": "subcategoria",
    "authors": "autores",
    "symbolizes": "representa",
    "species": "especie",
    "park_name": "espacio verde",
    "rango": "rango",
    "periodo": "periodo",
    "dba_low": "dBA minimo",
    "dba_high": "dBA maximo",
    "classification": "clasificacion",
}


FINANCE_ALIASES = (
    (("merval",), "byma_merval_close"),
    (("ypf", "ypfd"), "byma_ypfd_close"),
    (("reserva",), "bcra_var_1"),
    (("inflacion mensual",), "bcra_var_27"),
    (("inflacion",), "bcra_var_28"),
    (("dolar", "tipo de cambio"), "bcra_fx_usd"),
    (("uva",), "bcra_var_1240"),
    (("tasa",), "bcra_var_160"),
)


def finance_series_key(query: str) -> str | None:
    normalized = normalize_query(query)
    for aliases, series_key in FINANCE_ALIASES:
        if any(alias in normalized for alias in aliases):
            return series_key
    return None


async def build_finance_payload(query: str) -> dict | None:
    normalized = normalize_query(query)
    if "alquiler" in normalized and any(term in normalized for term in ("merval", "ypf", "dolar", "tasa")):
        return {
            "query": query,
            "answer": "No tengo datos suficientes para correlacionar la serie financiera con alquileres: IDECBA alquileres todavía no fue integrado.",
            "answer_markdown": "No tengo datos suficientes para correlacionar la serie financiera con alquileres: IDECBA alquileres todavía no fue integrado.",
            "citations": [], "entities_used": [], "mentioned_entities": [], "explainability": [],
        }
    series_key = finance_series_key(query)
    if not series_key:
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        points = await latest_series_points(conn, series_key, limit=500)
    if not points:
        return None
    recent = points[-5:]
    latest = recent[-1]
    unit = latest.get("unit") or "sin unidad"
    lines = [f"## {latest['entity_name']}", "",
             f"Último dato disponible: **{latest.get('value', latest.get('value_text'))} {unit}** el {latest['observed_at']} (fuente: {latest['source_name']}). [1]",
             "", "Últimos puntos verificados:", ""]
    lines.extend(f"- {row['observed_at']}: {row.get('value', row.get('value_text'))} {row.get('unit') or ''}" for row in recent)
    citation = {"entity_id": latest["entity_id"], "entity_name": latest["entity_name"],
                "sources": [{"url": url, "valid_at": str(row["observed_at"])} for row in recent
                            for url in (row.get("origins") or [])][:5]}
    return {"query": query, "answer": "\n".join(lines), "answer_markdown": "\n".join(lines),
            "citations": [citation],
            "entities_used": [{"id": latest["entity_id"], "name": latest["entity_name"], "type": latest["entity_type"]}],
            "mentioned_entities": [{"id": latest["entity_id"], "name": latest["entity_name"], "type": latest["entity_type"],
                                    "subtype": None, "lat": None, "lng": None, "source_count": len(citation["sources"])}],
            "explainability": [{"index": 1, "text": f"Serie {series_key}; última revisión del período {latest['observed_period']}.",
                                  "entity_id": latest["entity_id"], "entity_name": latest["entity_name"], "lat": None, "lng": None,
                                  "sources": citation["sources"]}]}


def normalize_query(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9\s]", " ", normalized)


def is_restaurant_zone_count_query(query: str) -> bool:
    q = normalize_query(query)
    asks_zone = any(word in q.split() for word in ("zona", "zonas", "area", "areas"))
    asks_count = any(phrase in q for phrase in (
        "mayor cantidad",
        "mas cantidad",
        "mas restaurantes",
        "mayor concentracion",
        "donde hay mas",
        "con mas",
    ))
    return asks_zone and asks_count and "restaurant" in q


def inferred_neighborhood(query: str) -> str | None:
    normalized = f" {normalize_geography(query)} "
    candidates = sorted(NEIGHBORHOOD_TO_COMMUNE, key=len, reverse=True)
    for candidate in candidates:
        if f" {normalize_geography(candidate)} " in normalized:
            return candidate
    # Includes Palermo Soho/Hollywood aliases without treating them as official
    # administrative units.
    return resolve_neighborhood(query)


def host_from_url(url: str) -> str:
    match = re.match(r"^https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else "fuente"


async def build_restaurant_zone_count_payload(query: str, neighborhood: str | None = None,
                                              commune: int | None = None) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # This aggregation deliberately follows persisted official geography,
        # not approximate Palermo boxes.
        sql = """SELECT place.id, place.name, place.lat, place.lng, COUNT(DISTINCT e.id) total,
            GROUP_CONCAT(DISTINCT e.origin_url SEPARATOR '|') origins
            FROM entities e JOIN relationships r ON r.from_entity_id=e.id AND r.relationship_type='LOCATED_IN'
            JOIN entities place ON place.id=r.to_entity_id AND place.entity_type='Location'
            LEFT JOIN relationships h ON h.from_entity_id=place.id AND h.relationship_type='PART_OF'
            WHERE e.entity_type='Organization' AND e.subtype='restaurant' AND e.is_active=TRUE
              AND e.canonical_id IS NULL AND place.name NOT LIKE 'Comuna %'
              AND place.name <> 'Ciudad Autónoma de Buenos Aires'"""
        params = []
        if neighborhood:
            params.append(neighborhood); sql += f" AND place.name=${len(params)}"
        elif commune:
            params.append(f"Comuna {commune}"); sql += f" AND h.to_entity_id=(SELECT id FROM entities WHERE name=${len(params)} AND entity_type='Location' LIMIT 1)"
        rows = await conn.fetch(sql + " GROUP BY place.id, place.name, place.lat, place.lng ORDER BY total DESC LIMIT 5", *params)
    if not rows:
        return None
    valid_at = date.today().isoformat()
    top_zones = [dict(row) for row in rows]
    lines = [
        f"## Barrios con mayor cantidad de restaurantes{' en ' + neighborhood if neighborhood else ' en CABA'}",
        "",
        "El ranking usa las relaciones territoriales oficiales disponibles en el grafo.",
        "",
    ]
    citations = []
    mentioned_entities = []
    explainability = []

    for index, zone in enumerate(top_zones, start=1):
        lat = float(zone["lat"]) if zone.get("lat") is not None else None
        lng = float(zone["lng"]) if zone.get("lng") is not None else None
        source_urls = [url for url in str(zone.get("origins") or "").split("|") if url][:5]
        source_refs = [{"url": url, "valid_at": valid_at} for url in source_urls]
        lines.append(
            f"- **{zone['name']}**: {zone['total']} restaurantes registrados. [{index}]"
        )
        citations.append({
            "entity_id": zone["id"],
            "entity_name": zone["name"],
            "sources": source_refs,
        })
        mentioned_entities.append({
            "id": zone["id"],
            "name": zone["name"],
            "type": "Location",
            "subtype": "neighborhood",
            "lat": lat,
            "lng": lng,
            "source_count": len(source_urls),
        })
        explainability.append({
            "index": index,
            "text": (
                f"{zone['name']} aparece en el ranking porque concentra "
                f"{zone['total']} restaurantes vinculados al barrio oficial."
            ),
            "entity_id": zone["id"],
            "entity_name": zone["name"],
            "lat": lat,
            "lng": lng,
            "sources": source_refs,
        })

    await log_query(
        query_mode="search_natural",
        query_text=query,
        result_count=sum(int(zone["total"]) for zone in top_zones),
        entity_types_returned=["Location", "Organization"],
    )

    return {
        "query": query,
        "answer": "\n".join(lines),
        "answer_markdown": "\n".join(lines),
        "citations": citations,
        "entities_used": [
            {"id": zone["id"], "name": zone["name"], "type": "Location"}
            for zone in top_zones
        ],
        "mentioned_entities": mentioned_entities,
        "explainability": explainability,
    }


def format_entity(entity: dict, index: int) -> tuple[str, dict]:
    """Devuelve el bloque de contexto y el mapeo de cita para una entidad."""
    lines = [
        f"[{index}] {entity['name']} ({entity['entity_type']}" +
        (f" / {entity['subtype']}" if entity.get("subtype") else "") + ")"
    ]
    citation = {
        "entity_id": entity["id"],
        "entity_name": entity["name"],
        "sources": [],
    }

    props = entity.get("properties", []) or []
    if entity.get("lat") is not None and entity.get("lng") is not None:
        lines.append(f"  - coordenadas: {entity['lat']}, {entity['lng']}")
    for prop in props:
        key = prop["key"]
        if key not in CITABLE_KEYS:
            continue
        value = prop["value"]
        label = PROPERTY_LABELS.get(key, key)
        lines.append(f"  - {label}: {value}")
        for origin in prop.get("origins") or []:
            if origin and origin not in citation["sources"]:
                citation["sources"].append(origin)

    if entity.get("origin_url") and entity["origin_url"] not in citation["sources"]:
        citation["sources"].append(entity["origin_url"])

    return "\n".join(lines), citation


def prop_map(entity: dict) -> dict[str, str]:
    return {
        prop["key"]: prop["value"]
        for prop in entity.get("properties", []) or []
        if prop.get("key") and prop.get("value") is not None
    }


def is_noise_query(query: str, entities: list[dict]) -> bool:
    q = query.lower()
    return "ruido" in q and any(entity.get("subtype") == "zona_ruido" for entity in entities)


def noise_high(entity: dict) -> float:
    props = prop_map(entity)
    try:
        return float(props.get("dba_high") or props.get("dba_low") or 0)
    except ValueError:
        return 0


def build_noise_answer(query: str, entities: list[dict]) -> str:
    noise_entities = [entity for entity in entities if entity.get("subtype") == "zona_ruido"]
    if not noise_entities:
        return ""

    ranked = sorted(noise_entities, key=noise_high, reverse=True)
    lines = [
        f"## Zonas de ruido nocturno",
        "",
        "Los rangos más altos detectados en el grafo son:",
        "",
    ]
    for index, entity in enumerate(ranked[:5], start=1):
        props = prop_map(entity)
        coords = ""
        if entity.get("lat") is not None and entity.get("lng") is not None:
            coords = f" Centroide aproximado: {entity['lat']}, {entity['lng']}."
        lines.append(
            f"- **{entity['name']}**: {props.get('rango') or 'rango no informado'}"
            f" ({props.get('dba_low', '?')}-{props.get('dba_high', '?')} dBA).{coords} [{index}]"
        )
    lines.append("")
    lines.append("La fuente modela estas zonas como polígonos/centroides de Comuna 14, no como direcciones postales exactas.")
    return "\n".join(lines)


def build_extractive_answer(query: str, entities: list[dict]) -> str:
    """Respuesta local cuando no hay LLM configurado."""
    if not entities:
        return "No tengo datos suficientes para responder."
    if is_noise_query(query, entities):
        noise_answer = build_noise_answer(query, entities)
        if noise_answer:
            return noise_answer

    lines = [
        f"## Respuesta sobre {query}",
        "",
        f"Encontré {len(entities)} resultados relevantes en el grafo de CABA:",
        "",
    ]
    for index, entity in enumerate(entities, start=1):
        details = []
        if entity.get("lat") is not None and entity.get("lng") is not None:
            details.append(f"coordenadas: {entity['lat']}, {entity['lng']}")
        for prop in entity.get("properties", []) or []:
            key = prop["key"]
            if key not in CITABLE_KEYS:
                continue
            label = PROPERTY_LABELS.get(key, key)
            details.append(f"{label}: {prop['value']}")
            if len(details) >= 4:
                break
        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- **{entity['name']}**{suffix}. [{index}]")
    return "\n".join(lines)


def source_count(citation: dict) -> int:
    return len(citation.get("sources") or [])


def build_mentioned_entities(entities: list[dict], citations: list[dict]) -> list[dict]:
    citations_by_id = {c["entity_id"]: c for c in citations}
    mentioned = []
    seen = set()
    for entity in entities:
        dedupe_key = (entity["name"], entity["entity_type"], entity.get("subtype"))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        citation = citations_by_id.get(entity["id"], {})
        mentioned.append({
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["entity_type"],
            "subtype": entity.get("subtype"),
            "lat": float(entity["lat"]) if entity.get("lat") is not None else None,
            "lng": float(entity["lng"]) if entity.get("lng") is not None else None,
            "source_count": source_count(citation),
        })
    return mentioned


def build_explainability(entities: list[dict], citations: list[dict]) -> list[dict]:
    citations_by_id = {c["entity_id"]: c for c in citations}
    rows = []
    for index, entity in enumerate(entities[:5], start=1):
        useful_props = []
        if entity.get("lat") is not None and entity.get("lng") is not None:
            useful_props.append(f"coordenadas: {entity['lat']}, {entity['lng']}")
        for prop in entity.get("properties", []) or []:
            if prop["key"] in CITABLE_KEYS:
                label = PROPERTY_LABELS.get(prop["key"], prop["key"])
                useful_props.append(f"{label}: {prop['value']}")
            if len(useful_props) >= 3:
                break
        if useful_props:
            text = f"{entity['name']} se incluyó por estos datos verificados: {', '.join(useful_props)}."
        else:
            text = f"El resultado {entity['name']} se incluyó por coincidencia de entidad y relevancia dentro del grafo."
        rows.append({
            "index": index,
            "text": text,
            "entity_id": entity["id"],
            "entity_name": entity["name"],
            "lat": float(entity["lat"]) if entity.get("lat") is not None else None,
            "lng": float(entity["lng"]) if entity.get("lng") is not None else None,
            "sources": citations_by_id.get(entity["id"], {}).get("sources", []),
        })
    return rows


def build_prompt(query: str, context: str) -> str:
    return f"""Sos un asistente del CABA Knowledge Graph, una base de datos verificada sobre la Ciudad Autónoma de Buenos Aires.

Responde la pregunta del usuario usando UNICAMENTE los datos que te paso abajo.
Si los datos no alcanzan, responde exactamente: "No tengo datos suficientes para responder."

Reglas:
- Usa lenguaje natural y conciso.
- Cita cada dato con [N] al final de la oración correspondiente.
- Si comparas varias entidades, indica claramente las diferencias.
- No inventes datos que no estén en el contexto.

Pregunta: {query}

Datos verificados:
{context}

Responde en español."""


@router.get("/search/natural")
async def knowledge_search_natural(
    q: str = Query(..., min_length=2),
    max_entities: int = Query(5, ge=1, le=10),
    neighborhood: str | None = None,
    commune: int | None = Query(None, ge=1, le=15),
):
    """
    Respuesta en lenguaje natural con citas reales a entidades y fuentes.
    """
    inferred = neighborhood or inferred_neighborhood(q)
    finance_payload = await build_finance_payload(q)
    if finance_payload:
        await log_query(query_mode="search_natural", query_text=q,
                        result_count=len(finance_payload["entities_used"]),
                        entity_types_returned=[item["type"] for item in finance_payload["entities_used"]])
        return finance_payload
    if is_restaurant_zone_count_query(q):
        aggregate_payload = await build_restaurant_zone_count_payload(q, inferred, commune)
        if aggregate_payload:
            return aggregate_payload

    search_result = await knowledge_search(q=q, min_score=0.25, limit=max_entities,
                                           neighborhood=inferred, commune=commune)
    entities = search_result.get("results", [])
    if is_noise_query(q, entities):
        entities = sorted(entities, key=noise_high, reverse=True)

    if not entities:
        await log_query(
            query_mode="search_natural",
            query_text=q,
            result_count=0,
            entity_types_returned=[],
        )
        return {
            "query": q,
            "answer": "No tengo datos suficientes para responder.",
            "answer_markdown": "No tengo datos suficientes para responder.",
            "citations": [],
            "entities_used": [],
            "mentioned_entities": [],
            "explainability": [],
        }

    context_blocks = []
    citations = []
    for i, entity in enumerate(entities, start=1):
        block, citation = format_entity(entity, i)
        context_blocks.append(block)
        citations.append(citation)

    context = "\n\n".join(context_blocks)
    prompt = build_prompt(q, context)

    if LLM.api_key:
        try:
            completion = await LLM.chat.completions.create(
                model=OR_MODEL,
                messages=[
                    {"role": "system", "content": "Sos un asistente factual y conciso."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=600,
            )
            answer = completion.choices[0].message.content or ""
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Error del LLM: {exc}")
    else:
        answer = build_extractive_answer(q, entities)

    if is_noise_query(q, entities):
        noise_answer = build_noise_answer(q, entities)
        if noise_answer:
            answer = noise_answer
    elif entities and "No tengo datos suficientes para responder" in answer:
        answer = build_extractive_answer(q, entities)

    await log_query(
        query_mode="search_natural",
        query_text=q,
        result_count=len(entities),
        entity_types_returned=sorted({e["entity_type"] for e in entities}),
    )

    # Normalizar citas: cada source queda con valid_at = hoy si no hay otra info
    valid_at = date.today().isoformat()
    for c in citations:
        c["sources"] = [
            {"url": url, "valid_at": valid_at} for url in c["sources"]
        ]

    mentioned_entities = build_mentioned_entities(entities, citations)
    explainability = build_explainability(entities, citations)

    return {
        "query": q,
        "answer": answer.strip(),
        "answer_markdown": answer.strip(),
        "citations": citations,
        "entities_used": [{"id": e["id"], "name": e["name"], "type": e["entity_type"]} for e in entities],
        "mentioned_entities": mentioned_entities,
        "explainability": explainability,
    }
