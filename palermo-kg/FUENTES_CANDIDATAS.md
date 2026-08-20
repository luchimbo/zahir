# Fuentes candidatas adicionales — Palermo Knowledge Graph

Listado de fuentes confiables y oficiales relacionadas con Palermo (CABA) que **no** están
implementadas ni documentadas hoy en el proyecto. Sirven como backlog para Fase 4 de `PLAN.md`.

## Criterios

- **Tier**
  - `P0`: alto valor, fuente pública/estructurada, integración simple.
  - `P1`: alto valor, requiere normalización o cruces.
  - `P2`: valor contextual, más volumen o mantenimiento.
  - `P3`: fuente frágil, scraping web, API con auth o baja trazabilidad.
- **Excluidas**: fuentes ya cubiertas por BA Data, scrapers GCBA implementados (`gcba_health_education`,
  `gcba_mobility`, `gcba_culture_public_space`, `gcba_environment`, `gcba_commercial_signals`), OSM,
  Wikidata, IGJ, INPI, Boletín Oficial, INDEC censo de población, SMN, Zonaprop/Argenprop. Ver
  `SCRAPING_RESEARCH.md` y `PLAN.md`.

## GCBA

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| IDECBA — Comunas en la web | Demografía, vivienda, educación, salud, mercado inmobiliario y obra pública de la Comuna 14 (Palermo) | JSON/Excel/CSV | P0 | Mensual |
| IDECBA — Dinámica del mercado de alquiler de departamentos | Precios y oferta de alquiler por zona (complementa BA Data sin entrar en inmobiliario por listing) | Excel/PDF | P1 | Trimestral |
| IDECBA — Anuario Estadístico y ReMeBA | Contexto demográfico y geoportal estadístico de la Región Metropolitana | CSV/GeoJSON | P1 | Anual |
| Ente de Turismo de la Ciudad (BA Turismo / Visit Buenos Aires) | Atractivos, circuitos, hotelería y estadísticas de turismo de Palermo | Web/API | P1 | Semanal |
| Puntos Verdes / Economía Circular | Puntos de reciclaje, estaciones verdes y programas ambientales del barrio | Web/GeoJSON | P1 | Semanal |
| Polideportivos / Juegos BA / clubes de barrio | Infraestructura deportiva oficial y agenda de actividades en Palermo | Web | P1 | Mensual |
| Mecenazgo GCBA | Proyectos culturales financiados con sede o alcance en Palermo | Web/CSV | P2 | Mensual |
| Presupuesto Abierto CABA | Obra pública, ejecución de gasto e inversión por Comuna 14 | CSV/API | P2 | Mensual |
| Defensoría del Pueblo CABA | Informes y denuncias con incidencia en el barrio | Web/PDF | P3 | Mensual |

## Transporte (gap: trenes)

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| Trenes Argentinos (SOFSE) — línea Mitre | Estaciones Palermo, 3 de Febrero, Lisandro de la Torre y Ministro Carranza; horarios, frecuencia y afluencia | Web/JSON | P0 | Semanal |
| SUBE — datos abiertos | Validaciones, tarifas y uso del transporte público que atraviesa Palermo | CSV | P1 | Mensual |

## Estadística

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| INDEC — Censo Nacional Económico 2021 | Estructura productiva y de empleo por zona (complementa `indec_census`, que cubre población) | CSV/XLSX | P2 | Mensual |

## Catastro e inmobiliario

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| Registro de la Propiedad Inmueble de CABA (RPI) | Titularidad y gravámenes de inmuebles del barrio | Consulta web | P2 | Trimestral |
| Banco Ciudad — indicadores inmobiliarios | Tasaciones e indicadores oficiales del mercado inmobiliario porteño | Web/PDF | P2 | Trimestral |

## Nación y judicial

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| CIJ — Centro de Información Judicial | Causas y fallos con parte en Palermo (complementa la Cámara Civil y Comercial ya integrada) | Web | P2 | Semanal |
| Ministerio Público Fiscal de la Nación | Delitos georreferenciados por barrio (complementa la estadística delictual GCBA de BA Data) | CSV/Web | P2 | Mensual |

## Patrimonio

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| Comisión Nacional de Museos y de Monumentos y Lugares Históricos | Monumentos históricos nacionales en Palermo (Bosques de Palermo, Botánico, etc.) | Web | P2 | Trimestral |
| Museos nacionales en Palermo (Museo Nacional de Arte Decorativo, etc.) | Colecciones, exposiciones y patrimonio radicado en el barrio | Web | P3 | Manual |

## Ciencia y educación

| Fuente | Qué aporta a Palermo | Formato | Tier | Frecuencia |
|---|---|---|---|---|
| UBA — Facultad de Agronomía y Veterinaria | Campus en el límite de Palermo: agenda pública, investigación y eventos | Web | P2 | Semanal |
| CONICET | Publicaciones académicas e investigaciones sobre Palermo | Web/API | P3 | Trimestral |

## Resumen priorizado

| Orden | Scraper sugerido (convención `snake_case`) | Fuente |
|---|---|---|
| 1 | `trenes_sofsa.py` | Trenes Argentinos — línea Mitre |
| 2 | `idecba_comuna.py` | IDECBA — Comunas en la web / ReMeBA |
| 3 | `gcba_ecocircular.py` | Puntos Verdes / Economía Circular |
| 4 | `gcba_deportes.py` | Polideportivos / Juegos BA / clubes de barrio |
| 5 | `gcba_turismo.py` | Ente de Turismo de la Ciudad |
| 6 | `sube_open.py` | SUBE — datos abiertos |
| 7 | `cij_causas.py` | CIJ |
| 8 | `mpf_delitos.py` | Ministerio Público Fiscal |
| 9 | `rpi_consultas.py` | Registro de la Propiedad Inmueble CABA |
| 10 | `idcba_alquileres.py` | IDECBA — Dinámica del mercado de alquiler |

Antes de implementar cualquier fuente nueva, seguir `SOURCE_OPERATIONS.md § Control previo a una fuente nueva` y `db/RULES.md`.
