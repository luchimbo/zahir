# Operación de fuentes

Este documento define cómo se habilitan, observan y mantienen las fuentes del
CABA Knowledge Graph. Complementa las reglas de `db/RULES.md`.

## Registro mínimo

Cada fuente en `sources` debe tener nombre en `snake_case`, URL, tier y una
política documentada aquí antes de ejecutar una ingesta. Después de una
ejecución exitosa, el scraper debe actualizar `sources.scraped_at`.

Para cada fuente se registran también, en el historial de ejecución o el
orquestador: licencia/términos, frecuencia objetivo, cuota/costo, método de
acceso, última ejecución, filas leídas, entidades afectadas y error si falló.

## Políticas iniciales

| Fuente | Frecuencia objetivo | Método | Regla de activación |
|---|---:|---|---|
| `ba_data` | diaria o según dataset | CSV / CKAN | Siempre incremental y con filtro Palermo/Comuna 14. |
| `gcba_wfs` / IDECABA | mensual | WFS | Validar capa y licencia antes de cada nueva capa. |
| `osm` | mensual | Overpass | Respetar límites del servicio y atribución ODbL. |
| `wikidata` | mensual | SPARQL | Consultas acotadas geográficamente. |
| `igj` | semanal | fuente pública | No inferir estado legal si no está expresamente publicado. |
| `boletin_oficial` | diaria | PDF/HTML | Conservar URL, fecha y fragmento verificable. |
| `google_places` | semanal | API con cuota | Requiere presupuesto/cuota aprobados. |
| `arca` | bajo demanda | SOAP autenticado | Requiere ticket WSAA, certificado y representación autorizada; no ejecutar sin esas credenciales. |
| `inpi` | pendiente | consulta web | No hay API/dataset oficial general validado; no automatizar mediante scraping hasta confirmar términos y acceso. |
| `georef` | bajo demanda | API pública | Respaldo de USIG; no sobrescribe coordenadas GCBA válidas. |
| `padron_educativo` | anual | descarga oficial | Requiere `PADRON_EDUCATIVO_URL` vigente; resolver por CUE/CUI antes de crear. |
| `indec_censo` | por censo | WFS/Redatam | Sólo indicadores agregados por radio censal; no por domicilio. |
| `ign` | bajo demanda | WMS/WFS | Referencia cartográfica; no duplica infraestructura de GCBA. |
| `sinca` | anual | CKAN | Histórico visible: conservar fecha y no presentar como agenda vigente. |
| `refes` | desactivada | pendiente | Validar endpoint de descarga, licencia y condiciones antes de activar. |
| `refes_historical` | anual | XLSX oficial | Fuente 2024: sólo validación histórica, no sustituye GCBA. |
| `transporte_rmba` | manual | KML oficial | Red histórica; complementa y no reemplaza movilidad GCBA. |
| `national_monuments` | desactivada | descubrimiento | Sin descarga estructurada unificada validada; no ingerir automáticamente. |
| `cnv` | desactivada | pendiente | Registros públicos son buscador por registro individual, sin export masivo; no automatizar hasta validar dataset. |
| `byma_merval` / `byma_ypf` | diaria | BYMA Open Data | Histórico oficial nacional, sin coordenadas; backfill manual y luego refresh incremental. |
| `ambito_merval` / `ambito_ypf` | manual | endpoint approval-gated | Respaldo histórico secundario; ejecutar sólo con `--include-approval` y citar siempre Ámbito. |
| `bcra_estadisticas` | diaria | API oficial BCRA | Allowlist macro curada; el backfill inicial es manual. |
| `bcra_comunicaciones` | manual | índices PDF BCRA | Requiere `--include-credentials --allow-paid`; el resumen LLM es opcional. |

## Control previo a una fuente nueva

1. Confirmar licencia, términos, autenticación y límites.
2. Ejecutar una muestra pequeña, filtrada a Palermo, sin carga masiva.
3. Medir duplicados, geocodificación y propiedades útiles.
4. Registrar la fuente y agregar smoke test antes de calendarizarla.

## Pilotos y promoción

Todas las fuentes nuevas se ejecutan primero como piloto limitado. El único
entrypoint es `scripts/run_sources.py`:

```powershell
# valida (sin escritura) un adaptador con contrato
.\.venv\Scripts\python scripts\run_sources.py --source gcba_sports --validate
# escribe una muestra y sólo habilita el refresh si supera los controles
.\.venv\Scripts\python scripts\run_sources.py --source gcba_sports --pilot --limit 25 --promote
# consulta cuáles fuentes quedaron habilitadas
.\.venv\Scripts\python scripts\run_sources.py --status
```

Un piloto debe devolver registros válidos, origen trazable y cero errores
fatales. `--promote` habilita exclusivamente la fuente que cumpla esos
criterios; una reejecución idempotente puede escribir cero filas nuevas y aun
así ser promovible. El refresh diario ejecuta sólo fuentes promovidas.

Los adaptadores candidatos usan una URL de dataset oficial explícita, para
evitar convertir portales o buscadores web en scraping no autorizado:

| Fuente | Variable de dataset |
|---|---|
| Trenes SOFSE | `TRENES_SOFSE_DATA_URL` |
| IDECBA Comuna / alquileres | `IDECBA_COMUNA_DATA_URL` / `IDECBA_ALQUILERES_DATA_URL` |
| GCBA economía circular / turismo | `GCBA_ECOCIRCULAR_DATA_URL` / `GCBA_TURISMO_DATA_URL` |
| SUBE | `SUBE_OPEN_DATA_URL` |
| CIJ / MPF / RPI | `CIJ_CAUSAS_DATA_URL`, `MPF_DELITOS_DATA_URL`, `RPI_CONSULTAS_DATA_URL` |

`CIJ` y `RPI` siguen requiriendo validación de términos y se mantienen en
modo `approval` aunque exista una URL configurada.

## Programador local

`scripts/install_task_scheduler.ps1` instala la tarea diaria
`PalermoKG-DailyRefresh` a las 03:00. La tarea llama a
`scripts/scheduled_refresh.py`, evita ejecuciones concurrentes mediante Task
Scheduler y conserva los últimos 30 logs en `logs/`.

## Fuentes evaluadas y no activadas

- **ARCA, padrón:** el web service de padrón devuelve datos públicos por CUIT,
  pero cada llamada exige token y firma obtenidos mediante WSAA. La credencial
  debe pertenecer a una organización autorizada; no se sustituye con scraping
  de la consulta pública.
- **INPI, marcas:** el portal permite consultas individuales de marcas, pero
  todavía no se validó una interfaz oficial de descarga o API para una ingesta
  repetible. Queda en evaluación manual.
- **CNV, mercado de capitales:** se evaluó `cnv.gov.ar/SitioWeb/RegistrosPublicos`
  (agentes, agentes de PIC, mercados, calificadoras, auditores, idóneos, PSAV) y
  `cnv.gov.ar/sitioweb/empresas` (emisoras). Los nueve registros son buscadores
  por apellido/razón social/CUIT/número, con página de detalle por resultado
  (`DetallesRegistrosPublicos/{id}`), sin botón de exportación ni endpoint
  JSON/CSV documentado. El único dataset masivo real de CNV encontrado en
  datos.gob.ar (`sspm-fondos-comunes-inversion`) es agregado por tipo de fondo,
  no un padrón de entidades con domicilio. No se activa: automatizar el
  buscador sería scraping de un portal de consulta, lo que la política del
  proyecto evita explícitamente. Reevaluar si CNV publica alguna vez un
  dataset abierto de emisoras/agentes en su catálogo de datos abiertos
  (`argentina.gob.ar/cnv/transparencia/catalogos-de-datos-abiertos`).
- **SSN, aseguradoras:** `datosabiertos.ssn.gob.ar` sí es un portal CKAN real
  con CSV masivo (CC-BY 4.0) para aseguradoras, sociedades de productores
  asesores, agentes institorios, etc. — a diferencia de CNV, el problema no es
  de acceso sino de dato: ninguno de esos CSV trae domicilio. Se intentó
  enriquecer los `LegalEntity` de IGJ cruzando por CUIT en vez de crear
  entidades sin ubicación, pero los 877 `LegalEntity` cargados hoy no tienen
  la propiedad `cuit` (se cargaron con una versión anterior de `igj.py` y
  `sources.scraped_at` de `igj` está en `NULL`). Sin CUIT del lado de IGJ el
  cruce no tiene con qué matchear. Reevaluar cuando se recargue IGJ con la
  versión actual del scraper (si vuelve a correr, sí escribe `cuit`).
- **BCRA/SGR, otras entidades financieras:** `datos.gob.ar` sólo tiene
  agregados (préstamos a entidades financieras, indicadores de SGR), no un
  padrón de entidades con domicilio; `bcra.gob.ar`/`www2.bcra.gob.ar` no
  respondió de forma confiable desde este entorno. No hay candidato viable
  todavía en este rubro.

## Auditoría

Ejecutar periódicamente:

```powershell
.\.venv\Scripts\python scripts\source_audit.py
```

El reporte es de solo lectura y muestra volumen, porcentaje geocodificado y
frescura observada. Una fuente sin `scraped_at` no se considera monitoreada,
aunque tenga propiedades históricas.
