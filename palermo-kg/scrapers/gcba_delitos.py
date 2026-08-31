"""
Scraper: BA Data GCBA - Estadísticas de Delitos
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV sin autenticacion.

Dataset: delitos
Agrega las estadísticas por año y tipo de delito, y las asocia a la entidad
canónica de cada barrio en el alcance elegido (CABA por defecto).
"""
import argparse
import asyncio
import csv
import io
import re
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import (
    get_conn,
    get_source_id,
    get_or_create_entity,
    mark_source_synced,
    upsert_property,
)
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.geo_scope import record_in_scope
from geography_catalog import resolve_neighborhood

SUPPORTS_SOURCE_CONTRACT = True
SOURCE_NAME = "ba_data"

DELITOS_URLS = {
    2023: "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/delitos/delitos_2023.csv",
    2024: "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/delitos/delitos_2024.csv",
}


def slugify(text: str) -> str:
    """Convierte texto en un slug simple (ej: 'Robo (con violencia)' -> 'robo')."""
    t = text.lower().strip()
    t = t.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    t = re.sub(r"[^a-z0-9_]+", "_", t)
    return t.strip("_")


async def main():
    parser = argparse.ArgumentParser()
    add_source_arguments(parser)
    args = parser.parse_args()

    print("=== Scraper GCBA Estadisticas de Delitos ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, SOURCE_NAME)

        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            seen = 0
            for anio, url in DELITOS_URLS.items():
                print(f"-> Procesando delitos de {anio}...")
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    text = r.content.decode("utf-8-sig", "replace")
                    rows = list(csv.DictReader(io.StringIO(text)))
                except Exception as exc:
                    print(f"  Fallo descarga de {anio}: {exc}")
                    continue
                rows = bounded(rows, args.limit) if args.limit else rows

                for row in rows:
                    barrio_raw = (row.get("barrio") or "").strip()
                    if not barrio_raw:
                        continue
                    seen += 1
                    if not record_in_scope(row_neighborhood=barrio_raw, scope=args.scope,
                                           neighborhood=args.neighborhood, commune=args.commune):
                        continue

                    official = resolve_neighborhood(barrio_raw)
                    nombre = official or barrio_raw
                    palermo_id = await get_or_create_entity(
                        conn,
                        name=f"{nombre} (barrio)" if official else f"{barrio_raw} (barrio)",
                        entity_type="Location",
                        subtype="barrio",
                        origin_url="https://data.buenosaires.gob.ar"
                    )
                    palermo_id = str(palermo_id)

                    tipo = (row.get("tipo") or "Otros").strip()
                    try:
                        cantidad = int(row.get("cantidad") or 1)
                    except ValueError:
                        cantidad = 1

                    tipo_slug = slugify(tipo)
                    prop_key = f"crime_stats_{anio}_{tipo_slug}"
                    print(f"    {nombre} | {anio} | {tipo}: {cantidad} -> {prop_key}")
                    await upsert_property(
                        conn,
                        palermo_id,
                        prop_key,
                        str(cantidad),
                        "number",
                        source_id,
                        origins=[url],
                        confidence=0.98
                    )

        if args.write:
            await mark_source_synced(conn, source_id)

        print(f"[OK] Delitos: {seen} filas evaluadas | scope={args.scope} | write={args.write}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
