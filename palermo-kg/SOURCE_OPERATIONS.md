# Operación de fuentes

Este documento define cómo se habilitan, observan y mantienen las fuentes del
Palermo Knowledge Graph. Complementa las reglas de `db/RULES.md`.

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
| `cep_xxi` / `enacom_context` / `ceamse_context` | manual | datos agregados | Activar sólo con granularidad CABA, radio o coordenadas verificables. |
| `national_monuments` | desactivada | descubrimiento | Sin descarga estructurada unificada validada; no ingerir automáticamente. |
| `up_disenio_comunicacion` / `up_mapa_espacios_disenio` | anual | web/PDF manual | Fuentes académicas e históricas; revisar derechos y fecha antes de extraer. |
| `michelin_guide_buenos_aires` / `hipodromo_gastronomia` | semanal/mensual | web manual | Usar para descubrimiento y verificación; no copiar reseñas extensas. |
| `observatorio_leyendas_palermo` / `palermonline_historia` | anual/trimestral | PDF/web manual | Separar hechos documentados de leyendas y crónicas. |
| `trama_ropa_autor` / `godoy_mix_group` | mensual | web manual | Verificar local, marca y vigencia comercial. |
| `palermo_design` / `modo_casa` / `madera_muebles` | mensual | web manual | Verificar showroom, dirección y oferta vigente. |
| `feliza_queer` / `agenda_queer` | semanal | web/red social manual | Eventos dinámicos; conservar fecha de captura y no inferir identidad. |
| `cc_nueva_uriarte` / `c3_ciencia` | semanal/mensual | web manual | Registrar agenda, talleres y sede. |
| `malba` / `museo_arte_decorativo` / `museo_evita` | mensual | web institucional | Registrar colecciones, exposiciones y horarios con fecha de vigencia. |

## Control previo a una fuente nueva

1. Confirmar licencia, términos, autenticación y límites.
2. Ejecutar una muestra pequeña, filtrada a Palermo, sin carga masiva.
3. Medir duplicados, geocodificación y propiedades útiles.
4. Registrar la fuente y agregar smoke test antes de calendarizarla.

## Fuentes evaluadas y no activadas

- **ARCA, padrón:** el web service de padrón devuelve datos públicos por CUIT,
  pero cada llamada exige token y firma obtenidos mediante WSAA. La credencial
  debe pertenecer a una organización autorizada; no se sustituye con scraping
  de la consulta pública.
- **INPI, marcas:** el portal permite consultas individuales de marcas, pero
  todavía no se validó una interfaz oficial de descarga o API para una ingesta
  repetible. Queda en evaluación manual.

## Auditoría

Ejecutar periódicamente:

```powershell
.\.venv\Scripts\python scripts\source_audit.py
```

El reporte es de solo lectura y muestra volumen, porcentaje geocodificado y
frescura observada. Una fuente sin `scraped_at` no se considera monitoreada,
aunque tenga propiedades históricas.
