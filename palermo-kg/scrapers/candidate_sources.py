"""Entrypoints para las nueve fuentes aprobadas del backlog.

Las fuentes web frágiles o con términos por confirmar requieren una URL de
dataset explícita en el entorno. Así nunca se convierte una página de búsqueda
en scraping automático accidental.
"""
from __future__ import annotations

import argparse
import asyncio
import os

from scrapers.shared.contract import add_source_arguments
from scrapers.shared.tabular_source import TabularConfig, run_tabular


SPECS = {
    "trenes_sofse": ("TRENES_SOFSE_DATA_URL", "Transport", "train_station", 1),
    "idecba_comuna": ("IDECBA_COMUNA_DATA_URL", "Location", "statistical_area", 1),
    "gcba_ecocircular": ("GCBA_ECOCIRCULAR_DATA_URL", "Facility", "recycling_point", 1),
    "gcba_turismo": ("GCBA_TURISMO_DATA_URL", "Facility", "tourist_attraction", 1),
    "sube_open": ("SUBE_OPEN_DATA_URL", "Transport", "public_transport", 1),
    "cij_causas": ("CIJ_CAUSAS_DATA_URL", "LegalCase", "judicial_case", 2),
    "mpf_delitos": ("MPF_DELITOS_DATA_URL", "HistoricalRecord", "crime_statistic", 2),
    "rpi_consultas": ("RPI_CONSULTAS_DATA_URL", "Parcel", "property_registry", 2),
    "idecba_alquileres": ("IDECBA_ALQUILERES_DATA_URL", "Location", "rental_market", 1),
}


async def main_for(source_name: str):
    parser = argparse.ArgumentParser(description=f"Ingesta {source_name}")
    add_source_arguments(parser)
    args = parser.parse_args()
    env_key, entity_type, subtype, tier = SPECS[source_name]
    url = os.getenv(env_key)
    if not url:
        raise RuntimeError(f"{env_key} es obligatorio: configure un dataset oficial CSV/JSON/GeoJSON validado antes de activar {source_name}.")
    return await run_tabular(TabularConfig(source_name, url, tier, entity_type, subtype), write=args.write, limit=args.limit)


def run(source_name: str):
    return asyncio.run(main_for(source_name))
