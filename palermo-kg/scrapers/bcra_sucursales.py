"""
Scraper: Cajeros ATM y sucursales bancarias en CABA
Fuentes:
  - BA Data GCBA (cajeros con geolocacion, CSV)
  - OSM complementa con bancos (via osm_palermo.py)
Tier 1 — sin autenticacion.
"""

import asyncio
import csv
import io
import httpx
from scrapers.shared.db_helpers import (
    ensure_source, get_conn, get_or_create_entity, mark_source_synced, upsert_property,
    bulk_get_or_create_entities, bulk_upsert_properties,
)
from scrapers.shared.normalizer import normalize_name, normalize_value

# BA Data GCBA — dataset de cajeros en CABA (CSV)
GCBA_CAJEROS_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "secretaria-de-desarrollo-urbano/cajeros-automaticos/"
    "cajeros-automaticos.csv"
)

LAT_MIN, LAT_MAX = -34.615, -34.555
LNG_MIN, LNG_MAX = -58.455, -58.390


def clean(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def parse_float(value):
    value = clean(value).replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def valid_lat_lng(lat, lng) -> bool:
    return (
        lat is not None
        and lng is not None
        and LAT_MIN <= lat <= LAT_MAX
        and LNG_MIN <= lng <= LNG_MAX
    )


def build_address(row: dict) -> str:
    parts = [clean(row.get("calle")), clean(row.get("altura"))]
    return " ".join(p for p in parts if p).strip()


async def scrape_cajeros_gcba(conn, source_id: str):
    print("-> Descargando cajeros ATM desde BA Data GCBA...")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        try:
            r = await client.get(GCBA_CAJEROS_URL)
            r.raise_for_status()
            text = r.content.decode("utf-8-sig", "replace")
            rows = list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"  WARNING: {e}")
            print("  -> Dataset de cajeros no disponible en GCBA, saltando.")
            return

    print(f"  {len(rows)} cajeros en el dataset")

    candidates = []
    for row in rows:
        lat = parse_float(row.get("lat"))
        lng = parse_float(row.get("long"))
        if not valid_lat_lng(lat, lng):
            continue

        banco = clean(row.get("banco") or row.get("BANCO") or row.get("ENTIDAD") or "")
        red = clean(row.get("red") or row.get("RED") or "")
        if not banco and not red:
            continue

        label = f"Cajero {banco} {red}".strip() if red else f"Cajero {banco}"
        direccion = clean(
            row.get("ubicacion") or row.get("DOMICILIO") or row.get("DIRECCION") or build_address(row)
        )
        # Cada cajero es una entidad fisica distinta; incluimos direccion/coordenadas en el nombre
        name = normalize_name(f"{label} - {direccion}" if direccion else f"{label} - {lat},{lng}")
        barrio = clean(row.get("barrio") or row.get("BARRIO") or "")
        comuna = clean(row.get("comuna") or row.get("COMUNA") or "")
        calle2 = clean(row.get("calle2") or "")
        terminales = clean(row.get("terminales") or "")
        no_vidente = clean(row.get("no_vidente") or "")
        dolares = clean(row.get("dolares") or "")

        candidates.append({
            "name": name,
            "entity_type": "Facility",
            "subtype": "cajero_atm",
            "lat": lat,
            "lng": lng,
            "origin_url": GCBA_CAJEROS_URL,
            "props": {
                "address": (direccion, "string"),
                "banco_nombre": (normalize_value(banco) if banco else "", "string"),
                "red_cajero": (normalize_value(red) if red else "", "string"),
                "neighborhood": (barrio, "string"),
                "commune": (comuna, "string"),
                "street_corner": (calle2, "string"),
                "atm_terminals": (terminales, "number"),
                "atm_accesible": (
                    "true" if no_vidente.lower() in ("true", "1", "si") else "false",
                    "boolean"
                ),
                "atm_usd": (
                    "true" if dolares.lower() in ("true", "1", "si") else "false",
                    "boolean"
                ),
            },
        })

    print(f"  {len(candidates)} cajeros en Palermo")

    entity_records = [
        {
            "name": c["name"],
            "entity_type": c["entity_type"],
            "subtype": c["subtype"],
            "lat": c["lat"],
            "lng": c["lng"],
            "origin_url": c["origin_url"],
        }
        for c in candidates
    ]
    ids_by_name = await bulk_get_or_create_entities(conn, entity_records)

    prop_records = []
    for c in candidates:
        entity_id = ids_by_name.get(c["name"])
        if not entity_id:
            continue
        for key, (value, vtype) in c["props"].items():
            if not value:
                continue
            if vtype == "number":
                try:
                    value = str(int(float(value)))
                except ValueError:
                    continue
            prop_records.append({
                "entity_id": entity_id,
                "key": key,
                "value": value,
                "value_type": vtype,
                "confidence": 0.9,
                "origins": [GCBA_CAJEROS_URL],
            })

    await bulk_upsert_properties(conn, prop_records, source_id)
    print(f"  OK cajeros ATM GCBA: {len(candidates)} insertados/actualizados")


async def register_redes_cajeros(conn, source_id: str):
    """Registra las redes de cajeros como entidades propias."""
    redes = [
        ("Red Link", "https://www.redlink.com.ar"),
        ("Red Banelco", "https://www.banelco.com.ar"),
    ]
    for nombre, url in redes:
        entity_id = await get_or_create_entity(
            conn,
            name=nombre,
            entity_type="Facility",
            subtype="red_cajeros",
            origin_url=url,
        )
        await upsert_property(conn, entity_id, "website", url, "url",
                              source_id, confidence=1.0)
    print("  OK redes de cajeros registradas (Link, Banelco)")


async def main():
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, "bcra", GCBA_CAJEROS_URL, 1)
        await scrape_cajeros_gcba(conn, source_id)
        await register_redes_cajeros(conn, source_id)
        await mark_source_synced(conn, source_id)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
