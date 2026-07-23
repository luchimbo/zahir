"""Geocodifica entidades canonicas activas sin coordenadas que tienen direccion.

Usa USIG (preferido en CABA) con fallback a GeorefAR filtrando por provincia CABA.
Solo persiste resultados dentro del bounding box de Palermo. Dry-run por defecto.
"""
import argparse
import asyncio
import re

import httpx
from scrapers.shared.db_helpers import ensure_source, get_conn, mark_source_synced, upsert_property
from scrapers.shared.usig import geocode_address as usig_geocode

LAT_MIN, LAT_MAX = -34.6020, -34.5620
LNG_MIN, LNG_MAX = -58.4620, -58.3840
GEOREF_URL = "https://apis.datos.gob.ar/georef/api/v2.0/direcciones"
CONCURRENCY = 4

CANDIDATES_SQL = """
SELECT e.id, e.name, e.entity_type, pa.value AS address
FROM entities e
JOIN active_properties pa ON pa.entity_id = e.id AND pa.key = 'address'
WHERE e.canonical_id IS NULL AND e.is_active
  AND (e.lat IS NULL OR e.lng IS NULL)
  AND e.entity_type IN ('Organization', 'Facility', 'Transport')
  AND ($1 IS NULL OR e.id > $1)
ORDER BY e.id
"""


def clean_address(raw: str) -> str:
    """Simplifica direcciones compuestas a 'Calle altura' cuando es posible."""
    addr = re.sub(r"\(.*?\)", "", raw)
    addr = addr.split(" - ")[0]
    addr = re.sub(r"/\d+$", "", addr)
    addr = re.sub(r"\s{2,}", " ", addr).strip(" ,.-")
    return addr


def in_palermo(lat: float, lng: float) -> bool:
    return LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


async def georef_geocode(client: httpx.AsyncClient, address: str):
    response = await client.get(
        GEOREF_URL,
        params={
            "direccion": f"{address}, CABA",
            "provincia": "Ciudad Autonoma de Buenos Aires",
            "max": 1,
        },
    )
    if response.status_code != 200:
        return None
    rows = response.json().get("direcciones") or []
    if not rows:
        return None
    point = rows[0].get("ubicacion") or {}
    try:
        return float(point["lat"]), float(point["lon"])
    except (KeyError, TypeError, ValueError):
        return None


async def resolve(client: httpx.AsyncClient, addresses: list[str]):
    """Devuelve (lat, lng, backend) o None. Prueba cada direccion candidata."""
    for raw in addresses:
        address = clean_address(raw)
        if not address:
            continue
        try:
            result = await usig_geocode(client, address)
        except httpx.HTTPError:
            result = None
        if result and in_palermo(result.lat, result.lng):
            return result.lat, result.lng, result.backend
        try:
            fallback = await georef_geocode(client, address)
        except httpx.HTTPError:
            fallback = None
        if fallback and in_palermo(*fallback):
            return fallback[0], fallback[1], "georef"
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Persistir coordenadas; por defecto dry-run.")
    parser.add_argument("--limit", type=int, default=0, help="Procesar como maximo N entidades.")
    parser.add_argument(
        "--after-id", default=None,
        help="Reanudar despues de este UUID, respetando el orden estable de entidades.",
    )
    args = parser.parse_args()

    conn = await get_conn()

    # DB-API no reutiliza el mismo placeholder: $1 aparece dos veces en el SQL.
    rows = await conn.fetch(CANDIDATES_SQL, args.after_id, args.after_id)
    by_entity: dict[str, dict] = {}
    for row in rows:
        entry = by_entity.setdefault(
            str(row["id"]),
            {"name": row["name"], "type": row["entity_type"], "addresses": []},
        )
        if row["address"] not in entry["addresses"]:
            entry["addresses"].append(row["address"])

    entities = list(by_entity.items())
    if args.limit:
        entities = entities[: args.limit]
    print(f"Entidades candidatas: {len(entities)} | write={args.write} | after_id={args.after_id}")

    stats = {"geocoded": 0, "unresolved": 0, "done": 0}
    semaphore = asyncio.Semaphore(CONCURRENCY)
    resolved: list[tuple[str, float, float, str]] = []

    async with httpx.AsyncClient(timeout=20) as client:
        async def worker(entity_id: str, info: dict):
            async with semaphore:
                result = await resolve(client, info["addresses"])
            if result:
                resolved.append((entity_id, *result))
            else:
                stats["unresolved"] += 1
            stats["done"] += 1
            if stats["done"] % 200 == 0:
                print(f"  progreso: {stats['done']}/{len(entities)}")

        await asyncio.gather(*(worker(eid, info) for eid, info in entities))

    stats["geocoded"] = len(resolved)
    by_backend = {}
    for _, _, _, backend in resolved:
        by_backend[backend] = by_backend.get(backend, 0) + 1
    print(f"Resueltas: {stats['geocoded']} ({by_backend}) | sin resolver: {stats['unresolved']}")
    if entities:
        print(f"Cursor siguiente: {entities[-1][0]}")

    if not args.write:
        for entity_id, lat, lng, backend in resolved[:10]:
            print(f"  [{backend}] {by_entity[entity_id]['name'][:40]:42s} {lat:.6f},{lng:.6f}")
        await conn.close()
        return

    usig_source_id = await ensure_source(conn, "usig", "http://ws.usig.buenosaires.gob.ar/", 1)
    georef_source_id = await ensure_source(conn, "georef", "https://apis.datos.gob.ar/georef/api/v2.0", 1)

    for entity_id, lat, lng, backend in resolved:
        await conn.execute(
            "UPDATE entities SET lat = $1, lng = $2, updated_at = now() WHERE id = $3",
            lat, lng, entity_id,
        )
        await upsert_property(
            conn, entity_id, "geocode_source", backend, "string",
            usig_source_id if backend == "usig" else georef_source_id,
            origins=["http://ws.usig.buenosaires.gob.ar/" if backend == "usig" else "https://apis.datos.gob.ar/georef/api/v2.0"],
            confidence=0.5,
        )
    used_backends = {backend for _, _, _, backend in resolved}
    if "usig" in used_backends:
        await mark_source_synced(conn, usig_source_id)
    if "georef" in used_backends:
        await mark_source_synced(conn, georef_source_id)
    print(f"Persistidas {len(resolved)} entidades geocodificadas")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
