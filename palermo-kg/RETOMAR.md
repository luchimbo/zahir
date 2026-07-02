# Retomar Palermo Knowledge Graph

Estado verificado el 2026-07-02.

## Resumen

El proyecto ya tiene una base funcional:

- Schema PostgreSQL desplegado en Neon.
- API FastAPI funcionando contra la DB.
- Scrapers Python existentes para BA Data, Google Places, OSM, Wikidata, IGJ, BCRA, Zonaprop y Argenprop.
- Agente CLI en `agent/agent.py` usando OpenRouter.
- Frontend Next.js inicial en `frontend/`.
- `query_log` implementado para detectar gaps de cobertura.

La documentacion antigua habla de 458 entidades, pero el estado real actual de la DB es:

- 36.646 entidades canonicas.
- Principales fuentes con propiedades cargadas:
  - `igj`: 118.595
  - `ba_data`: 16.511
  - `osm`: 5.229
  - `google_places`: 1.662
  - `wikidata`: 562
  - `bcra`: 1.010

Nota operativa: los scrapers inmobiliarios quedan pausados por ahora:

- `zonaprop.py`
- `argenprop.py`
- `mercadolibre_inmuebles.py` cuando exista

No correr ingesta de alquileres/ventas hasta reactivar explicitamente ese frente.

Scraper nuevo implementado:

- `scrapers/gcba_health_education.py`
  - `farmacias`
  - `hospitales`
  - `centros-salud-accion-comunitaria-cesac`
  - `centros-salud-privados`
  - `establecimientos-educativos`
  - Corre solo fuentes oficiales GCBA no-inmobiliarias.
  - Filtra por `barrio` cuando existe y usa bounding box solo como fallback.
- `scrapers/gcba_mobility.py`
  - `ecobici`
  - `subte_estaciones`
  - `bocas_subte`
  - `colectivos_paradas`
  - `colectivos_recorridos`
  - Corre solo movilidad oficial GCBA no-inmobiliaria.
  - Soporta selector de dataset y offset numerico para retomar cargas largas.

## Setup local

```powershell
cd D:\Zahir\palermo-kg
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

El entorno local usa Python 3.13. Por eso `asyncpg` esta fijado en `0.30.0`; `0.29.0` intenta compilar y falla sin Microsoft C++ Build Tools.

## Verificaciones rapidas

Estado de la DB:

```powershell
.\.venv\Scripts\python scripts\db_status.py
```

Smoke test de API:

```powershell
.\.venv\Scripts\python scripts\smoke_api.py
```

Aplicar migraciones:

```powershell
.\.venv\Scripts\python scripts\migrate.py
```

Consultar gaps:

```text
GET /api/insights/query-gaps
GET /api/insights/query-summary
```

Build y smoke test del frontend:

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm install
npm run build
npm run smoke
```

Resultado esperado del frontend smoke:

```text
Smoke OK
api=ok
home_has_title=true
search_results=10
```

El smoke del frontend usa puertos aislados por defecto (`8017` API, `3017` Next) para no chocar con servidores locales ya levantados.

## Levantar en local

API:

```powershell
cd D:\Zahir\palermo-kg
.\.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```text
http://127.0.0.1:8000
```

Frontend:

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm run dev -- --hostname 127.0.0.1 --port 3001
```

```text
http://127.0.0.1:3001
```

Nota: el puerto `3000` estaba ocupado por otra app local, por eso el frontend de Palermo KG usa `3001`.

## Proximo paso recomendado

La v1 del frontend ya permite buscar entidades y consultar colecciones rapidas contra la API local. Los siguientes pasos recomendados:

1. Normalizar/limpiar `README.md`, `PLAN.md` y `plan_desarrollo.md`, porque todavia no reflejan el mismo estado.
2. Endurecer scoring de `/api/search`; hoy pg_trgm devuelve resultados flojos para consultas raras que contienen "Palermo".
3. Reparar `bcra_sucursales.py`: la URL de BA Data para cajeros devuelve 404.
4. Agregar endpoint de search con respuesta natural y citas reales.
5. Seguir con fuentes no-inmobiliarias: cultura/espacio publico, ambiente urbano y señales comerciales no-inmobiliarias.
