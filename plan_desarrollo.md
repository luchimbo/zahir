# Plan de Desarrollo — Palermo Knowledge Graph

## Estado actual
- [x] Arquitectura definida
- [x] Modelo de datos diseñado (EAV extensible)
- [x] Fuentes de datos identificadas y clasificadas por tier
- [ ] Base de datos creada
- [ ] Datos semilla cargados
- [ ] Scrapers funcionando
- [ ] Agente IA conectado
- [ ] Interfaz de chat deployada

---

## Fase 1 — Fundación de la base de datos
**Duración estimada: 1 semana**

- [ ] Decidir plataforma: Neon (simple) vs CockroachDB (10GB gratis)
- [ ] Crear cuenta y proyecto en la plataforma elegida
- [ ] Ejecutar el schema SQL (6 tablas: entity_types, entities, properties, relationships, sources, tags)
- [ ] Crear índices
- [ ] Cargar datos semilla iniciales de Palermo:
  - [ ] Sub-barrios (Soho, Hollywood, Chico, Viejo) — fuente: Cala API output
  - [ ] Parques y plazas principales — fuente: GCBA datos abiertos
  - [ ] Líneas de transporte que pasan por Palermo — fuente: BA Data

**Verificación:** Query `SELECT * FROM entities WHERE entity_type = 'Location'` devuelve los sub-barrios de Palermo.

---

## Fase 2 — Tier 1: Ingesta desde APIs nativas
**Duración estimada: 1 semana**

- [ ] Crear cuenta en n8n cloud (app.n8n.cloud)
- [ ] Workflow 1: BA Data (GCBA) → entities/properties
  - Endpoint: data.buenosaires.gob.ar (lugares de interés, espacios verdes)
  - Cron: diario
- [ ] Workflow 2: Agenda Cultural GCBA → Event entities
  - Cron: diario
- [ ] Workflow 3: Google Places API → Organization entities (restaurantes, comercios)
  - Requiere: Google Cloud API key (gratis hasta cierto uso)
  - Cron: semanal
- [ ] Workflow 4: Ciudad 3D / WFS GCBA → Parcel entities (zonificación)
  - Cron: mensual

**Verificación:** Query de restaurantes en Palermo devuelve resultados con rating y horarios.

---

## Fase 3 — Tier 2: Scraping estructurado
**Duración estimada: 2 semanas**

- [ ] Crear cuenta en Railway (railway.app) para correr scripts Python
- [ ] Scraper Zonaprop → Property entities
  - Campos: precio, m², ambientes, zona, URL fuente
  - Cron: diario
- [ ] Scraper Argenprop → Property entities (complemento)
- [ ] Scraper IGJ → LegalEntity entities
  - Filtro: domicilios en Palermo
  - Cron: semanal
- [ ] Scraper ARBA/AGIP → Parcel entities (valuaciones fiscales)
  - Cron: mensual
- [ ] Scraper INPI → Trademark entities
  - Filtro: titulares con domicilio en Palermo
  - Cron: mensual

**Verificación:** Consulta de propiedades de alquiler en Palermo Hollywood devuelve listados con precios actualizados.

---

## Fase 4 — Agente IA
**Duración estimada: 1 semana**

- [ ] Obtener API key de Claude (console.anthropic.com)
- [ ] Escribir script Python básico que:
  1. Recibe una pregunta en lenguaje natural
  2. La convierte en query SQL (via Claude)
  3. Ejecuta la query contra la base de datos
  4. Claude genera respuesta en lenguaje natural con los datos
- [ ] Definir system prompt con el mapa completo de tablas y sus usos
- [ ] Probar preguntas cruzadas:
  - "¿Cuánto cuesta alquilar un 2 ambientes en Palermo Soho?"
  - "¿Qué restaurantes veganos hay en Palermo Hollywood con buena calificación?"
  - "¿El local en Thames 1700 está registrado en IGJ?"

**Verificación:** El agente responde con datos reales de la base, no inventados.

---

## Fase 5 — Tier 3: PDFs y documentos
**Duración estimada: 2-3 semanas**

- [ ] Pipeline Boletín Oficial CABA:
  - Script Python (Scrapy) → descarga PDF diario
  - PyPDF/OCR → extrae texto
  - Claude → identifica entidades y hechos → JSON estructurado
  - JSON → Supabase (nuevos registros en entities/properties)
  - Cron: diaria, madrugada
- [ ] Pipeline IHCBA (Instituto Histórico):
  - Crawler → extrae artículos históricos de Palermo
  - Claude → etiqueta períodos, entidades mencionadas
  - → HistoricalRecord entities
- [ ] Pipeline Poder Judicial:
  - Scraper → litigios relacionados con propiedades/comercios de Palermo
  - → LegalCase entities

**Verificación:** El agente puede responder "¿Hubo resoluciones del Boletín que afecten al área de Plaza Serrano este mes?"

---

## Fase 6 — Interfaz de chat
**Duración estimada: 1 semana**

- [ ] Crear proyecto en Vercel (vercel.com)
- [ ] Usar template de chat con Next.js + Claude API
- [ ] Conectar con el agente de Fase 4
- [ ] Deploy

**Verificación:** Se puede abrir la URL y hacerle preguntas sobre Palermo desde el navegador.

---

## Fase 7 — Tier 4: Archivos históricos (largo plazo)
**Sin fecha fija — cuando el resto esté estable**

- [ ] Scraper AGN (Archivo General de la Nación) → metadatos de fotos y documentos históricos de Palermo
- [ ] OCR de planos históricos
- [ ] Cartografía histórica de Mapotecas GCBA
- [ ] Asociar registros históricos a entidades actuales (ej: "este parque aparece en planos desde 1887")

---

## Notas técnicas

- **EAV pattern**: nunca modificar el schema para agregar variables — siempre insertar en `properties`
- **Trazabilidad**: todo dato debe tener `source_id` apuntando a su fuente
- **Extensión geográfica**: si en el futuro se expande a otros barrios, solo agregar entidades con nuevo `location_type` — la estructura escala sola
- **Cala API key**: `clsk_xBH2BSLCVxHah852uNLO3qZUALvbAzMFu7FmSQ3m62E` — REVOCAR Y REGENERAR, fue expuesta en chat

---

## Criterio de "versión 1 lista"

La v1 está lista cuando el agente puede responder correctamente estas 5 preguntas:
1. "¿Qué parques tiene Palermo?"
2. "¿Cuánto cuesta alquilar un 2 ambientes en Palermo Soho?"
3. "¿Qué restaurantes recomendás en Palermo Hollywood para ir con perro?"
4. "¿Qué eventos gratuitos hay este fin de semana?"
5. "¿Cuál es la zonificación del sector de Thames y Gorriti?"
