# Plan de Desarrollo — Palermo Knowledge Graph

Objetivo: knowledge graph hiper-local sobre Palermo, Buenos Aires.  
Inspirado en Cala.ai y Diffbot. Base de conocimiento verificable para que un agente IA responda sin alucinar.

---

## Estado actual

- **~37.000 entidades canonicas activas** en Neon PostgreSQL
- **Scrapers listos:** `gcba_ba_data.py`, `google_places.py`, `osm_palermo.py`, `wikidata_ba.py`, `igj.py`, `boletin_oficial.py`, `bcra_sucursales.py`, `gcba_health_education.py`, `gcba_mobility.py`, `gcba_extended.py`
- **Scrapers pausados:** `zonaprop.py`, `argenprop.py` (no correr ingesta inmobiliaria hasta reactivar explicitamente)
- **API FastAPI** con endpoints de busqueda, entidades, query e insights
- **Frontend** funcional en Next.js (local/Vercel)

---

## Fase 1 — Scrapers y datasets (EN PROGRESO)

### 1.1 Scrapers completados
| Scraper | Fuente | Entidades / propiedades | Frecuencia |
|---|---|---|---|
| `gcba_ba_data.py` | BA Data GCBA | barrios, subte, parques, comunas | Mensual |
| `gcba_health_education.py` | BA Data GCBA | farmacias, hospitales, CESAC, salud privada, escuelas | Mensual |
| `gcba_mobility.py` | BA Data GCBA | subte, bocas, colectivos, Ecobici | Mensual |
| `gcba_extended.py` | BA Data GCBA | bibliotecas, datasets adicionales | Mensual |
| `google_places.py` | Google Places API | 219 organizaciones | Semanal |
| `osm_palermo.py` | OpenStreetMap / Overpass | miles de POIs | Mensual |
| `wikidata_ba.py` | Wikidata SPARQL | museos, hospitales, monumentos | Mensual |
| `igj.py` | IGJ / datos.jus.gob.ar | 30.000+ sociedades | Semanal |
| `boletin_oficial.py` | Boletin Oficial CABA | clausuras, habilitaciones | Diaria |
| `bcra_sucursales.py` | BCRA / BA Data GCBA | cajeros ATM (365 en Palermo) | Mensual |

### 1.2 Scrapers pausados
| Scraper | Fuente | Motivo |
|---|---|---|
| `zonaprop.py` | Zonaprop | Datos inmobiliarios pausados |
| `argenprop.py` | Argenprop | Datos inmobiliarios pausados |

### 1.3 Scrapers nuevos — Semana 1 (fácil, alto volumen) 🔵
| Scraper | Fuente | Descripción | Auth | Estado |
|---|---|---|---|---|
| `osm_palermo.py` | OpenStreetMap / Overpass API | Miles de POIs con coords, categorías, horarios | Libre | ✅ |
| `wikidata_ba.py` | Wikidata SPARQL | Entidades estructuradas: hospitales, museos, monumentos | Libre | ✅ |
| `gcba_extended.py` | BA Data GCBA (datasets adicionales) | Farmacias, escuelas, centros de salud, bibliotecas | Libre | ✅ |
| `gcba_health_education.py` | BA Data GCBA | Farmacias, hospitales, CESAC, salud privada, escuelas | Libre | ✅ |
| `gcba_mobility.py` | BA Data GCBA | Subte, bocas, colectivos, Ecobici | Libre | ✅ |
| `colectivos_caba.py` | BA Data GCBA | Recorridos y paradas de colectivos | Libre | ✅ (dentro de gcba_mobility.py) |
| `ecobici.py` | BA Data / API Ecobici | Estaciones bici pública, disponibilidad | Libre | ✅ (dentro de gcba_mobility.py) |

### 1.4 Scrapers nuevos — Semana 2 (scrapers web) 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `tripadvisor.py` | TripAdvisor | Restaurantes, hoteles, atracciones con reviews | HTML scraping |
| `guia_oleo.py` | Guía Óleo | Restaurantes AR con menús y precios | HTML scraping |
| `alternativa_teatral.py` | Alternativa Teatral | Obras de teatro, venues, compañías | HTML scraping |
| `eventbrite_ba.py` | Eventbrite | Eventos en Palermo | API pública |
| `pedidosya.py` | PedidosYa | Restaurantes con menús actualizados | HTML scraping |
| `rappi_ba.py` | Rappi | Comercios y restaurantes | HTML scraping |

### 1.5 Scrapers nuevos — Semana 3 (APIs + datos complejos) 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `afip_cuit.py` | AFIP | Lookup de CUIT para entidades legales | Libre |
| `agip_habilitaciones.py` | AGIP CABA | Habilitaciones comerciales vigentes | Libre |
| `mapa_delito.py` | Mapa del Delito CABA | Incidentes por zona | BA Data |
| `foursquare.py` | Foursquare Places | POIs con categorías y popularidad | API key |
| `catastro_caba.py` | Catastro CABA | Parcelas, superficies, propietarios | BA Data |
| `registro_propiedad.py` | Registro Prop. Inmueble | Titularidad de inmuebles | Web scraping |

### 1.6 Scrapers nuevos — Semana 4 (enriquecimiento y señales) 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `smn_clima.py` | SMN | Datos climáticos históricos y actuales | Libre |
| `apra_aire.py` | APRA CABA | Calidad del aire por zona | BA Data |
| `aysa_cortes.py` | AySA | Cortes de agua programados | Web scraping |
| `arbolado_urbano.py` | GCBA | Árbol por árbol, especie, estado | BA Data |
| `mercadolibre_inmuebles.py` | MercadoLibre | Inmuebles en Palermo | HTML scraping |
| `reddit_ba.py` | Reddit r/buenosaires | Menciones y discusiones sobre Palermo | API pública |

---

### 1.7 Scrapers nuevos — Gobierno extra 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `gcba_obras.py` | BA Data GCBA | Obras en curso, calles cortadas, permisos activos | Libre |
| `gcba_baches.py` | BA Data GCBA | Baches reportados por zona | Libre |
| `gcba_luminarias.py` | BA Data GCBA | Estado del alumbrado público | Libre |
| `gcba_wifi.py` | BA Data GCBA | Puntos de wifi público en Palermo | Libre |
| `gcba_patrimonio.py` | BA Data GCBA | Edificios patrimoniales catalogados | Libre |
| `gcba_monumentos.py` | BA Data GCBA / MHN | Monumentos históricos nacionales | Libre |
| `gcba_presupuesto.py` | BA Data GCBA | Proyectos de presupuesto participativo | Libre |
| `gcba_juntas.py` | BA Data GCBA | Centros de Gestión y Participación (CGP) | Libre |
| `enacom_antenas.py` | ENACOM | Antenas de telefonía por zona | Libre |
| `gcba_permisos_obra.py` | BA Data GCBA | Permisos de construcción activos | Libre |

### 1.8 Scrapers nuevos — Banca / Fintech 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `bcra_sucursales.py` | BCRA | Sucursales bancarias y cajeros ATM (CSV público) | Libre |
| `rapipago.py` | Rapipago / Pagofácil | Puntos de pago en Palermo | Libre |
| `cnv_sociedades.py` | CNV | Sociedades cotizantes en bolsa | Libre |
| `inpi_marcas.py` | INPI | Marcas y patentes registradas (cruzar con IGJ) | Libre |

### 1.9 Scrapers nuevos — Salud privada 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `doctoralia.py` | Doctoralia | Médicos en Palermo con especialidad y cobertura | HTML scraping |
| `osde.py` | OSDE | Centros médicos y prestadores en Palermo | HTML scraping |
| `swiss_medical.py` | Swiss Medical | Centros y prestadores | HTML scraping |
| `pami_prestadores.py` | PAMI | Prestadores PAMI en Palermo | Libre |

### 1.10 Scrapers nuevos — Turismo / Alojamiento 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `booking.py` | Booking.com | Hoteles y apart-hoteles en Palermo | API key |
| `airbnb.py` | Inside Airbnb | Dataset histórico de alojamientos CABA (gratis) | Libre |
| `hostelworld.py` | Hostelworld | Hostels con precios y reviews | API key |
| `timeout_ba.py` | Timeout Buenos Aires | Recomendaciones editoriales de lugares | HTML scraping |

### 1.11 Scrapers nuevos — Deportes / Bienestar 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `wellhub.py` | Wellhub/Gympass | Gimnasios y estudios adheridos en Palermo | API key |
| `gcba_clubes.py` | BA Data GCBA | Clubes deportivos y polideportivos | Libre |
| `gcba_canchas.py` | BA Data GCBA | Canchas de tenis municipales | Libre |
| `gcba_piletas.py` | BA Data GCBA | Piletas municipales | Libre |

### 1.12 Scrapers nuevos — Startups / Empresas tech 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `crunchbase.py` | Crunchbase | Startups con sede en Palermo, inversiones | API key |
| `clutch_ba.py` | Clutch.co | Agencias y empresas tech en BA | HTML scraping |

### 1.13 Scrapers nuevos — Historia / Patrimonio 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `gcba_calles.py` | BA Data GCBA | Calles con nombre histórico y origen | Libre |
| `gcba_archivo.py` | Archivo GCBA | Fotos históricas de Palermo | Libre |
| `biblioteca_nacional.py` | Biblioteca Nacional | Catálogo de publicaciones sobre BA/Palermo | API |

### 1.14 Scrapers nuevos — Señales digitales 🔵
| Scraper | Fuente | Descripción | Auth |
|---|---|---|---|
| `youtube_ba.py` | YouTube Data API | Reviews y vlogs de lugares en Palermo | API key |
| `google_trends.py` | Google Trends | Términos más buscados sobre Palermo | Libre |

---

## Mapa completo de fuentes (123 identificadas)

### Datos Oficiales CABA/Nación (24)
- BA Data GCBA ✅ · IGJ ⏳ · Boletín Oficial CABA ⏳
- Catastro CABA · Registro de la Propiedad · AGIP habilitaciones
- INDEC censos · AFIP CUIT lookup · ANMAT habilitaciones salud
- Min. Educación CABA · Min. Salud CABA · SECHI eventos
- datos.gob.ar (nacional) · ACUMAR medio ambiente
- Obras en curso GCBA · Baches reportados · Luminarias
- Wifi público GCBA · Patrimonio histórico · Monumentos MHN
- Presupuesto participativo · Juntas CGP · ENACOM antenas
- Permisos de obra · Calles históricas · Archivo GCBA

### Banca / Fintech (7)
- BCRA sucursales bancarias · Red Link cajeros · Banelco cajeros
- Rapipago/Pagofácil puntos · CNV sociedades · INPI marcas
- Casas de cambio CABA

### Inmuebles (8)
- Zonaprop ⏳ · Argenprop · MercadoLibre Inmuebles
- Properati · RE/MAX AR · Reporte Inmobiliario $/m²
- OLX · Inside Airbnb (dataset gratis)

### Gastronomía / Comercio (9)
- Google Places ✅ · TripAdvisor · Guía Óleo
- PedidosYa · Rappi · TheFork/ElTenedor
- OpenTable AR · Mercado Pago comercios · Yelp

### Geo / Mapa (7)
- OpenStreetMap/Overpass · Wikidata · Wikipedia artículos BA
- Foursquare Places · HERE Maps POIs · Mapillary · Nominatim

### Transporte (6)
- Subte GCBA ✅ · Colectivos CABA · Ecobici
- Metrobus paradas · SUBE flujos · Estacionamiento medido

### Cultura / Ocio (7)
- Alternativa Teatral · BA Ciudad agenda cultural
- Entradas.com/Passline · Cines · Museos CABA
- Festivales recurrentes · Eventbrite BA

### Salud — pública (5)
- Farmacias de turno CABA · Hospitales Min. Salud
- PAMI sucursales · Clínicas privadas · Turnos médicos

### Salud — privada (4)
- Doctoralia · OSDE · Swiss Medical · PAMI prestadores

### Turismo / Alojamiento (7)
- Booking.com · Inside Airbnb · Hostelworld
- Timeout Buenos Aires · Lonely Planet · Culture Trip · Tur.bus

### Educación (9)
- Min. Educación CABA · Universidades (UBA, UP, Palermo, UADE, UdeSA)
- Institutos terciarios · Talleres/academias
- Portal Padres · British Council · Colegios bilingües

### Economía / Mercados (4)
- MercadoLibre precios · Cotización dólar blue
- Inflatables histórico · SEPA BCRA canasta

### Deportes / Bienestar (7)
- Wellhub/Gympass · Clubes deportivos GCBA
- Canchas de tenis municipales · Piletas municipales
- Canchas de pádel BA · Parque Tres de Febrero · ClassPass BA

### Startups / Tech (6)
- Crunchbase · AngelList/Wellfound · LinkedIn empresas
- Clutch.co · Glassdoor · INPI marcas

### Ambiente / Clima (7)
- SMN · APRA calidad del aire · ACUMAR contaminación
- Sensores ruido urbano · AySA cortes · EDESUR/EDENOR cortes · Arbolado urbano

### Seguridad (3)
- Mapa del Delito CABA · Cámaras GCBA · Nextdoor alertas

### Historia / Patrimonio (3)
- Calles históricas · Archivo GCBA · Biblioteca Nacional

### Señales digitales / UGC (10)
- Instagram hashtag Palermo · Twitter/X geo · Reddit r/buenosaires
- Facebook grupos · Google Reviews ✅ · YouTube reviews
- TikTok trending · Google Trends · Mastodon geo · Tripadvisor foros

**Total: ~123 fuentes · 3 listas ✅ · 3 en progreso ⏳ · 117 nuevas 🔵**

---

## Fase 2 — Retroalimentación y señales de uso

- Tabla `query_log` para registrar cada búsqueda con resultado
- Si resultado vacío → trigger de scraping dirigido para esa entidad
- Cross-validation entre fuentes → subir/bajar confidence score
- Deduplicación automática con `entity_resolver.py`

---

## Fase 3 — Agente IA

Ver `AGENTS.md` para arquitectura del agente.

---

## Fase 4 — Frontend

- Next.js en Vercel
- Mapa interactivo de Palermo
- Search bar con autocompletado
- Vista detalle de entidad con historial de propiedades

---

## Comandos útiles

```bash
# Correr API
python -m uvicorn api.main:app --reload

# Correr un scraper
python -m scrapers.gcba_ba_data
python -m scrapers.google_places

# Verificar DB
psql $DATABASE_URL -c "SELECT type, COUNT(*) FROM entities WHERE canonical_id IS NULL GROUP BY type;"
```
