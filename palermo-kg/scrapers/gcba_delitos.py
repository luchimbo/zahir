"""
Scraper: BA Data GCBA - Estadísticas de Delitos
Fuente: https://data.buenosaires.gob.ar
Tier 1 - datasets oficiales CSV sin autenticacion.

Dataset: delitos
Agrega las estadísticas por año y tipo de delito, y las asocia a la entidad canónica de Palermo.
"""

import asyncio
import csv
import io
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import (
    get_conn,
    get_source_id,
    get_or_create_entity,
    upsert_property,
)
from scrapers.shared.normalizer import normalize_value

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
    import re
    print("=== Scraper GCBA Estadisticas de Delitos ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        
        # Obtener o crear la entidad canónica de Palermo
        palermo_id = await conn.fetchval(
            """
            SELECT id FROM entities
            WHERE entity_type = 'Location' AND name = 'Palermo (barrio)' AND canonical_id IS NULL
            LIMIT 1
            """
        )
        if not palermo_id:
            print("  Palermo (barrio) no encontrado. Creándolo...")
            palermo_id = await get_or_create_entity(
                conn,
                name="Palermo (barrio)",
                entity_type="Location",
                subtype="barrio",
                origin_url="https://data.buenosaires.gob.ar"
            )
            
        palermo_id = str(palermo_id)
        print(f"  Entidad Palermo (barrio) ID: {palermo_id}")
        
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            for anio, url in DELITOS_URLS.items():
                print(f"-> Procesando delitos de {anio}...")
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    text = r.content.decode("utf-8-sig", "replace")
                    rows = csv.DictReader(io.StringIO(text))
                except Exception as exc:
                    print(f"  Fallo descarga de {anio}: {exc}")
                    continue
                
                # Contadores para tipos de delitos en Palermo
                stats = Counter()
                total_palermo = 0
                
                for row in rows:
                    barrio = (row.get("barrio") or "").strip().upper()
                    if barrio == "PALERMO":
                        tipo = (row.get("tipo") or "Otros").strip()
                        cantidad = 1
                        try:
                            cantidad = int(row.get("cantidad") or 1)
                        except ValueError:
                            pass
                        stats[tipo] += cantidad
                        total_palermo += cantidad
                
                print(f"  Total delitos en Palermo para {anio}: {total_palermo}")
                if total_palermo == 0:
                    print("  No se encontraron registros de Palermo. Saltando upsert.")
                    continue
                    
                # Guardar estadísticas agregadas
                for tipo, count in stats.items():
                    tipo_slug = slugify(tipo)
                    prop_key = f"crime_stats_{anio}_{tipo_slug}"
                    print(f"    {tipo}: {count} -> {prop_key}")
                    
                    await upsert_property(
                        conn,
                        palermo_id,
                        prop_key,
                        str(count),
                        "number",
                        source_id,
                        origins=[url],
                        confidence=0.98
                    )
                
                # Guardar total anual
                await upsert_property(
                    conn,
                    palermo_id,
                    f"crime_stats_{anio}_total",
                    str(total_palermo),
                    "number",
                    source_id,
                    origins=[url],
                    confidence=0.98
                )
                
        print("\n[OK] Scraper de estadísticas de delitos finalizado con éxito.")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    import re  # Asegurar import de re
    asyncio.run(main())
