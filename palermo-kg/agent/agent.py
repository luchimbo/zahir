"""
Agente IA — Palermo Knowledge Graph
Usa OpenRouter (DeepSeek V4 Flash) + herramientas propias de la API local.
"""

import os
import json
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_BASE   = "http://localhost:8000"
OR_MODEL   = "deepseek/deepseek-v4-flash"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# ── Definición de tools (formato OpenAI) ────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entity",
            "description": (
                "Busca entidades en el Knowledge Graph de Palermo por nombre usando similitud fuzzy. "
                "Úsalo cuando el usuario mencione el nombre de un lugar, local u organización. "
                "Devuelve las entidades más similares con su ID y tipo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":  {"type": "string",  "description": "Nombre a buscar (ej: 'Don Julio', 'La Cabrera')"},
                    "limit": {"type": "integer", "description": "Máximo de resultados (default 5)", "default": 5},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity",
            "description": (
                "Obtiene el perfil completo de una entidad por su UUID: dirección, teléfono, "
                "rating, horarios, precio, etc. Úsalo después de search_entity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "UUID de la entidad"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_entities",
            "description": (
                "Consulta estructurada filtrando por tipo de entidad, subtipo o tag. "
                "Útil para listar restaurantes, bares, parques, sociedades, estaciones, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string", "description": "Organization | LegalEntity | Facility | Location | Transport"},
                    "subtype":     {"type": "string", "description": "Subtipo: restaurant, bar, parque, SA, estacion_subte, etc."},
                    "tag":         {"type": "string", "description": "Tag: vegano, pet-friendly, etc."},
                    "limit":       {"type": "integer", "description": "Máximo de resultados (default 20)", "default": 20},
                    "offset":      {"type": "integer", "description": "Offset para paginación", "default": 0},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fuzzy_search",
            "description": (
                "Búsqueda de texto libre en todos los campos del Knowledge Graph. "
                "Úsalo para búsquedas abiertas cuando no sabés el tipo exacto de entidad."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto libre (ej: 'parrilla con terraza', 'plaza palermo soho')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_series",
            "description": "Busca series financieras o económicas trazables: Merval, YPFD, dólar BCRA, reservas, inflación y tasas.",
            "parameters": {"type": "object", "properties": {
                "q": {"type": "string", "description": "Nombre o tema de la serie"},
                "source": {"type": "string", "description": "Fuente opcional, por ejemplo byma_merval o ambito_merval"},
            }, "required": ["q"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_series",
            "description": "Obtiene puntos fechados de una serie y sus URLs de origen.",
            "parameters": {"type": "object", "properties": {
                "series_key": {"type": "string"}, "source": {"type": "string"},
                "from": {"type": "string", "description": "YYYY-MM-DD"},
                "to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "default": 100},
            }, "required": ["series_key"]},
        },
    },
]

# ── Ejecución de tools ───────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    try:
        with httpx.Client(timeout=10) as http:
            if name == "search_entity":
                r = http.get(f"{API_BASE}/api/entity/search", params={
                    "name": args["name"],
                    **({"limit": args["limit"]} if "limit" in args else {}),
                })
            elif name == "get_entity":
                r = http.get(f"{API_BASE}/api/entity/{args['entity_id']}")
            elif name == "query_entities":
                params = {k: v for k, v in args.items() if v is not None}
                r = http.get(f"{API_BASE}/api/query", params=params)
            elif name == "fuzzy_search":
                r = http.get(f"{API_BASE}/api/search", params={"q": args["query"]})
            elif name == "search_series":
                r = http.get(f"{API_BASE}/api/series", params={k: v for k, v in args.items() if v is not None})
            elif name == "get_series":
                series_key = args["series_key"]
                r = http.get(f"{API_BASE}/api/series/{series_key}", params={k: v for k, v in args.items() if k != "series_key" and v is not None})
            else:
                return json.dumps({"error": f"Tool desconocido: {name}"})

            r.raise_for_status()
            return json.dumps(r.json(), ensure_ascii=False, indent=2)

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ── Loop del agente ──────────────────────────────────────────────────────────

SYSTEM = (
    "Sos un asistente experto en la Ciudad Autónoma de Buenos Aires. "
    "Tenés acceso a un Knowledge Graph con datos reales de CABA: restaurantes, bares, "
    "parques, plazas, sociedades registradas en IGJ, estaciones de subte y más. "
    "Cuando el usuario pregunta algo sobre CABA o un barrio específico, usá las herramientas para consultar "
    "la base de datos y respondé con información concreta y verificada. "
    "Para datos financieros o BCRA usá search_series y get_series; siempre citá fecha y fuente del punto. "
    "Si piden correlación con alquileres y no hay serie IDECBA, decí que no hay datos suficientes. "
    "Respondé en español, de forma clara y concisa."
)


def chat(user_message: str, history: list) -> tuple[str, list]:
    history.append({"role": "user", "content": user_message})

    while True:
        response = client.chat.completions.create(
            model=OR_MODEL,
            messages=[{"role": "system", "content": SYSTEM}] + history,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        history.append(msg.model_dump(exclude_none=True))

        if response.choices[0].finish_reason == "stop":
            return msg.content or "", history

        if response.choices[0].finish_reason == "tool_calls" and msg.tool_calls:
            tool_results = []
            for call in msg.tool_calls:
                fn   = call.function.name
                args = json.loads(call.function.arguments)
                print(f"  [tool] {fn}({json.dumps(args, ensure_ascii=False)})")
                result = execute_tool(fn, args)
                tool_results.append({
                    "role":         "tool",
                    "tool_call_id": call.id,
                    "content":      result,
                })

            history.extend(tool_results)
            continue

        break

    return "No pude generar una respuesta.", history


def main():
    print("=" * 60)
    print("  Agente CABA KG  ·  DeepSeek V4 Flash via OpenRouter")
    print("  Escribí tu pregunta o 'salir' para terminar")
    print("=" * 60)
    print()

    history: list = []
    while True:
        try:
            user_input = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("salir", "exit", "quit"):
            print("Hasta luego!")
            break

        print()
        answer, history = chat(user_input, history)
        print(f"Agente: {answer}")
        print()


if __name__ == "__main__":
    main()
