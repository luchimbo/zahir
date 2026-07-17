"""Registra metadatos de las fuentes nacionales sin descargar ni ingerir datos."""
import asyncio
from scrapers.shared.db_helpers import ensure_source, get_conn

SOURCES = {
    "georef": ("https://apis.datos.gob.ar/georef/api/v2.0", 1),
    "padron_educativo": ("https://www.argentina.gob.ar/node/246613", 1),
    "indec_censo": ("https://geonode.indec.gob.ar", 1),
    "ign": ("https://www.ign.gob.ar/NuestrasActividades/InformacionGeoespacial/ServiciosOGC", 1),
    "sinca": ("https://datos.gob.ar/dataset/cultura-mapa-cultural-espacios-culturales", 4),
    "refes": ("https://www.argentina.gob.ar/salud", 1),
}

async def main():
    conn = await get_conn()
    try:
        for name, (url, tier) in SOURCES.items():
            await ensure_source(conn, name, url, tier)
            print(f"registrada: {name}")
    finally:
        await conn.close()

if __name__ == "__main__": asyncio.run(main())
