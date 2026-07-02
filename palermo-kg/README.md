# Palermo Knowledge Graph

Una base de conocimiento hiper-local sobre el barrio de Palermo, Buenos Aires.

El objetivo es simple: que un agente de IA pueda responder preguntas sobre Palermo con información real y verificada, sin inventar nada.

---

## El problema que resuelve

Cuando le preguntás a un LLM "¿qué restaurantes hay en Palermo Soho?" o "¿cuánto cuesta alquilar un dos ambientes en Palermo Hollywood?", el modelo alucina. Inventa nombres, direcciones, precios. No tiene acceso a datos actualizados y locales.

Este proyecto construye la infraestructura para que eso no pase:

1. **Scrapers** que recolectan datos reales de decenas de fuentes (Google Places, BA Data, Zonaprop, IGJ, OpenStreetMap, etc.)
2. **Una base de datos** que organiza esos datos como un grafo de entidades y relaciones
3. **Una API** que expone esos datos
4. **Un agente** que usa la API como única fuente de verdad

---

## Arquitectura

```
Fuentes de datos (71 identificadas)
    ↓ scrapers/
Base de datos (Neon PostgreSQL)
    ↓ api/
API REST (FastAPI)
    ↓
Agente IA (DeepSeek via OpenRouter)
    ↓
Respuestas verificadas sobre Palermo
```

---

## Estado actual

| Componente | Estado |
|---|---|
| Schema de base de datos | Desplegado en Neon |
| Scraper BA Data GCBA | 16.511+ propiedades (salud, educacion, transporte, espacios verdes) |
| Scraper Google Places | 219 organizaciones |
| Scraper OpenStreetMap | 5.229+ propiedades |
| Scraper Wikidata | 562 propiedades |
| Scraper IGJ | 118.595 propiedades |
| Scraper Boletin Oficial | Implementado |
| Scraper BCRA sucursales/cajeros | Reparado y funcionando |
| API FastAPI | 7 endpoints listos |
| Agente conversacional | Funciona en terminal |
| Frontend (Next.js) | Funcional en Vercel/local |

**Total: ~37.000 entidades canonicas activas en la DB**

Los scrapers inmobiliarios (`zonaprop.py`, `argenprop.py`) quedan pausados por ahora.

---

## Qué hay en la base de datos

El grafo tiene entidades de estos tipos:

| Tipo | Ejemplos |
|---|---|
| `Organization` | Restaurantes, bares, cafés, comercios, ONGs |
| `Location` | Barrios y sub-barrios de Palermo |
| `Facility` | Parques, plazas, museos, hospitales, escuelas |
| `Transport` | Estaciones de subte, paradas de colectivo, Ecobici |
| `Property` | Inmuebles en alquiler o venta |
| `LegalEntity` | Sociedades registradas en IGJ |
| `Event` | Obras de teatro, festivales, eventos culturales |
| `HistoricalRecord` | Clausuras y resoluciones del Boletín Oficial |

Cada entidad tiene:
- **Propiedades** con historial (precio, rating, horarios, teléfono, etc.)
- **Relaciones** con otras entidades (`LOCATED_IN`, `NEAR`, `OWNED_BY`, etc.)
- **Tags** (vegano, pet-friendly, con-terraza, etc.)
- **Confidence score** basado en cuántas fuentes confirman la entidad

---

## Fuentes de datos

71 fuentes identificadas en 10 categorías:

| Categoría | Fuentes |
|---|---|
| Datos oficiales CABA/Nación | BA Data GCBA, IGJ, Boletín Oficial, AGIP, AFIP, Catastro, INDEC... |
| Gastronomía / Comercio | Google Places, TripAdvisor, Guía Óleo, PedidosYa, Rappi... |
| Inmuebles | Zonaprop, Argenprop, MercadoLibre, Properati... |
| Geo / Mapa | OpenStreetMap, Wikidata, Foursquare, HERE Maps... |
| Transporte | Subte, colectivos, Ecobici, Metrobus, SUBE... |
| Cultura / Ocio | Alternativa Teatral, Eventbrite, museos, cines... |
| Salud | Min. Salud CABA, farmacias de turno, PAMI... |
| Educación | Min. Educación CABA, UBA, institutos terciarios... |
| Ambiente / Clima | SMN, APRA calidad del aire, arbolado urbano, AySA... |
| Seguridad | Mapa del Delito CABA, alertas vecinales... |

Ver el plan completo de implementación en [`PLAN.md`](PLAN.md).

---

## Cómo correr el proyecto

### Requisitos

```bash
pip install -r requirements.txt
```

Variables de entorno en `.env`:
```
DATABASE_URL=postgresql://...
GOOGLE_PLACES_API_KEY=...
OPENROUTER_API_KEY=...
```

### Correr la API

```bash
python -m uvicorn api.main:app --reload
# → http://localhost:8000
```

### Correr el agente

```bash
python -m agent.agent
```

```
============================================================
  Agente Palermo KG  ·  DeepSeek V4 Flash via OpenRouter
  Escribí tu pregunta o 'salir' para terminar
============================================================

Vos: ¿Dónde puedo comer una buena parrilla en Palermo?
Agente: Según el Knowledge Graph, las parrillas mejor valoradas en Palermo son...
```

### Correr un scraper

```bash
python -m scrapers.gcba_ba_data
python -m scrapers.google_places
```

---

## API

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado de la conexión a la DB |
| `GET /api/search?q=texto` | Búsqueda full-text endurecida en entidades |
| `GET /api/search/natural?q=texto` | Respuesta en lenguaje natural con citas reales |
| `GET /api/entity/search?name=texto` | Búsqueda por nombre (fuzzy) |
| `GET /api/entity/{uuid}` | Perfil completo de una entidad |
| `GET /api/entity/{uuid}/{key}` | Valor de una propiedad específica |
| `GET /api/query` | Query filtrada por tipo, subtipo o tag |
| `GET /api/insights/query-gaps` | Consultas sin resultados (para detectar gaps) |
| `GET /api/insights/query-summary` | Resumen de consultas recientes |

---

## Estructura del proyecto

```
palermo-kg/
├── api/                    # FastAPI — endpoints REST
│   ├── main.py
│   ├── db.py
│   ├── query_log.py
│   └── routers/
│       ├── entity.py
│       ├── insights.py
│       ├── query.py
│       ├── search.py
│       └── search_natural.py
├── agent/                  # Agente conversacional
│   └── agent.py            # DeepSeek + tools sobre la API
├── scrapers/               # Scripts de recolección de datos
│   ├── shared/
│   │   ├── db_helpers.py   # upsert_entity, upsert_property, helpers batch
│   │   └── normalizer.py   # normalize_name, normalize_value
│   ├── gcba_ba_data.py     # BA Data GCBA base
│   ├── gcba_health_education.py  # farmacias, hospitales, escuelas
│   ├── gcba_mobility.py    # subte, colectivos, Ecobici
│   ├── gcba_extended.py    # datasets extendidos GCBA
│   ├── google_places.py    # Google Places
│   ├── osm_palermo.py      # OpenStreetMap
│   ├── wikidata_ba.py      # Wikidata
│   ├── igj.py              # IGJ sociedades
│   ├── bcra_sucursales.py  # cajeros ATM
│   ├── boletin_oficial.py  # Boletín Oficial CABA
│   ├── zonaprop.py         # pausado
│   └── argenprop.py        # pausado
├── db/                     # Schema SQL modular
│   ├── RULES.md            # Reglas de consistencia — leer antes de tocar la DB
│   ├── init.sql            # Schema completo (ejecuta todos los archivos)
│   ├── 00_extensions.sql
│   ├── 01_entity_types.sql
│   └── ...
├── PLAN.md                 # Roadmap completo y lista de fuentes
├── AGENTS.md               # Instrucciones para agentes IA
└── README.md               # Este archivo
```

---

## Reglas de consistencia

Antes de modificar la base de datos o escribir un scraper, leer [`db/RULES.md`](db/RULES.md).

Las reglas más importantes:
- **Nunca hacer DELETE** — las entidades se marcan con `is_active = false`
- **Nunca sobreescribir propiedades** — se cierran con `valid_until` y se crea un registro nuevo (historial)
- **Siempre filtrar `canonical_id IS NULL`** — los duplicados tienen `canonical_id` populado
- **Nunca inventar datos** — si la DB no tiene la información, el agente lo dice explícitamente

---

## Inspiración

- [Cala.ai](https://cala.ai) — knowledge graph de ciudades
- [Diffbot](https://diffbot.com) — knowledge graph de la web
- [Wikidata](https://wikidata.org) — grafo de conocimiento libre
