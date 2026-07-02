"""
Scraper: BA Data GCBA — datasets CSV
Datasets:
  - Ecobici estaciones   -> Transport / ecobici
  - Cajeros automaticos  -> Facility / cajero_atm
  - Comisarias           -> Facility / comisaria
  - Colectivos paradas   -> Transport / parada_colectivo  (GeoJSON)
"""

import asyncio
import csv
import io
import httpx
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id
)
from scrapers.shared.normalizer import normalize_name, normalize_value

CDN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets"

# Palermo bounding box para filtrar
LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390


def in_palermo(lat, lng):
    try:
        return LAT_MIN <= float(lat) <= LAT_MAX and LNG_MIN <= float(lng) <= LNG_MAX
    except (TypeError, ValueError):
        return False


async def fetch_text(url):
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


async def fetch_json(url):
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def parse_csv(text):
    text = text.lstrip("﻿")  # strip BOM
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


async def scrape_ecobici(conn, source_id):
    url = f"{CDN}/transporte-y-obras-publicas/estaciones-bicicletas-publicas/nuevas-estaciones-bicicletas-publicas.csv"
    print("-> ecobici...")
    rows = parse_csv(await fetch_text(url))
    count = 0
    for row in rows:
        lat, lng = row.get("latitud", ""), row.get("longitud", "")
        if not in_palermo(lat, lng):
            continue
        nombre = normalize_name(row.get("nombre", ""))
        if not nombre:
            continue
        eid = await get_or_create_entity(conn, name=f"Ecobici {nombre}",
                                          entity_type="Transport", subtype="ecobici",
                                          lat=float(lat), lng=float(lng))
        for k, v, t in [
            ("address", row.get("direccion", ""), "string"),
            ("barrio", row.get("barrio", ""), "string"),
            ("comuna", row.get("comuna", ""), "string"),
            ("id_estacion", row.get("numero_de_estacion", ""), "string"),
        ]:
            if v:
                await upsert_property(conn, eid, k, normalize_value(v) if t == "string" else v,
                                      t, source_id, confidence=0.95)
        count += 1
    print(f"  OK: {count} estaciones ecobici en Palermo")
    return count


async def scrape_cajeros(conn, source_id):
    url = f"{CDN}/secretaria-de-desarrollo-urbano/cajeros-automaticos/cajeros-automaticos.csv"
    print("-> cajeros ATM...")
    rows = parse_csv(await fetch_text(url))
    count = 0
    for row in rows:
        lat, lng = row.get("lat", ""), row.get("long", "")
        if not in_palermo(lat, lng):
            continue
        banco = normalize_name(row.get("banco", "ATM"))
        red = row.get("red", "")
        nombre = f"ATM {banco}" + (f" ({red})" if red else "")
        eid = await get_or_create_entity(conn, name=nombre,
                                          entity_type="Facility", subtype="cajero_atm",
                                          lat=float(lat), lng=float(lng))
        calle = row.get("calle", "")
        altura = row.get("altura", "")
        address = f"{calle} {altura}".strip() if calle else ""
        for k, v, t in [
            ("address", address, "string"),
            ("barrio", row.get("barrio", ""), "string"),
            ("banco", banco, "string"),
            ("red_cajero", red, "string"),
            ("acepta_dolares", "true" if row.get("dolares", "").lower() == "true" else "false", "boolean"),
        ]:
            if v:
                await upsert_property(conn, eid, k, v, t, source_id, confidence=0.95)
        count += 1
    print(f"  OK: {count} cajeros ATM en Palermo")
    return count


async def scrape_comisarias(conn, source_id):
    url = f"{CDN}/ministerio-de-justicia-y-seguridad/divisiones-comisarias-vecinales/divisiones-comisarias-vecinales.csv"
    print("-> comisarias...")
    rows = parse_csv(await fetch_text(url))
    count = 0
    for row in rows:
        nombre = normalize_name(row.get("nombre", ""))
        if not nombre:
            continue
        eid = await get_or_create_entity(conn, name=nombre,
                                          entity_type="Facility", subtype="comisaria",
                                          lat=None, lng=None)
        for k, v, t in [
            ("comuna", row.get("comuna", ""), "string"),
            ("division", row.get("division", ""), "string"),
            ("departamento", row.get("departamen", ""), "string"),
        ]:
            if v:
                await upsert_property(conn, eid, k, v, t, source_id, confidence=0.9)
        count += 1
    print(f"  OK: {count} comisarias")
    return count


async def scrape_colectivos(conn, source_id):
    url = f"{CDN}/transporte-y-obras-publicas/colectivos/paradas-de-colectivo.geojson"
    print("-> paradas colectivo...")
    data = await fetch_json(url)
    features = data.get("features", [])
    count = 0
    for f in features:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates", [])
        if not coords or len(coords) < 2:
            continue
        try:
            lng, lat = float(coords[0]), float(coords[1])
        except (ValueError, TypeError):
            continue
        if not in_palermo(lat, lng):
            continue

        stop_name = props.get("stop_name", "")
        route = props.get("route_short_name", "")
        nombre = normalize_name(f"Parada {route} - {stop_name}" if route else f"Parada {stop_name}")
        if not nombre or nombre == "Parada  - ":
            continue

        eid = await get_or_create_entity(conn, name=nombre,
                                          entity_type="Transport", subtype="parada_colectivo",
                                          lat=lat, lng=lng)
        for k, v, t in [
            ("stop_id", props.get("stop_id", ""), "string"),
            ("linea", route, "string"),
            ("ramal", props.get("route_long_name", ""), "string"),
        ]:
            if v:
                await upsert_property(conn, eid, k, v, t, source_id, confidence=0.95)
        count += 1
        if count % 500 == 0:
            print(f"  {count} paradas...")

    print(f"  OK: {count} paradas de colectivo en Palermo")
    return count


async def main():
    print("=== Scraper GCBA CSV ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "ba_data")
        total = 0
        for fn in [scrape_ecobici, scrape_cajeros, scrape_comisarias, scrape_colectivos]:
            total += await fn(conn, source_id)
            await asyncio.sleep(1)
        print(f"\nTotal: {total} entidades")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
