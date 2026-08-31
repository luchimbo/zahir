"""Guardia de acceso para CNV: no automatiza scraping de un buscador sin dataset masivo.

Los registros públicos de CNV (agentes, emisoras, fondos, calificadoras) sólo
exponen una consulta por nombre/CUIT/número, sin exportación CSV/JSON ni API
documentada. Convertir ese buscador en scraping masivo violaría la política
del proyecto de no automatizar portales de búsqueda. Ver SOURCE_OPERATIONS.md.
"""
import os
def main():
    if not os.getenv("CNV_DATASET_URL"):
        raise RuntimeError("CNV bloqueado: no hay dataset oficial masivo (CSV/JSON/API) validado, sólo búsqueda por registro individual.")
    raise RuntimeError("CNV bloqueado: configurar endpoint oficial de descarga masiva y condiciones de uso antes de habilitar la ingesta.")
if __name__ == "__main__": main()
