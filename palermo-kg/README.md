# Palermo Knowledge Graph

Base de conocimiento hiper-local sobre Palermo, Buenos Aires.

El objetivo es que un agente de IA responda preguntas sobre Palermo con datos reales, estructurados y trazables, en vez de inventar información.

## Qué resuelve

Un LLM general puede alucinar nombres, direcciones, precios o estados legales. Este proyecto evita eso usando una fuente de verdad propia:

1. Scrapers que recolectan datos de fuentes públicas y abiertas.
2. Una base PostgreSQL modelada como grafo de entidades, propiedades y relaciones.
3. Una API REST que expone consultas naturales y estructuradas.
4. Un frontend para explorar respuestas, citas, entidades y coordenadas.
5. Un agente que debe usar el grafo como fuente principal.

## Estado actual

| Componente | Estado |
|---|---|
| Schema PostgreSQL | Desplegado en Neon |
| API FastAPI | Funcional |
| Search estructurado | Funcional |
| Search natural con citas | Funcional, con fallback local sin LLM |
| Frontend Next.js | Funcional local/Vercel |
| Query log e insights | Funcional |
| Scrapers GCBA/OSM/Wikidata/IGJ/BCRA/Google Places | Implementados |
| Scrapers nacionales/geoespaciales (INDEC, REFES, SINCA, RMBA, ENACOM...) | Implementados, refresh manual |
| Scrapers inmobiliarios | Pausados |

La referencia operativa actual verificada es de 46.711 entidades canónicas activas. Para verificar el estado real de la DB:

```powershell
.\.venv\Scripts\python scripts\db_status.py
```

## Alcance MVP v1

La v1 prioriza:

- Búsqueda natural con citas verificables.
- Consultas estructuradas por entidad, tipo, subtipo y tag.
- Transporte y movilidad.
- Cultura, espacio público, monumentos, ferias y murales.
- Ambiente urbano, ruido, arbolado y anegamientos.
- Comercio, habilitaciones, decks y permisos gastronómicos.
- Entidades legales de IGJ.
- Fuentes oficiales GCBA y fuentes abiertas ya integradas.

Queda fuera de v1:

- Scraping inmobiliario.
- Scraping agresivo de sitios comerciales.
- Automatización n8n/Railway.
- Nuevas APIs pagas.
- Cambios de schema.

## No correr sin aprobación

Estos frentes están pausados o pueden consumir cuotas/costos. No ejecutarlos sin aprobación explícita:

- `scrapers/zonaprop.py`
- `scrapers/argenprop.py`
- futuro `scrapers/mercadolibre_inmuebles.py`
- nuevas APIs pagas
- ingestas masivas sobre Neon Free

## Arquitectura

```text
Fuentes públicas y abiertas
    -> scrapers/
PostgreSQL / Neon
    -> api/ FastAPI
Frontend Next.js
    -> respuestas con citas, entidades, mapa y explicabilidad
Agente IA
    -> razona sobre datos estructurados
```

## API

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado de conexión a DB |
| `GET /api/search?q=texto` | Búsqueda estructurada con scoring |
| `GET /api/search/natural?q=texto` | Respuesta natural con citas reales |
| `GET /api/entity/search?name=texto` | Búsqueda fuzzy de entidad |
| `GET /api/entity/{uuid}` | Entidad completa (params: `include_history`, `source`, `historical`) |
| `GET /api/entity/{uuid}/{key}` | Propiedad específica |
| `GET /api/query` | Consulta tabular por filtros (incluye `source`, `historical`) |
| `GET /api/insights/query-gaps` | Consultas sin resultados |
| `GET /api/insights/query-summary` | Resumen de uso reciente |
| `GET /api/insights/source-health` | Frescura y cobertura por fuente |
| `GET /api/insights/data-quality` | Indicadores de calidad accionables |

`/api/search/natural` mantiene este contrato:

- `answer`
- `answer_markdown`
- `citations`
- `entities_used`
- `mentioned_entities`
- `explainability`

Si no hay datos suficientes, responde: `No tengo datos suficientes para responder.`

## Setup

```powershell
cd D:\Zahir\palermo-kg
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

`.env`:

```text
DATABASE_URL=postgresql://...
GOOGLE_PLACES_API_KEY=...
OPENROUTER_API_KEY=...
OR_MODEL=deepseek/deepseek-v4-flash
```

`OPENROUTER_API_KEY` es opcional para desarrollo.

## Comandos

API:

```powershell
.\.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm run dev -- --hostname 127.0.0.1 --port 3001
```

Checks:

```powershell
.\.venv\Scripts\python scripts\db_status.py
.\.venv\Scripts\python scripts\smoke_api.py
.\.venv\Scripts\python scripts\smoke_search_citations.py
```

Tests automatizados (requieren `requirements-dev.txt`; los de API leen la DB real y se saltan sin `DATABASE_URL`):

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```

Frontend build/smoke:

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm run build
npm run smoke
```

## Reglas de consistencia

Antes de modificar DB o scrapers, leer `db/RULES.md`.

Reglas principales:

- No borrar entidades; marcar `is_active = false`.
- No sobrescribir propiedades históricas; cerrar con `valid_until` y crear una nueva.
- Filtrar entidades canónicas con `canonical_id IS NULL`.
- No inventar datos; si falta información, decirlo explícitamente.

## Continuidad

Para retomar el proyecto, empezar por `RETOMAR.md`.
