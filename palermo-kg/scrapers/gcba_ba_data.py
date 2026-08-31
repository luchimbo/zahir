"""
Scraper: BA Data GCBA
Fuente: https://data.buenosaires.gob.ar
Tier 1 — API pública sin autenticación.

Datasets que importa:
  - Espacios verdes (parques, plazas) → Facility
  - Comunas y barrios               → Location
  - Estaciones de subte             → Transport
"""

import argparse
import asyncio
import httpx
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id, mark_source_synced
)
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.contract import add_source_arguments
from scrapers.shared.geo_scope import record_in_scope

SUPPORTS_SOURCE_CONTRACT = True

BA_DATA_BASE = "https://datosabiertos-usig-apis.buenosaires.gob.ar/usig"

DATASETS = {
    "espacios_verdes": {
        "url": f"{BA_DATA_BASE}/recorridos-saludables/recorridos",
        "entity_type": "Facility",
        "subtype": "parque",
    },
}

# API de barrios GCBA (GeoJSON)
BARRIOS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/barrios/barrios.geojson"

# API de estaciones de subte
SUBTE_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/sbase/subte-estaciones/estaciones-de-subte.geojson"

# API de espacios verdes
ESPACIOS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/espacios-verdes/espacio_verde_publico.geojson"

async def scrape_barrios(conn, source_id: str, args):
    print("-> Scrapeando barrios...")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(BARRIOS_URL)
        r.raise_for_status()
        data = r.json()

    features = data.get("features", [])
    if features:
        print(f"  [debug] keys disponibles: {list(features[0].get('properties', {}).keys())}")

    count = 0
    for f in features:
        props = f.get("properties", {})
        # Intentar varias keys posibles
        name = normalize_name(props.get("BARRIO") or props.get("barrio") or
                props.get("nombre") or props.get("NOMBRE") or "")
        if not name:
            continue

        coords = f.get("geometry", {}).get("coordinates", [])
        lat, lng = None, None
        try:
            lat = coords[0][0][1]
            lng = coords[0][0][0]
        except (IndexError, TypeError):
            pass

        if not record_in_scope(lat=lat, lng=lng, row_neighborhood=name, row_commune=props.get("COMUNA") or props.get("comuna"),
                               scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
            continue

        area_km2 = props.get("AREA") or props.get("area") or props.get("area_metro")
        perimeter = props.get("PERIMETRO") or props.get("perimetro") or props.get("perimetro_")
        comuna = props.get("COMUNA") or props.get("comuna")

        entity_id = await get_or_create_entity(
            conn, name=name, entity_type="Location", subtype="barrio",
            lat=lat, lng=lng,
            description=f"Barrio {name}, CABA",
            origin_url=BARRIOS_URL,
            all_names=[name.upper(), name.lower()]
        )

        if area_km2:
            await upsert_property(conn, entity_id, "area_km2", str(round(area_km2 / 1_000_000, 4)),
                                   "number", source_id, origins=[BARRIOS_URL])
        if comuna:
            await upsert_property(conn, entity_id, "comuna", str(int(comuna)),
                                   "number", source_id, origins=[BARRIOS_URL])
        if perimeter:
            await upsert_property(conn, entity_id, "perimetro_m", str(round(perimeter, 2)),
                                   "number", source_id, origins=[BARRIOS_URL])
        count += 1

    print(f"  OK {count} barrios procesados")


async def scrape_subte(conn, source_id: str, args):
    print("-> Scrapeando estaciones de subte...")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(SUBTE_URL)
        r.raise_for_status()
        data = r.json()

    features = data.get("features", [])
    if features:
        print(f"  [debug] keys subte: {list(features[0].get('properties', {}).keys())}")
    count = 0
    for f in features:
        props = f.get("properties", {})
        name = (props.get("estacion") or props.get("nombre") or
                props.get("ESTACION") or props.get("NOMBRE") or "").strip().title()
        linea = (props.get("linea") or props.get("LINEA") or
                 props.get("line") or "").strip()
        if not name or not linea:
            continue

        coords = f.get("geometry", {}).get("coordinates", [])
        # Point geometry → [lng, lat]
        lat = float(coords[1]) if len(coords) > 1 else None
        lng = float(coords[0]) if len(coords) > 0 else None

        if not record_in_scope(lat=lat, lng=lng, scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
            continue

        full_name = f"Estación {name} (Línea {linea})"

        entity_id = await get_or_create_entity(
            conn, name=full_name, entity_type="Transport", subtype="estacion_subte",
            lat=lat, lng=lng,
            description=f"Estación de subte {name}, Línea {linea}",
            origin_url=SUBTE_URL,
            all_names=[name, f"Subte {name}"]
        )

        await upsert_property(conn, entity_id, "linea", linea,
                               "string", source_id, origins=[SUBTE_URL])
        if props.get("long_nombre"):
            await upsert_property(conn, entity_id, "nombre_largo", props["long_nombre"],
                                   "string", source_id, origins=[SUBTE_URL])
        count += 1

    print(f"  OK {count} estaciones de subte procesadas")


async def scrape_espacios_verdes(conn, source_id: str, args):
    print("-> Scrapeando espacios verdes...")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(ESPACIOS_URL)
        r.raise_for_status()
        data = r.json()

    features = data.get("features", [])
    count = 0

    for f in features:
        props = f.get("properties", {})
        name = (props.get("nombre") or props.get("NOMBRE") or props.get("nom_mapa") or "").strip().title()
        barrio = (props.get("barrio") or props.get("BARRIO") or "").upper()

        if not name:
            continue

        geom = f.get("geometry", {})
        geom_type = geom.get("type", "")
        coords = geom.get("coordinates", [])
        lat, lng = None, None
        try:
            if geom_type == "Point":
                lng, lat = float(coords[0]), float(coords[1])
            elif geom_type in ("Polygon", "MultiPolygon"):
                ring = coords[0][0] if geom_type == "MultiPolygon" else coords[0]
                lng, lat = float(ring[0][0]), float(ring[0][1])
        except (IndexError, TypeError, ValueError):
            pass
        if not record_in_scope(lat=lat, lng=lng, row_neighborhood=barrio, row_commune=props.get("comuna") or props.get("COMUNA"),
                               scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
            continue

        area = props.get("area") or props.get("AREA")
        clasificacion = (props.get("clasificac") or props.get("CLASIFICAC") or
                         props.get("tipo") or props.get("TIPO") or "").lower()

        entity_id = await get_or_create_entity(
            conn, name=name, entity_type="Facility",
            subtype=clasificacion or "espacio_verde",
            lat=lat, lng=lng,
            description=f"{clasificacion.title() or 'Espacio verde'} en CABA",
            origin_url=ESPACIOS_URL,
            all_names=[name.upper()]
        )

        if area:
            await upsert_property(conn, entity_id, "area_m2", str(round(float(area), 2)),
                                   "number", source_id, origins=[ESPACIOS_URL])
        await upsert_property(conn, entity_id, "barrio", barrio.title(),
                               "string", source_id, origins=[ESPACIOS_URL])
        await upsert_property(conn, entity_id, "is_free", "true",
                               "boolean", source_id, origins=[ESPACIOS_URL])
        count += 1

    print(f"  OK {count} espacios verdes de {args.scope} procesados")


async def main():
    parser = argparse.ArgumentParser()
    add_source_arguments(parser)
    args = parser.parse_args()
    print("=== Scraper BA Data GCBA ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        if not args.write:
            print("Validación completada; usar --write para persistir.")
            return
        await scrape_barrios(conn, source_id, args)
        await scrape_subte(conn, source_id, args)
        await scrape_espacios_verdes(conn, source_id, args)
        await mark_source_synced(conn, source_id)
        print("\nOK Scraper finalizado exitosamente")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
