"""
Endpoint de busqueda natural con citas reales.
Usa el knowledge search interno para traer entidades y luego un LLM
(OpenRouter) para generar una respuesta en lenguaje natural con fuentes.
"""

import os
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from openai import AsyncOpenAI

from api.query_log import log_query
from api.routers.search import knowledge_search

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
    for prop in props:
        key = prop["key"]
        if key not in CITABLE_KEYS:
            continue
        value = prop["value"]
        lines.append(f"  - {key}: {value}")
        for origin in prop.get("origins") or []:
            if origin and origin not in citation["sources"]:
                citation["sources"].append(origin)

    if entity.get("origin_url") and entity["origin_url"] not in citation["sources"]:
        citation["sources"].append(entity["origin_url"])

    return "\n".join(lines), citation


def build_prompt(query: str, context: str) -> str:
    return f"""Sos un asistente del Palermo Knowledge Graph, una base de datos verificada sobre el barrio de Palermo, Buenos Aires.

Responde la pregunta del usuario usando UNICAMENTE los datos que te paso abajo.
Si los datos no alcanzan, responde exactamente: "No tengo datos suficientes para responder."

Reglas:
- Usa lenguaje natural y conciso.
- Cita cada dato con [N] al final de la oracion correspondiente.
- Si comparas varias entidades, indica claramente las diferencias.
- No inventes datos que no esten en el contexto.

Pregunta: {query}

Datos verificados:
{context}

Responde en espanol."""


@router.get("/search/natural")
async def knowledge_search_natural(
    q: str = Query(..., min_length=2),
    max_entities: int = Query(5, ge=1, le=10),
):
    """
    Respuesta en lenguaje natural con citas reales a entidades y fuentes.
    """
    if not LLM.api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY no configurada")

    search_result = await knowledge_search(q=q, min_score=0.25, limit=max_entities)
    entities = search_result.get("results", [])

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
            "citations": [],
            "entities_used": [],
        }

    context_blocks = []
    citations = []
    for i, entity in enumerate(entities, start=1):
        block, citation = format_entity(entity, i)
        context_blocks.append(block)
        citations.append(citation)

    context = "\n\n".join(context_blocks)
    prompt = build_prompt(q, context)

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

    return {
        "query": q,
        "answer": answer.strip(),
        "citations": citations,
        "entities_used": [{"id": e["id"], "name": e["name"], "type": e["entity_type"]} for e in entities],
    }
