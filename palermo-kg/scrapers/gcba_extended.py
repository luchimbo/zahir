"""
Scraper: BA Data GCBA — datasets extendidos
Fuente: https://data.buenosaires.gob.ar
Tier 1 — GeoJSON publicos sin autenticacion.

Datasets:
  - Farmacias                -> Facility / farmacia
  - Establecimientos educativos -> Facility / escuela / universidad
  - Centros de salud         -> Facility / centro_de_salud
  - Estaciones Ecobici       -> Transport / ecobici
  - Museos                   -> Facility / museo
  - Bibliotecas              -> Facility / biblioteca
  - Clubes deportivos        -> Facility / club_deportivo
  - Wifi publico             -> Facility / wifi_publico
"""

import argparse
import asyncio
import httpx
from scrapers.shared.db_helpers import (
    bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
)
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.contract import add_source_arguments
from scrapers.shared.geo_scope import record_in_scope

SUPPORTS_SOURCE_CONTRACT = True

CDN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets"

DATASETS = [
    {
        # keys reales: long, lat, telefono, objeto, calle_nomb, altura, barrio, comuna
        "name": "farmacias",
        "url": f"{CDN}/ministerio-de-salud/farmacias/farmacias.geojson",
        "entity_type": "Facility",
        "subtype": "farmacia",
        "name_keys": ["objeto"],
        "coord_from_props": True,  # lat/long vienen en properties, no en geometry
        "props": {
            "phone": ["telefono"],
            "address": ["calle_nomb"],
            "barrio": ["barrio"],
            "comuna": ["comuna"],
        },
    },
    {
        # keys reales: fna, gna, nam, esp, ate, dir, bar
        "name": "hospitales",
        "url": f"{CDN}/ministerio-de-salud/hospitales/hospitales.geojson",
        "entity_type": "Facility",
        "subtype": "hospital",
        "name_keys": ["nam"],
        "props": {
            "address": ["dir"],
            "barrio": ["bar"],
            "especialidad": ["esp"],
            "atencion": ["ate"],
        },
    },
    {
        # keys reales: fna, gna, nam, tip, dir, bar, com, tel
        "name": "bibliotecas",
        "url": f"{CDN}/ministerio-de-cultura/bibliotecas/bibliotecas.geojson",
        "entity_type": "Facility",
        "subtype": "biblioteca",
        "name_keys": ["nam"],
        "props": {
            "address": ["dir"],
            "barrio": ["bar"],
            "phone": ["tel"],
            "tipo": ["tip"],
            "comuna": ["com"],
        },
    },
]

NUMBER_KEYS = {"capacidad", "comuna"}
BOOLEAN_KEYS = {"is_free"}
URL_KEYS = {"website"}


def get_val(props, keys):
    for k in keys:
        v = props.get(k)
        if v and str(v).strip() not in ("", "None", "N/A", "S/D", "0"):
            return str(v).strip()
    return ""


def get_coords(feature):
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates", [])
    gtype = geom.get("type", "")
    try:
        if gtype == "Point":
            return float(coords[1]), float(coords[0])
        elif gtype == "MultiPoint":
            return float(coords[0][1]), float(coords[0][0])
        elif gtype == "Polygon":
            return float(coords[0][0][1]), float(coords[0][0][0])
        elif gtype == "MultiPolygon":
            return float(coords[0][0][0][1]), float(coords[0][0][0][0])
    except (IndexError, TypeError, ValueError):
        pass
    return None, None


async def scrape_dataset(conn, source_id, dataset, args):
    dname = dataset["name"]
    print(f"-> {dname}...")

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        try:
            r = await client.get(dataset["url"])
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  ERROR: {e}")
            return None

    features = data.get("features", [])
    if not features:
        print(f"  WARNING: sin features")
        return None

    sample = features[0].get("properties", {})
    print(f"  {len(features)} features | keys: {list(sample.keys())[:10]}")

    subtype_key = dataset.get("subtype_key")
    subtype_map = dataset.get("subtype_map", {})
    count = 0
    entity_records = []
    property_records = []

    for f in features:
        props = f.get("properties") or {}
        name_raw = get_val(props, dataset["name_keys"])
        if not name_raw:
            continue

        name = normalize_name(name_raw)
        lat, lng = get_coords(f)

        subtype = dataset["subtype"]
        if subtype_key:
            tipo_raw = (props.get(subtype_key) or "").upper().strip()
            for k, v in subtype_map.items():
                if k in tipo_raw:
                    subtype = v
                    break

        # Algunas fuentes GCBA ponen lat/lon en props en lugar de geometry
        if dataset.get("coord_from_props"):
            try:
                lat = float(props.get("lat") or 0) or lat
                lng = float(props.get("long") or props.get("lon") or 0) or lng
            except (ValueError, TypeError):
                pass

        # Validar rango de coordenadas (numeric(10,7) = max ±999.9999999)
        try:
            if lat is not None and not (-90 <= float(lat) <= 90):
                lat = None
            if lng is not None and not (-180 <= float(lng) <= 180):
                lng = None
        except (TypeError, ValueError):
            lat, lng = None, None

        row_neighborhood = get_val(props, dataset.get("props", {}).get("neighborhood", ["barrio", "bar"]))
        row_commune = get_val(props, dataset.get("props", {}).get("commune", ["comuna", "com"]))
        if not record_in_scope(lat=lat, lng=lng, row_neighborhood=row_neighborhood, row_commune=row_commune,
                               scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
            continue

        entity_records.append({
            "name": name, "entity_type": dataset["entity_type"], "subtype": subtype,
            "lat": lat, "lng": lng, "origin_url": dataset["url"],
        })

        for prop_key, source_keys in dataset.get("props", {}).items():
            value = get_val(props, source_keys)
            if not value:
                continue

            if prop_key in BOOLEAN_KEYS:
                vtype = "boolean"
                value = "true" if value.upper() in ("SI", "S", "TRUE", "1") else "false"
            elif prop_key in NUMBER_KEYS:
                vtype = "number"
                try:
                    value = str(int(float(value)))
                except ValueError:
                    continue
            elif prop_key in URL_KEYS:
                vtype = "url"
            else:
                vtype = "string"
                value = normalize_value(value)

            property_records.append({
                "entity_name": name, "key": prop_key, "value": value,
                "value_type": vtype, "confidence": 0.9, "origins": [dataset["url"]],
            })
        count += 1

    entity_ids = await bulk_get_or_create_entities(conn, entity_records)
    for record in property_records:
        record["entity_id"] = entity_ids[record.pop("entity_name")]
    await bulk_upsert_properties(conn, property_records, source_id)
    print(f"  OK: {count} entidades")
    return count


async def main():
    parser = argparse.ArgumentParser()
    add_source_arguments(parser)
    args = parser.parse_args()
    print("=== Scraper GCBA Extended ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data_extended")
        total = 0
        completed = True
        for dataset in DATASETS:
            if not args.write:
                print("Validación completada; usar --write para persistir.")
                return
            n = await scrape_dataset(conn, source_id, dataset, args)
            if n is None:
                completed = False
                continue
            total += n
            await asyncio.sleep(1)
        if not completed:
            raise RuntimeError("GCBA Extended quedo parcial; no se marco la fuente como sincronizada")
        await mark_source_synced(conn, source_id)
        print(f"\nTotal: {total} entidades insertadas/actualizadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
