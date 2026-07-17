# Fuentes externas preparadas, no activadas

Estas integraciones quedan deliberadamente desactivadas. No se agregan credenciales de ejemplo ni se realizan solicitudes automáticas.

| Fuente | Variable requerida | Requisito antes de activar |
|---|---|---|
| ARCA padrón | `ARCA_CERT_PATH`, `ARCA_PRIVATE_KEY_PATH`, `ARCA_CUIT` | WSAA, certificado y representación autorizada. |
| INPI | `INPI_ACCESS_TOKEN` si se habilita una API oficial | Confirmar API, licencia y términos de automatización. |
| Google Places | `GOOGLE_PLACES_API_KEY` | Presupuesto/cuotas aprobados. |
| Agenda cultural externa | `CULTURE_AGENDA_API_KEY` si corresponde | API oficial vigente y contrato de uso. |

Los scrapers inmobiliarios y scraping agresivo permanecen fuera de este refresh manual.

## REFES / Salud Nación

El adaptador `refes` queda desactivado: el registro se utilizará sólo para
validar servicios y contacto de centros de salud ya existentes cuando se confirme
un endpoint de descarga oficial, estable y permitido. No se agrega al refresh.
