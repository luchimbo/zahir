# Investigación de fuentes — CABA

Actualizado: 2026-08-28. Esta lista separa fuentes verificadas para la carga
inicial de CABA de fuentes que requieren condiciones adicionales. Cada conector
debe usar el contrato territorial y reportar cobertura por barrio/comuna.

## Prioridad de carga inicial

| Fuente | Cobertura y valor | Formato / estrategia | Estado |
|---|---|---|---|
| [Límites de barrios GCBA](https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/barrios/barrios.geojson) | 48 barrios y 15 comunas; referencia para toda entidad puntual | GeoJSON; cargar primero y resolver punto-en-polígono | Implementado en `scrapers.geography` |
| [Hospitales](https://data.buenosaires.gob.ar/dataset/hospitales) y [Farmacias](https://data.buenosaires.gob.ar/dataset/farmacias) | Salud, dirección, teléfono, barrio y comuna | CSV/GeoJSON; ID del proveedor cuando exista | Migrar `gcba_health_education` a CABA |
| [Espacios culturales](https://data.buenosaires.gob.ar/dataset/espacios-culturales) | Museos, bibliotecas, centros culturales, monumentos y salas | CSV/SHP; entidad puntual geocodificada | Migrar `gcba_culture_public_space` a CABA |
| [AGC: habilitaciones](https://data.buenosaires.gob.ar/dataset/habilitaciones-aprobadas), [fiscalizaciones](https://data.buenosaires.gob.ar/dataset/fiscalizaciones), [obras](https://data.buenosaires.gob.ar/dataset/obras-iniciadas) y [locales bailables](https://data.buenosaires.gob.ar/dataset/locales-bailables) | Actividad comercial, controles, obras y eventos; alto valor para consultas locales | CSV/XLSX; procesar incrementalmente por fecha, dirección e ID | Migrar los conectores AGC a CABA |
| [Movilidad, subte y colectivos](https://data.buenosaires.gob.ar/dataset/?tags=movilidad) | Estaciones, paradas, red e indicadores operativos | CSV/GeoJSON; puntos y líneas, relaciones con barrios | Migrar `gcba_mobility` a CABA |
| [IDECBA alquileres](https://www.estadisticaciudad.gob.ar/eyc/categoria-banco-datos/alquileres/) | Series por barrio y comuna de precios, superficie y ambientes | Tablas descargables; crear propiedades históricas en `Location`, no avisos individuales | Fuente agregada P0 |

## Fuentes valiosas con tratamiento especial

| Fuente | Decisión |
|---|---|
| [Arbolado público lineal](https://data.buenosaires.gob.ar/dataset/arbolado-publico-lineal) | Incorporar en lotes y como capa ambiental. El recurso disponible incluye registros geolocalizados, pero su período base es 2017–2018: debe etiquetarse como histórico/contextual, no como estado actual. |
| [Agenda oficial de Turismo](https://turismo.buenosaires.gob.ar/es/busqueda/agenda) | Candidata para eventos vigentes. Antes de automatizar, validar términos, paginación y si cada ficha ofrece fecha/lugar estructurados. |
| [API de Lugares de Interés](https://data.buenosaires.gob.ar/dataset/api-busqueda-lugares-interes) | No usar en la carga inicial: la propia ficha informa que las APIs y GTFS están suspendidos/revisión. Mantener sólo como vigilancia de reactivación. |
| Google Places, Zonaprop y Argenprop | No bloquear CABA. Requieren credenciales, costo y/o autorización explícita; usar ID externo para no fusionar sucursales. |

## Orden operativo

1. Cargar y validar la geografía oficial en staging.
2. Migrar fuentes puntuales públicas: salud, cultura, movilidad y AGC.
3. Cargar IDECBA como indicadores agregados por barrio/comuna.
4. Ejecutar `scripts/caba_readiness.py`; exigir cobertura, trazabilidad y cero puntos fuera de CABA.
5. Sólo después incorporar fuentes de gran volumen, web o pagas.

## Criterios de admisión

- URL de recurso oficial y licencia/condiciones identificables.
- ID estable o combinación de nombre, dirección y coordenadas.
- Fecha de actualización conocida y origen guardado por propiedad.
- Geografía oficial resoluble; si no hay punto ni barrio/comuna, no se publica como entidad puntual.
- Piloto de cada fuente en staging antes de habilitar su refresh.

**Excepción — capa nacional/contextual:** una fuente sin geografía resoluble puede admitirse si (a) es una serie temporal o normativa de alcance nacional publicada por un organismo oficial, (b) se carga con `territory="national"` y sin coordenadas (`lat=lng=NULL`), de modo que nunca compite con entidades puntuales de CABA ni aparece en `scripts/caba_readiness.py`, y (c) su valor es contextual — explicar el entorno macro/financiero de la Ciudad, no describir un lugar. Las fuentes admitidas por esta vía son `byma_merval`, `byma_ypf`, `ambito_merval`, `ambito_ypf`, `bcra_estadisticas` y `bcra_comunicaciones` (ver `db/RULES.md` §11 y `SOURCE_OPERATIONS.md`).
