# Investigacion de fuentes para scrapear Palermo

Fecha: 2026-07-02  
Alcance: fuentes no-inmobiliarias. Quedan pausados Zonaprop, Argenprop, MercadoLibre Inmuebles y precios de alquiler/venta.

## Criterio de prioridad

- P0: alto valor, fuente publica/estructurada, scraper simple.
- P1: alto valor, requiere normalizacion o cruces.
- P2: valor contextual, mas volumen o mantenimiento.
- P3: fuente fragil, web scraping, API paga o baja trazabilidad.

## P0 - Scrapers oficiales faciles

| Fuente | Dataset / origen | Que extraer | Entidades | Valor para preguntas |
|---|---|---|---|---|
| BA Data - Farmacias | `farmacias` | nombre, direccion, coords, telefono si existe | `Facility` subtype `farmacia` | "farmacias cerca", cobertura salud barrial |
| BA Data - Establecimientos educativos | `establecimientos-educativos` | nombre, nivel, gestion, direccion, coords | `Facility` subtype `escuela`, `universidad`, etc. | escuelas/colegios por zona |
| BA Data - Espacios verdes | `espacios-verdes` | parques, plazas, superficies, geometria | `Facility` subtype `parque/plaza` | verde urbano, plazas cercanas |
| BA Data - Ecobici estaciones | `estaciones-bicicletas-publicas` | estacion, direccion, coords, sistema | `Transport` subtype `ecobici` | movilidad cercana |
| BA Data - Subte estaciones y bocas | `subte-estaciones`, `bocas-subte` | estaciones, lineas, accesos, coords | `Transport` | transporte y accesibilidad |
| BA Data - Colectivos paradas | `colectivos-paradas` | parada, lineas, coords | `Transport` subtype `parada_colectivo` | conectividad por lugar |
| BA Data - Espacios culturales | `espacios-culturales` | nombre, tipo, direccion, coords | `Facility` subtype `espacio_cultural` | cultura, salidas |
| BA Data - Ferias y mercados | `ferias-mercados` | feria, dias, horarios, ubicacion | `Event` o `Facility` | ferias barriales y mercados |

## P1 - Oficiales con alto valor contextual

| Fuente | Dataset / origen | Que extraer | Entidades | Observaciones |
|---|---|---|---|---|
| AGC - Habilitaciones aprobadas | `habilitaciones-aprobadas` | razon social/local, rubro, direccion, fecha | `Organization`, `LegalEntity` | Cruza comercios con legalidad/habilitacion. |
| Mapa de Oportunidades Comerciales | `mapa-oportunidades-comerciales-moc` | aperturas, cierres, rubros, demografia | propiedades de `Location` o señales comerciales | Sirve para "que rubros crecen en Palermo". |
| Salud publica | `hospitales`, `centros-salud-accion-comunitaria-cesac` | nombre, tipo, direccion, coords | `Facility` subtype `hospital/cesac` | Muy confiable. |
| Salud privada | `centros-salud-privados` | nombre, tipo, direccion | `Facility` subtype `centro_salud_privado` | Complementa Google Places. |
| Comisarias | `comisarias-policia-ciudad` | nombre, jurisdiccion, direccion, coords | `Facility` subtype `comisaria` | Seguridad/servicios. |
| WiFi publico | `puntos-wi-fi-publicos` | sitio, coords, lugar | `Facility` subtype `wifi_publico` | Utilidad urbana. |
| Monumentos y murales | `monumentos`, `murales` | nombre, autor, direccion, coords si existe | `Facility` / `HistoricalRecord` | Patrimonio e historia local. |
| Areas de Proteccion Historica | `areas-proteccion-historica` | area, normativa, poligono | `HistoricalRecord` / `Location` | Contexto historico y urbano. |
| Decks gastronomicos | `calzada-gastronomica` | calles habilitadas, geometria | `Location` / propiedad de calle | Senal comercial/gastronomica sin scrappear restaurantes. |

## P1 - Ambiente y calidad urbana

| Fuente | Dataset / origen | Que extraer | Modelado recomendado |
|---|---|---|---|
| Arbolado publico lineal | `arbolado-publico-lineal` | especie, altura, diametro, calle, coords | `Facility` subtype `arbol` o agregado por `Location` |
| Arbolado en espacios verdes | `arbolado-espacios-verdes` | especie, parque/plaza, coords | relacion `LOCATED_IN` con espacio verde |
| Calidad de aire | `calidad-aire` | contaminante, estacion, fecha, valor | propiedad temporal de `Location` o `Facility` estacion ambiental |
| Mapa de ruido | `mapa-ruido` | ruido diurno/nocturno, zona, geometria | propiedad `noise_level` en `Location` |
| Sitios posibles de anegamiento | `sitios-posibles-anegamiento` | punto/zona de riesgo, periodo | `Location` tag `flood-risk` |
| Reclamos BA Colaborativa | `sistema-unico-atencion-ciudadana` | categoria, barrio, fecha, estado | señales agregadas por zona; no entidad por reclamo salvo casos relevantes |

## P2 - Seguridad, fiscalizacion y gobierno

| Fuente | Dataset / origen | Que extraer | Cuidado |
|---|---|---|---|
| Delitos | `delitos` | tipo, comuna/barrio, fecha, coords si disponibles | Agregar estadisticas por zona, evitar exponer datos sensibles. |
| Fiscalizaciones | `fiscalizaciones` | rubro, resultado, fecha, direccion | Cruza con comercios; requiere normalizacion. |
| Locales bailables | `locales-bailables` | nombre, direccion, habilitacion | Interesante para noche/cultura. |
| Obras registradas / BA Obras | `obras-registradas`, `ba-obras` | obra, ubicacion, estado, organismo | No inmobiliario comercial, pero toca ciudad/obra publica. |
| Alumbrado LED | `alumbrado-led` | calle/sector con luminaria | seguridad/percepcion urbana. |

## P2 - Fuentes abiertas no GCBA

| Fuente | Que extraer | Por que sirve | Riesgo |
|---|---|---|---|
| OpenStreetMap / Overpass | POIs, shops, amenities, opening_hours, cuisine, accessibility | Cobertura amplia y libre | Calidad variable; dedup fuerte necesaria |
| Wikidata SPARQL | museos, teatros, hospitales, universidades, monumentos | IDs estables y links externos | No siempre Palermo exacto |
| Wikipedia | resumen historico de lugares destacados | contexto narrativo trazable | No usar para datos operativos actuales |
| datos.gob.ar | IGJ, datasets nacionales, transporte, ambiente | complementa CABA | Buscar dataset por dataset |
| Servicio Meteorologico Nacional | clima historico/actual | preguntas de ambiente/temporada | No hiperlocal a Palermo |

## P3 - Web scraping y APIs externas

| Fuente | Que extraer | Valor | Motivo P3 |
|---|---|---|---|
| Alternativa Teatral | obras, salas, fechas, entradas | eventos culturales vivos | HTML scraping, cambios frecuentes |
| Sitios de venues culturales | Niceto, La Rural, CC Recoleta, Planetario, etc. | agenda muy actual | Scraper por sitio |
| Eventbrite / Meetup | eventos privados y comunidad | eventos no oficiales | API/auth o scraping fragil |
| Google Places refresh | horarios, ratings, reviews_count, categorias | comercio actual | API paga/cuotas |
| TripAdvisor / Guia Oleo | gastronomia, reviews, rankings | recomendaciones | scraping delicado y ToS |
| Instagram / TikTok / YouTube | senales de popularidad | tendencias | baja trazabilidad, APIs limitadas |

## Scrapers recomendados para implementar primero

1. `gcba_health_education.py` - implementado
   - Datasets: `farmacias`, `hospitales`, `centros-salud-accion-comunitaria-cesac`, `centros-salud-privados`, `establecimientos-educativos`.
   - Impacto: salud + educacion confiable.
   - Nota: usa filtro por `barrio` cuando el dataset lo trae; el bounding box solo queda como fallback para evitar traer barrios vecinos.

2. `gcba_mobility.py` - implementado
   - Datasets: `estaciones-bicicletas-publicas`, `subte-estaciones`, `bocas-subte`, `colectivos-paradas`, `colectivos-recorridos`.
   - Impacto: preguntas de conectividad y accesibilidad.
   - Nota: usa filtro por barrio cuando existe; en recorridos detecta si la geometria pasa por Palermo y guarda un punto representativo.

3. `gcba_culture_public_space.py` - implementado
   - Datasets: `espacios-culturales`, `ferias-mercados`, `monumentos`, `murales`, `calesitas`.
   - Impacto: cosas para hacer y patrimonio.
   - Nota: carga solo Palermo por barrio o bounding box y guarda origins oficiales por propiedad.

4. `gcba_environment.py` - implementado
   - Datasets: `arbolado-publico-lineal`, `arbolado-espacios-verdes`, `calidad-aire`, `mapa-ruido`, `sitios-posibles-anegamiento`.
   - Impacto: calidad urbana, verde, ruido, ambiente.
   - Nota: usa fuentes oficiales GCBA, filtros por Comuna 14/bounding box y carga batch con limites de arbolado para no saturar Neon.

5. `gcba_commercial_signals.py` - implementado
   - Datasets: `habilitaciones-aprobadas`, `mapa-oportunidades-comerciales-moc`, `calzada-gastronomica`.
   - Impacto: actividad comercial sin entrar en inmobiliario.
   - Nota: usa habilitaciones 2026 por Comuna 14, MOC con zonas GeoJSON y permisos/decks gastronomicos oficiales.

## Preguntas nuevas que permitiria responder

- "Que farmacias y centros de salud tengo cerca de Plaza Italia?"
- "Que colegios publicos/privados hay en Palermo?"
- "Que estaciones Ecobici y paradas de colectivo quedan cerca de X?"
- "Que ferias hay esta semana o regularmente en Palermo?"
- "Que espacios culturales hay en Palermo Soho/Hollywood?"
- "Que zonas tienen mas arbolado o menos ruido?"
- "Que comercios/rubros estan habilitados por AGC?"
- "Que calles tienen permiso para decks gastronomicos?"
- "Que monumentos, murales o areas patrimoniales hay en Palermo?"

## Fuentes consultadas

- BA Data: https://data.buenosaires.gob.ar/
- CKAN package search: https://data.buenosaires.gob.ar/api/3/action/package_search
- CKAN package show: https://data.buenosaires.gob.ar/api/3/action/package_show
- OpenStreetMap Overpass API: https://overpass-api.de/
- Wikidata SPARQL: https://query.wikidata.org/
