# Retomar Palermo Knowledge Graph

Estado consolidado: 2026-07-17.

## Estado actual

Palermo Knowledge Graph ya tiene una v1 funcional:

- Schema PostgreSQL desplegado en Neon.
- API FastAPI con endpoints de health, search, search natural, entity, query e insights (query-gaps, query-summary, source-health, data-quality).
- Frontend Next.js conectado a la API local/proxy.
- Vista de entidad con propiedades categorizadas, fuente por propiedad, historial y warnings para fuentes históricas.
- Respuestas naturales con citas reales en `/api/search/natural`.
- Fallback extractivo local cuando no hay `OPENROUTER_API_KEY`.
- Query log para detectar gaps de cobertura.
- Scrapers oficiales y semi-estructurados para GCBA, OSM, Wikidata, IGJ, BCRA, Google Places y Boletín Oficial.
- Scrapers nacionales y geoespaciales (INDEC, REFES, SINCA, transporte RMBA, ENACOM, CEAMSE, CEP XXI, educación, monumentos) con refresh manual vía `scripts/refresh_official_sources.py`.

Estado de referencia de la DB documentado en la última verificación:

- 46.711 entidades canónicas.
- Fuentes principales con propiedades cargadas:
  - `igj`
  - `ba_data`
  - `osm`
  - `google_places`
  - `wikidata`
  - `bcra`

## Alcance MVP v1

La v1 se concentra en responder con datos trazables sobre:

- Búsqueda natural con citas.
- Búsqueda estructurada de entidades.
- Transporte y movilidad.
- Cultura, espacio público, monumentos, ferias y murales.
- Ambiente urbano, arbolado, ruido y anegamientos.
- Comercio, habilitaciones, decks y permisos gastronómicos.
- Entidades legales de IGJ.
- Fuentes oficiales GCBA y fuentes abiertas ya integradas.

Fuera de v1:

- Scraping inmobiliario.
- Scraping agresivo de sitios comerciales.
- Automatización n8n/Railway.
- Nuevas APIs pagas.
- Cambios de schema.

## No correr sin aprobación

No ejecutar ni reactivar estos frentes sin aprobación explícita:

- `scrapers/zonaprop.py`
- `scrapers/argenprop.py`
- futuro `scrapers/mercadolibre_inmuebles.py`
- scrapers con costos o cuotas pagas nuevas
- ingestas masivas que puedan superar límites de Neon Free

## Setup local

```powershell
cd D:\Zahir\palermo-kg
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Variables de entorno esperadas en `.env`:

```text
DATABASE_URL=postgresql://...
GOOGLE_PLACES_API_KEY=...
OPENROUTER_API_KEY=...
OR_MODEL=deepseek/deepseek-v4-flash
```

`OPENROUTER_API_KEY` es opcional para desarrollo: sin key, `/api/search/natural` usa respuesta extractiva local.

## Comandos útiles

Estado de DB:

```powershell
.\.venv\Scripts\python scripts\db_status.py
```

Smoke API:

```powershell
.\.venv\Scripts\python scripts\smoke_api.py
```

Smoke búsqueda/citas:

```powershell
.\.venv\Scripts\python scripts\smoke_search_citations.py
```

Aplicar migraciones:

```powershell
.\.venv\Scripts\python scripts\migrate.py
```

API local:

```powershell
.\.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Frontend local:

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm run dev -- --hostname 127.0.0.1 --port 3001
```

Build y smoke frontend:

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm run build
npm run smoke
```

## Endpoints principales

- `GET /health`
- `GET /api/search?q=texto`
- `GET /api/search/natural?q=texto`
- `GET /api/entity/search?name=texto`
- `GET /api/entity/{uuid}` (params: `include_history`, `source`, `historical`)
- `GET /api/entity/{uuid}/{key}`
- `GET /api/query` (incluye filtros `source`, `historical`)
- `GET /api/insights/query-gaps`
- `GET /api/insights/query-summary`
- `GET /api/insights/source-health`
- `GET /api/insights/data-quality`

## Próximo paso recomendado

Después de esta consolidación:

1. Tests automatizados con pytest (contrato de API, ranking y búsqueda natural).
2. Revisar cobertura de gaps reales desde `/api/insights/query-gaps`.
3. Revisar calidad de datos desde `/api/insights/data-quality` y `scripts/source_audit.py`.
4. Recién después evaluar nuevas fuentes.
