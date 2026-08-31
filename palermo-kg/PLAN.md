# Plan de Desarrollo - CABA Knowledge Graph

Objetivo: construir un knowledge graph verificable y trazable de CABA, con cobertura por barrio y comuna, para que un agente de IA responda con datos reales.

## Estado consolidado

La base actual ya permite una v1 útil:

- 46.711 entidades canónicas activas según la última verificación documentada.
- Schema PostgreSQL desplegado en Neon.
- API FastAPI con search, search natural, entity, query e insights.
- Frontend Next.js conectado a la API.
- Respuestas naturales con citas reales y fallback extractivo local.
- Query log para detectar gaps.
- Scrapers oficiales y abiertos implementados.

## MVP v1

La v1 queda enfocada en estabilidad y confianza:

- Búsqueda natural con citas.
- Búsqueda estructurada por tipo, subtipo, tag y nombre.
- Entidades y propiedades con trazabilidad.
- Transporte y movilidad.
- Cultura, espacio público, monumentos, ferias y murales.
- Ambiente urbano, ruido, arbolado y anegamientos.
- Comercio, habilitaciones, decks y permisos gastronómicos.
- Entidades legales IGJ.
- Fuentes oficiales GCBA y fuentes abiertas ya integradas.

Fuera de v1:

- Inmobiliario.
- Scraping agresivo de sitios comerciales.
- Automatización n8n/Railway.
- APIs pagas nuevas.
- Cambios de schema.

## No correr sin aprobación

No ejecutar estos frentes hasta que el usuario los reactive explícitamente:

- `scrapers/zonaprop.py`
- `scrapers/argenprop.py`
- futuro `scrapers/mercadolibre_inmuebles.py`
- ingestas masivas sobre Neon Free
- APIs nuevas con costo o cuotas estrictas

## Scrapers implementados

| Scraper | Cobertura | Estado |
|---|---|---|
| `gcba_ba_data.py` | Datos base BA Data | Activo |
| `gcba_health_education.py` | Farmacias, salud, escuelas | Activo |
| `gcba_mobility.py` | Subte, colectivos, Ecobici | Activo |
| `gcba_environment.py` | Aire, ruido, anegamientos, arbolado | Activo con límites de volumen |
| `gcba_culture_public_space.py` | Cultura, ferias, monumentos, murales, calesitas | Activo |
| `gcba_commercial_signals.py` | Habilitaciones, MOC, decks, permisos gastronómicos | Activo |
| `gcba_obras.py` | Obras y señales urbanas | Implementado |
| `gcba_patrimonio.py` | Patrimonio | Implementado |
| `gcba_wifi.py` | Wifi público | Implementado |
| `gcba_delitos.py` | Seguridad/mapa del delito | Implementado |
| `google_places.py` | Organizaciones y ratings | Activo si hay API key |
| `osm_palermo.py` | POIs abiertos | Activo |
| `wikidata_ba.py` | Entidades estructuradas | Activo |
| `igj.py` | Sociedades | Activo |
| `bcra_sucursales.py` | Bancos/cajeros | Activo |
| `boletin_oficial.py` | Boletín Oficial CABA | Implementado |
| `gcba_accessibility_ramps.py` | Rampas de accesibilidad | Implementado, refresh manual |
| `gcba_civil_registry.py` | Registro civil | Implementado, refresh manual |
| `gcba_clubs.py` | Clubes | Implementado, refresh manual |
| `gcba_community_institutions.py` | Instituciones comunitarias | Implementado, refresh manual |
| `gcba_cultural_archive.py` | Archivo cultural | Implementado, refresh manual |
| `gcba_healthy_stations.py` | Estaciones saludables | Implementado, refresh manual |
| `gcba_inspections.py` | Inspecciones AGC | Implementado, refresh manual |
| `gcba_labor_integration.py` | Integración laboral | Implementado, refresh manual |
| `gcba_libraries.py` | Bibliotecas | Implementado, refresh manual |
| `gcba_nightlife_events.py` | Vida nocturna | Implementado, refresh manual |
| `gcba_places_of_worship.py` | Lugares de culto | Implementado, refresh manual |
| `gcba_police_stations.py` | Comisarías | Implementado, refresh manual |
| `gcba_urban_code.py` | Código urbanístico | Implementado, refresh manual |
| `gcba_urban_planning.py` | Planeamiento urbano | Implementado, refresh manual |
| `indec_census.py` | Censo INDEC por radio | Implementado, refresh manual |
| `national_education.py` | Padrón educativo nacional | Implementado, refresh manual |
| `national_monuments.py` | Monumentos nacionales | Desactivado (sin descarga validada) |
| `refes_historical.py` | REFES salud histórico | Implementado, solo validación histórica |
| `sinca_culture.py` | Espacios culturales SINCA | Implementado, fuente histórica |
| `transporte_rmba.py` | Red transporte RMBA | Implementado, refresh manual |
| `cep_xxi.py` / `enacom_context.py` | Contexto agregado | Implementado, refresh manual |
| `link_agc_inspections.py` | Vínculo inspecciones-entidades | Implementado |

El refresh manual de estas fuentes se orquesta con `scripts/refresh_official_sources.py` y se audita con `scripts/source_audit.py` o `GET /api/insights/source-health`.

## Roadmap recomendado

### Fase 1 - Consolidación

- Mantener documentación alineada con el estado real.
- Corregir textos rotos y normalización de consultas en español.
- Agregar smoke tests de búsqueda y citas.
- Verificar build/smoke de frontend.

### Fase 2 - Producto

- ~~Mejorar vista de entidad agrupando propiedades por fuente, fecha y confianza~~ (hecho: categorías, fuente por propiedad, warnings históricos).
- ~~Agregar navegación desde resultados hacia detalle de entidad dentro del frontend~~ (hecho).
- Mostrar historial de propiedades cuando aplique (API ya soporta `include_history`; falta UI).
- Exponer relaciones relevantes de forma legible (API ya distingue incoming/outgoing; falta pulir UI).

### Fase 3 - Calidad de datos

- Usar `/api/insights/query-gaps` para priorizar cobertura real.
- Revisar deduplicación y `all_names`.
- Recalcular importancia y centralidad.
- Mejorar confidence por confirmación cruzada de fuentes.

### Fase 4 - Nuevas fuentes

Agregar fuentes solo después de que la v1 esté estable. Priorizar fuentes oficiales o abiertas antes que scraping web frágil.

Posibles candidatos:

- Catastro/zonificación CABA.
- INPI marcas.
- Agenda cultural.
- Eventos.
- Salud privada.
- Turismo/alojamiento abierto.

## Comandos de verificación

```powershell
cd D:\Zahir\palermo-kg
.\.venv\Scripts\python scripts\db_status.py
.\.venv\Scripts\python scripts\smoke_api.py
.\.venv\Scripts\python scripts\smoke_search_citations.py
```

```powershell
cd D:\Zahir\palermo-kg\frontend
$env:npm_config_cache="D:\Zahir\palermo-kg\frontend\.npm-cache"
npm run build
npm run smoke
```
