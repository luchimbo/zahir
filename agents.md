# Palermo Knowledge Graph — Documentación del Proyecto

## ¿Qué es esto?

Un hub de datos estructurado sobre el barrio de Palermo (Buenos Aires), inspirado en la arquitectura de [Cala.ai](https://www.cala.ai/) y [Diffbot](https://www.diffbot.com/). La idea es tener una base de conocimiento verificada y organizada sobre la que un agente de IA pueda responder preguntas con precisión y eficiencia — sin alucinar, con datos reales y trazables.

---

## Por qué este enfoque (lecciones de Cala y Diffbot)

### De Cala.ai
Cala convierte información pública en **datos estructurados y verificados** en lugar de texto desordenado. Esto permite:

- **Menos tokens por query** — datos estructurados (JSON) son más densos que prosa, reducen costos
- **Sin alucinaciones** — el LLM recibe hechos verificados, no busca en la web
- **Trazabilidad** — cada dato sabe de dónde vino (fuente + fecha)
- **Validez explícita** — cada propiedad tiene `valid_from` / `valid_until` expuesto en la API
- **4 modos de consulta** — search / query / lookup / retrieve (ver sección API)

### De Diffbot
Diffbot construye un knowledge graph usando CV + NLP para clasificar entidades automáticamente:

- **Clasificación automática** — el tipo de entidad se detecta antes de extraer datos
- **`allNames`** — nombres alternativos para deduplicación entre fuentes
- **`importance` score** — popularidad relativa de una entidad dentro del grafo (0-100)
- **`nb_incoming_edges`** — centralidad: cuántas relaciones apuntan a esta entidad
- **`origins[]` por fact** — cada propiedad guarda las URLs que la confirman
- **`confidence`** — cuántas fuentes distintas confirman un dato

El flujo es: **datos estructurados → LLM los razona → respuesta natural al usuario**

---

## Arquitectura general

```
Fuentes públicas (GCBA, Zonaprop, Google Places, IGJ, INPI, Judicial...)
        ↓
   Scrapers automáticos (n8n + scripts Python en Railway)
        ↓
   Clasificador LLM (¿qué tipo de entidad es? → confidence score)
        ↓
   Entity Resolver (¿ya existe? → canonical_id / dedup por all_names)
        ↓
   Base de datos PostgreSQL (knowledge graph)
        ↓
   API REST (4 endpoints: search / query / lookup / retrieve)
        ↓
   Agente IA (Claude claude-sonnet-4-6)
        ↓
   Interfaz de chat (Next.js en Vercel)
```

---

## Stack tecnológico

| Pieza | Herramienta | Por qué |
|---|---|---|
| Base de datos | **Neon** o **CockroachDB** | PostgreSQL gratis — Neon: 100 proyectos × 0.5GB; CockroachDB: 10GB |
| Automatización | **n8n cloud** | No-code, visual, cron jobs |
| Scraping avanzado | **Python en Railway** | Zonaprop, IGJ, ARBA, Judicial |
| IA | **Claude API** (claude-sonnet-4-6) | Mejor razonamiento sobre datos estructurados |
| Frontend | **Vercel + Next.js** | Deploy simple, gratis |

> **Decisión pendiente:** Neon (más simple) vs CockroachDB (10GB gratis). Si el volumen de datos va a ser alto (Zonaprop histórico + Boletín Oficial + ARBA), elegir CockroachDB.

---

## Modelo de datos

### Principio de extensibilidad (patrón EAV)
- Agregar una variable nueva = 1 INSERT en `properties`. Nunca se toca el schema.
- Agregar un tipo de entidad nuevo = 1 INSERT en `entity_types`. Sin migraciones.

### Tabla: `entity_types`
```sql
id           uuid PRIMARY KEY
name         text UNIQUE NOT NULL   -- Location, Facility, Organization, Property, Event, Transport, LegalEntity...
description  text
created_at   timestamp DEFAULT now()
```

### Tabla: `entities`
```sql
id                   uuid PRIMARY KEY DEFAULT gen_random_uuid()
name                 text NOT NULL
all_names            text[]         -- nombres alternativos para dedup (Diffbot: allNames)
entity_type          text NOT NULL REFERENCES entity_types(name)
types                text[]         -- puede ser múltiples tipos a la vez ["Organization","LegalEntity"]
subtype              text           -- restaurant, park, apartment, subte, SA, SRL...
description          text
lat                  numeric(10,7)
lng                  numeric(10,7)
is_active            boolean DEFAULT true
importance           smallint       -- 0-100, popularidad relativa en el grafo (Diffbot: importance)
nb_incoming_edges    integer DEFAULT 0  -- se recalcula con job nocturno (Diffbot: nbIncomingEdges)
canonical_id         uuid           -- apunta a entidad madre si este es un duplicado
classifier_model     text           -- qué modelo clasificó esta entidad
classifier_confidence numeric(3,2)  -- confianza de la clasificación 0.00-1.00
origin_url           text           -- URL principal de origen de esta entidad
created_at           timestamp DEFAULT now()
updated_at           timestamp DEFAULT now()
```

### Tabla: `properties` (EAV — variables dinámicas)
```sql
id           uuid PRIMARY KEY DEFAULT gen_random_uuid()
entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE
key          text NOT NULL    -- price_usd, area_m2, rating, hours_open, estado_igj...
value        text NOT NULL
value_type   text NOT NULL    -- string / number / boolean / date / url
valid_from   date
valid_until  date             -- NULL = sigue vigente
confidence   numeric(3,2)    -- 0.00-1.00, aumenta con más fuentes que confirman (Diffbot: nbOrigins)
origins      text[]           -- URLs que confirman este valor (Diffbot: origins)
last_seen_at timestamp        -- última vez que una fuente confirmó este valor
source_id    uuid REFERENCES sources(id)
created_at   timestamp DEFAULT now()
```

### Tabla: `relationships`
```sql
id                uuid PRIMARY KEY DEFAULT gen_random_uuid()
from_entity_id    uuid NOT NULL REFERENCES entities(id)
relationship_type text NOT NULL  -- LOCATED_IN, NEAR, BELONGS_TO, OFFERS, CONNECTS_TO, OWNED_BY
to_entity_id      uuid NOT NULL REFERENCES entities(id)
weight            numeric
confidence        numeric(3,2)   -- confianza de esta relación
origins           text[]         -- fuentes que confirman la relación
direction         text DEFAULT 'directed'  -- directed / bidirectional
created_at        timestamp DEFAULT now()
```

### Tabla: `sources`
```sql
id           uuid PRIMARY KEY DEFAULT gen_random_uuid()
source_name  text NOT NULL    -- zonaprop, gcba, google_places, igj, inpi, boletin_oficial...
source_url   text
scraped_at   timestamp
is_reliable  boolean DEFAULT true
```

### Tabla: `tags`
```sql
id        uuid PRIMARY KEY DEFAULT gen_random_uuid()
entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE
tag       text NOT NULL    -- "pet-friendly", "sin-tacc", "vegano", "vista-al-verde"...
```

### Índices recomendados
```sql
CREATE INDEX ON entities(entity_type);
CREATE INDEX ON entities(subtype);
CREATE INDEX ON entities(canonical_id);
CREATE INDEX ON entities USING GIN(all_names);
CREATE INDEX ON entities USING GIN(types);
CREATE INDEX ON properties(entity_id, key);
CREATE INDEX ON properties(entity_id, valid_until);
CREATE INDEX ON tags(entity_id);
CREATE INDEX ON tags(tag);
CREATE INDEX ON relationships(from_entity_id);
CREATE INDEX ON relationships(to_entity_id);
```

---

## Diseño de la API (inspirado en Cala)

Cala expone 4 modos de consulta distintos. Tu API replica este patrón:

### 1. `knowledge_search` — respuesta en lenguaje natural con citas
```
GET /api/search?q=parques+gratuitos+en+palermo
→ { answer: "...", citations: [{entity_id, source_url, valid_at}] }
```
El agente llama a esto cuando el usuario hace una pregunta en lenguaje natural.

### 2. `knowledge_query` — JSON tabular estructurado
```
GET /api/query?q=restaurantes+con+rating+mayor+a+4+en+palermo+soho
→ { rows: [{id, name, rating, address, ...}], total: 12 }
```
Ideal para comparaciones, listas, rankings.

### 3. `entity_search` — buscar entidad por nombre
```
GET /api/entity/search?name=El+Desnivel
→ { entities: [{id, name, types, importance, ...}] }
```
Resuelve nombres ambiguos a entidades canónicas.

### 4. `retrieve_entity` — entidad completa por UUID
```
GET /api/entity/{uuid}
→ { id, name, types, properties: [...], relationships: [...], sources: [...] }
```
Devuelve todo lo que se sabe de una entidad, con trazabilidad completa.

### Dot-notation (inspirado en Cala)
```
GET /api/entity/{uuid}/hours/monday
GET /api/entity/{uuid}/price_usd
GET /api/entity/palermo-soho/avg_rent_usd
```
Permite al LLM pedir campos específicos sin traer toda la entidad.

---

## Tipos de entidades y variables

### Location (barrios, zonas)
`name, location_type, lat, lng, population_estimate, area_km2, avg_rent_usd, avg_sale_usd_m2, noise_level, walkability_score, green_space_score, safety_perception, main_street`

### Facility (parques, museos, plazas)
`name, facility_type, lat, lng, area_m2, is_free, admission_price_ars, hours_open, hours_close, days_open, has_parking, accessible, phone, website, instagram, rating, review_count`

### Organization (comercios, restaurantes, servicios)
`name, org_type, lat, lng, address, phone, website, instagram, hours_open, hours_close, price_range ($/$$/$$$/$$$$), cuisine_type, accepts_reservations, has_delivery, rating, review_count, is_pet_friendly, has_outdoor_seating, is_wheelchair_accessible, payment_methods`

### Property (inmuebles)
`listing_type (rental/sale), property_type, lat, lng, address_approx, zone, area_m2, covered_area_m2, rooms, bathrooms, floor, has_balcony, has_parking, has_pool, has_gym, price_usd, expenses_ars, price_per_m2_usd, furnished, pets_allowed, source_url, listed_at, last_seen_at, is_active`

### Event (eventos, ferias)
`name, event_type, lat, lng, venue_name, start_date, end_date, start_time, is_free, ticket_price_ars, ticket_url, organizer, is_recurring, recurrence, source_url`

### Transport (subte, colectivos)
`transport_type, line, stop_name, lat, lng, direction, frequency_minutes, operating_hours, accessible`

### LegalEntity (IGJ — sociedades)
`razon_social, tipo_sociedad (SA/SRL/SAS), cuit, estado (activa/disuelta/concurso), domicilio_legal, fecha_constitucion, directivos, igj_url`

### Trademark (INPI — marcas)
`marca, titular, clase_niza, estado (vigente/vencida/en_disputa), fecha_registro, vencimiento`

### LegalCase (Poder Judicial)
`caratula, tipo (quiebra/desalojo/clausura/ruidos_molestos), estado, juzgado, fecha_inicio, entidad_involucrada`

### Parcel (ARBA/AGIP — catastro)
`partida_inmobiliaria, lat, lng, superficie_terreno_m2, valuacion_fiscal_ars, deuda_impositiva, tipo_dominio, zonificacion, fot`

### HistoricalRecord (IHCBA / AGN)
`title, period, source_type (article/map/photo/manuscript), content_summary, original_url, entities_mentioned`

---

## Fuentes de datos

### Tier 1 — APIs nativas (sin scraping)
| Fuente | Qué tiene | Formato |
|---|---|---|
| BA Data (data.buenosaires.gob.ar) | Transporte, lugares de interés, espacios verdes, georreferenciación | JSON / CSV |
| Ciudad 3D / WFS-WMS GCBA | Zonificación por parcela, edificabilidad, mixtura de usos | GeoJSON / KML |

### Tier 2 — Scraping estructurado
| Fuente | Qué tiene |
|---|---|
| Zonaprop / Argenprop | Propiedades en alquiler y venta |
| Google Places API | Comercios, restaurantes, servicios, ratings |
| Agenda Cultural GCBA | Eventos, ferias, espectáculos |
| IGJ | Sociedades activas, razón social, estado legal, directivos |
| INPI | Marcas registradas, titulares, disputas de propiedad intelectual |
| ARBA / AGIP | Valuaciones fiscales, deudas, subdivisiones PH |

### Tier 3 — PDFs y documentos (extracción con LLM)
| Fuente | Qué tiene |
|---|---|
| Boletín Oficial CABA | Resoluciones, leyes, clausuras, obras aprobadas |
| Instituto Histórico CABA (IHCBA) | Historia de barrios, crónicas, cuadernos de investigación |
| Poder Judicial (Cámara Civil y Comercial) | Litigios, quiebras, disputas de alquiler, clausuras judiciales |

### Tier 4 — Imágenes y archivos históricos (largo plazo)
| Fuente | Qué tiene |
|---|---|
| Archivo General de la Nación | Planos históricos, fotos, documentos manuscritos |
| Mapotecas GCBA | Cartografía histórica de Palermo |

---

## Frecuencia de actualización

| Fuente | Frecuencia |
|---|---|
| BA Data / GCBA APIs | Diaria |
| Zonaprop / Argenprop | Diaria |
| Agenda Cultural GCBA | Diaria |
| Boletín Oficial CABA | Diaria (madrugada) |
| Google Places | Semanal |
| IGJ | Semanal |
| Poder Judicial | Semanal |
| Ciudad 3D / GeoJSON | Mensual |
| INPI | Mensual |
| ARBA / AGIP | Mensual |
| IHCBA / AGN | Manual / trimestral |

---

## API keys y credenciales

| Servicio | Estado |
|---|---|
| Cala API | ⚠️ KEY EXPUESTA EN CHAT — revocar y regenerar en dashboard de Cala antes de usar |
| Google Places | Pendiente (necesita cuenta Google Cloud) |
| n8n cloud | Pendiente (crear cuenta) |
| Neon / CockroachDB | Pendiente (decisión de plataforma) |

---

## Preguntas de ejemplo que el agente debería poder responder

- "¿Qué parques hay en Palermo y cuál tiene mejor rating?"
- "¿Cuánto cuesta alquilar un 2 ambientes en Palermo Soho?"
- "¿El restaurante X está registrado en IGJ y tiene juicios activos?"
- "¿Qué eventos gratuitos hay este fin de semana en Palermo?"
- "¿Cuál es la zonificación del lote en Thames 1500?"
- "¿Qué marcas de moda tienen sede registrada en Palermo?"
- "¿Hubo resoluciones del Boletín Oficial que afecten a Plaza Serrano este mes?"
