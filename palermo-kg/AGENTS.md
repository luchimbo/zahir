# AGENTS.md — Palermo Knowledge Graph

Instrucciones para agentes IA que operan sobre este repositorio.

---

## Qué es este proyecto

Knowledge graph hiper-local sobre Palermo, Buenos Aires. Base de datos de entidades verificadas (negocios, inmuebles, transporte, cultura, salud, educación, etc.) para que un agente IA pueda responder preguntas sobre el barrio sin alucinar.

Stack: TiDB Cloud (MySQL 8 compatible) · FastAPI · Python scrapers · Next.js

---

## Reglas absolutas

1. **Siempre leer `db/RULES.md` antes de escribir SQL o scrapers.** Las reglas de deduplicación, propiedades históricas y normalización son obligatorias.
2. **Nunca hacer DELETE.** Las entidades y propiedades se desactivan con `is_active = false` o se cierran con `valid_until`. Ver RULES.md §1 y §2.
3. **Siempre filtrar `canonical_id IS NULL`** en queries de producción. Los duplicados tienen `canonical_id` populado y no deben aparecer en resultados normales.
4. **Nunca inventar datos.** Si no hay información en la DB, responder "no tengo datos suficientes". El objetivo es precisión, no cobertura.
5. **No modificar el schema SQL** sin actualizar todos los archivos en `db/` y documentar en RULES.md.

---

## Arquitectura de scrapers

Todos los scrapers siguen este patrón:

```
scrapers/
  shared/
    db_helpers.py     # upsert_entity(), upsert_property(), upsert_relationship(), ensure_source(), mark_source_synced()
    normalizer.py     # normalize_name(), normalize_value()
    georef.py         # API georef nacional (respaldo de USIG)
    usig.py           # georreferenciación USIG CABA
  gcba_*.py           # ✅ fuentes GCBA (ba_data, mobility, environment, culture, obras...)
  google_places.py    # ✅ Google Places (requiere API key)
  osm_palermo.py      # ✅ OpenStreetMap
  wikidata_ba.py      # ✅ Wikidata
  igj.py              # ✅ IGJ
  boletin_oficial.py  # ✅ Boletín Oficial CABA
  indec_census.py     # ✅ Censo INDEC
  sinca_culture.py    # ✅ SINCA (fuente histórica)
  *_context.py        # ✅ contexto nacional agregado (CEAMSE, CEP XXI, ENACOM)
  zonaprop.py         # ⛔ pausado — no correr sin aprobación
  argenprop.py        # ⛔ pausado — no correr sin aprobación
  entity_resolver.py  # deduplicación cross-source
```

Al crear un scraper nuevo:
1. Usar `upsert_entity()` y `upsert_property()` de `db_helpers.py` — nunca INSERT directo
2. Aplicar `normalize_name()` a todos los nombres antes de insertar
3. Registrar la fuente en `db/seed/sources.sql` con `source_name` en snake_case
4. Agregar el scraper a la tabla de la Fase 1 en `PLAN.md`

---

## Fuentes de datos — 71 identificadas

Ver listado completo en `PLAN.md § Mapa completo de fuentes`.

### Prioridad de implementación

**Semana 1 — fácil, alto volumen (APIs libres / CSVs directos):**
- `osm_palermo.py` — OpenStreetMap/Overpass: miles de POIs, coords, horarios
- `wikidata_ba.py` — Wikidata SPARQL: entidades estructuradas de BA
- `gcba_extended.py` — BA Data GCBA adicional: farmacias, escuelas, arbolado, ecobici
- `colectivos_caba.py` — recorridos y paradas de colectivos
- `ecobici.py` — estaciones bici pública

**Semana 2 — scrapers web:**
- `tripadvisor.py` · `guia_oleo.py` · `alternativa_teatral.py`
- `eventbrite_ba.py` · `pedidosya.py` · `rappi_ba.py`

**Semana 3 — APIs con auth + datos complejos:**
- `afip_cuit.py` · `agip_habilitaciones.py` · `mapa_delito.py`
- `foursquare.py` · `catastro_caba.py` · `registro_propiedad.py`

**Semana 4 — enriquecimiento y señales ambientales:**
- `smn_clima.py` · `apra_aire.py` · `aysa_cortes.py`
- `arbolado_urbano.py` · `mercadolibre_inmuebles.py` · `reddit_ba.py`

---

## Tipos de entidad disponibles

Ver `db/RULES.md §3` para la lista completa. Tipos actuales:

| Tipo | Uso |
|---|---|
| `Organization` | Negocios, restaurantes, bares, comercios, ONGs |
| `Location` | Barrios, submicrobarrios, zonas |
| `Facility` | Espacios verdes, museos, centros culturales, hospitales |
| `Transport` | Estaciones de subte, paradas de colectivo, estaciones Ecobici |
| `Property` | Inmuebles en alquiler o venta |
| `LegalEntity` | Sociedades registradas en IGJ |
| `Event` | Eventos, obras de teatro, festivales |
| `Parcel` | Parcelas catastrales |
| `HistoricalRecord` | Clausuras, resoluciones del Boletín Oficial |
| `Trademark` | Marcas comerciales |
| `LegalCase` | Causas judiciales |

---

## API disponible

La API corre en `http://localhost:8000` con `python -m uvicorn api.main:app --reload`.

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado de la DB |
| `GET /api/search?q=texto` | Búsqueda full-text en entidades |
| `GET /api/search/natural?q=texto` | Respuesta natural con citas (fallback extractivo sin `OPENROUTER_API_KEY`) |
| `GET /api/entity/search?name=texto` | Búsqueda por nombre exacto |
| `GET /api/entity/{uuid}` | Detalle de entidad con propiedades activas (params: `include_history`, `source`, `historical`) |
| `GET /api/entity/{uuid}/{key}` | Valor de una propiedad específica |
| `GET /api/query` | Query tabular por filtros (tipo, subtipo, tag, `source`, `historical`) |
| `GET /api/insights/query-gaps` | Consultas sin resultados |
| `GET /api/insights/query-summary` | Resumen de uso |
| `GET /api/insights/source-health` | Frescura y cobertura por fuente |
| `GET /api/insights/data-quality` | Indicadores de calidad (duplicados, sin coords, propiedades vencidas) |

Todos los endpoints filtran `canonical_id IS NULL` automáticamente.

---

## Agente conversacional (`agent/agent.py`)

El agente responde preguntas sobre Palermo usando la API como única fuente de verdad.

**Flujo de respuesta:**
1. Recibe pregunta del usuario
2. Determina qué entidades y propiedades son relevantes
3. Consulta la API (búsqueda → detalle → propiedades)
4. Si no hay datos suficientes → responder explícitamente que no tiene datos
5. Si hay datos → responder con la información y la fuente (`source_name`)

**El agente NO debe:**
- Inventar datos sobre negocios, precios o ubicaciones
- Hacer afirmaciones sin haberlas verificado en la API
- Responder sobre zonas fuera de Palermo y sus subbarrios (Palermo Soho, Hollywood, Chico, etc.)

**El agente SÍ puede:**
- Decir "no sé" cuando la DB no tiene datos
- Sugerir fuentes externas cuando explícitamente se lo piden
- Comparar entidades usando sus propiedades (precio, rating, distancia)

---

## Retroalimentación

El `query_log` ya está implementado:
- Toda consulta se loguea con: `query_text`, `result_count`, `entity_types_returned`, `timestamp`
- Queries con `result_count = 0` → revisar en `/api/insights/query-gaps` para scraping dirigido
- Pendiente: cross-validation entre fuentes para ajustar `confidence`

---

## Variables de entorno necesarias

```
DATABASE_URL=mysql://...  # TiDB Cloud
GOOGLE_PLACES_API_KEY=...
FOURSQUARE_API_KEY=...         # (futuro)
```

Ver `.env` en la raíz del proyecto (no commitear).
