"""Ingesta histórica de IGJ para sociedades con algún domicilio en Palermo.

Descubre todos los ZIP semestrales del catálogo oficial, conserva cada observación
mensual y sólo incorpora domicilios contenidos por el polígono oficial GCBA.
"""
import argparse
import asyncio
import csv
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx

from scrapers.shared.db_helpers import (
    ensure_source, finish_sync_run, get_conn, get_or_create_entity,
    mark_source_synced, start_sync_run, upsert_property,
)
from scrapers.shared.normalizer import clean_cuit, normalize_name, normalize_value
from scrapers.shared.usig import geocode_address

CKAN_PACKAGE = "https://datos.jus.gob.ar/api/3/action/package_show?id=da045e06-35cb-4bdd-9b5e-ddee6712c86c"
BARRIOS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/barrios/barrios.geojson"
CACHE_DIR = Path("scrapers/.cache/igj")


def value(row: dict, *keys: str) -> str:
    """Lee columnas con diferencias menores entre los CSV históricos."""
    normalized = {str(k).lower().strip(): v for k, v in row.items()}
    for key in keys:
        item = normalized.get(key.lower())
        if item not in (None, ""):
            return str(item).strip()
    return ""


def period_from_name(name: str) -> str:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", name)
    return match.group(1) + "-" + match.group(2) if match else "unknown"


def subtype_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_value(text).lower()).strip("_") or "other"


def resource_order(resource: dict) -> tuple[int, int, str]:
    text = " ".join(str(resource.get(k, "")) for k in ("name", "description", "url"))
    year = re.search(r"(20\d{2})", text)
    semester = re.search(r"semestre\s*(\d)", text, re.I)
    return (int(year.group(1)) if year else 0, int(semester.group(1)) if semester else 0, text)


def polygon_contains(point: tuple[float, float], geometry: dict) -> bool:
    """Ray casting, sin dependencia GIS adicional. point es (lng, lat)."""
    x, y = point

    def ring_contains(ring):
        inside = False
        for index, current in enumerate(ring):
            previous = ring[index - 1]
            x1, y1 = previous[0], previous[1]
            x2, y2 = current[0], current[1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        return inside

    kind = geometry.get("type")
    polygons = [geometry.get("coordinates", [])] if kind == "Polygon" else geometry.get("coordinates", [])
    for polygon in polygons:
        if polygon and ring_contains(polygon[0]) and not any(ring_contains(hole) for hole in polygon[1:]):
            return True
    return False


class GeocodeCache:
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(CACHE_DIR / "geocodes.sqlite3")
        self.db.execute("""CREATE TABLE IF NOT EXISTS geocodes (
            address TEXT PRIMARY KEY, lat REAL, lng REAL, backend TEXT, resolved INTEGER NOT NULL)""")

    def get(self, address: str):
        row = self.db.execute("SELECT lat,lng,backend,resolved FROM geocodes WHERE address=?", (address,)).fetchone()
        return row if row else None

    def put(self, address: str, result):
        if result:
            self.db.execute("INSERT OR REPLACE INTO geocodes VALUES (?,?,?,?,1)", (address, result.lat, result.lng, result.backend))
        else:
            self.db.execute("INSERT OR REPLACE INTO geocodes VALUES (?,?,?,?,0)", (address, None, None, None))
        self.db.commit()

    def close(self):
        self.db.close()


async def get_palermo_polygon(client: httpx.AsyncClient) -> dict:
    response = await client.get(BARRIOS_URL)
    response.raise_for_status()
    for feature in response.json().get("features", []):
        props = feature.get("properties", {})
        if value(props, "barrio", "BARRIO", "nombre", "NOMBRE").upper() == "PALERMO":
            return feature["geometry"]
    raise RuntimeError("El GeoJSON GCBA no contiene el polígono de Palermo")


async def discover_resources(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(CKAN_PACKAGE)
    response.raise_for_status()
    resources = response.json()["result"].get("resources", [])
    selected = [r for r in resources if "semestre" in str(r.get("name", "")).lower() and str(r.get("url", "")).lower().endswith(".zip")]
    return sorted(selected, key=resource_order)


async def download_resource(client: httpx.AsyncClient, resource: dict) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{resource.get('id', hashlib.sha256(resource['url'].encode()).hexdigest())}.zip"
    if path.exists() and path.stat().st_size:
        return path
    async with client.stream("GET", resource["url"]) as response:
        response.raise_for_status()
        with path.open("wb") as handle:
            async for chunk in response.aiter_bytes():
                handle.write(chunk)
    return path


def csv_rows(archive: zipfile.ZipFile, filename: str):
    with archive.open(filename) as binary:
        yield from csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline=""))


def record_payload(row: dict) -> dict:
    return {str(k).strip().lower(): str(v).strip() for k, v in row.items() if v not in (None, "")}


def event_date(row: dict) -> str | None:
    raw = value(row, "fecha", "fecha_asamblea", "fecha_presentacion", "fecha_balance")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


async def insert_record(conn, entity_id: str, source_id: str, record_type: str, period: str, payload: dict, origin: str):
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(f"{entity_id}|{record_type}|{period}|{canonical}".encode()).hexdigest()
    await conn.execute(
        """INSERT INTO legal_entity_records
           (id,entity_id,source_id,record_type,record_key,observed_period,event_date,payload,origins)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
           ON DUPLICATE KEY UPDATE last_seen_at=CURRENT_TIMESTAMP""",
        str(uuid4()), entity_id, source_id, record_type, key, period, event_date(payload), canonical, json.dumps([origin]),
    )


async def resolve_address(client, cache, address: str, semaphore: asyncio.Semaphore):
    cached = cache.get(address)
    if cached:
        lat, lng, backend, resolved = cached
        return (lat, lng, backend) if resolved else None
    async with semaphore:
        result = await geocode_address(client, address)
    cache.put(address, result)
    return (result.lat, result.lng, result.backend) if result else None


async def process_period(conn, client, cache, polygon, source_id: str, resource: dict, path: Path, semaphore) -> tuple[int, int]:
    seen = written = 0
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        domicile_files = sorted(name for name in names if "domicilios" in name.lower() and name.lower().endswith(".csv"))
        for domicile_file in domicile_files:
            period = period_from_name(domicile_file)
            entity_file = domicile_file.lower().replace("domicilios", "entidades")
            entity_name = next((name for name in names if name.lower() == entity_file), None)
            if not entity_name:
                continue
            entities = {value(row, "numero_correlativo"): row for row in csv_rows(archive, entity_name) if value(row, "numero_correlativo")}
            for domicile in csv_rows(archive, domicile_file):
                external_id = value(domicile, "numero_correlativo")
                entity = entities.get(external_id)
                if not entity:
                    continue
                street, number = value(domicile, "calle"), value(domicile, "numero")
                address = " ".join(part for part in (street, number) if part)
                if not address:
                    continue
                seen += 1
                location = await resolve_address(client, cache, address, semaphore)
                if not location or not polygon_contains((location[1], location[0]), polygon):
                    continue
                name = normalize_name(value(entity, "razon_social"))
                if not name:
                    continue
                lat, lng, backend = location
                entity_id = await get_or_create_entity(conn, name, "LegalEntity", subtype=subtype_name(value(entity, "descripcion_tipo_societario")), lat=lat, lng=lng, origin_url=resource["url"], source_id=source_id, external_id=external_id)
                observed_date = f"{period}-01" if period != "unknown" else None
                estado = "Baja" if value(entity, "dada_de_baja") else "Activa"
                for key, raw in (("cuit", clean_cuit(value(entity, "cuit"))), ("legal_status", estado), ("company_type", normalize_value(value(entity, "descripcion_tipo_societario"))), ("closure_reason", normalize_value(value(entity, "detalle_baja"))), ("legal_address", address)):
                    if raw:
                        await upsert_property(conn, entity_id, key, raw, "string", source_id, [resource["url"]], .5, observed_date)
                payload = record_payload(domicile)
                payload.update({"address": address, "lat": lat, "lng": lng, "geocoder": backend})
                await insert_record(conn, entity_id, source_id, "domicile", period, payload, resource["url"])
                written += 1
    return seen, written


async def process_all_domicile_records(conn, client, cache, source_id: str, resource: dict, path: Path, semaphore) -> int:
    """Conserva incluso las mudanzas fuera de Palermo de entidades ya elegibles."""
    rows = await conn.fetch("SELECT external_id, entity_id FROM external_ids WHERE source_id=$1", source_id)
    entity_ids = {str(row["external_id"]): str(row["entity_id"]) for row in rows}
    written = 0
    with zipfile.ZipFile(path) as archive:
        for filename in archive.namelist():
            if "domicilios" not in filename.lower() or not filename.lower().endswith(".csv"):
                continue
            period = period_from_name(filename)
            for domicile in csv_rows(archive, filename):
                entity_id = entity_ids.get(value(domicile, "numero_correlativo"))
                street, number = value(domicile, "calle"), value(domicile, "numero")
                address = " ".join(part for part in (street, number) if part)
                if not entity_id or not address:
                    continue
                location = await resolve_address(client, cache, address, semaphore)
                payload = record_payload(domicile)
                payload["address"] = address
                if location:
                    payload.update({"lat": location[0], "lng": location[1], "geocoder": location[2]})
                await insert_record(conn, entity_id, source_id, "domicile", period, payload, resource["url"])
                written += 1
    return written


async def process_legal_records(conn, source_id: str, resource: dict, path: Path) -> int:
    """Segunda pasada: agrega hechos de toda la historia de entidades ya elegibles."""
    rows = await conn.fetch("SELECT external_id, entity_id FROM external_ids WHERE source_id=$1", source_id)
    entity_ids = {str(row["external_id"]): str(row["entity_id"]) for row in rows}
    written = 0
    with zipfile.ZipFile(path) as archive:
        for filename in archive.namelist():
            lower = filename.lower()
            record_type = next((kind for marker, kind in (("autoridades", "authority"), ("asambleas", "assembly"), ("balances", "balance")) if marker in lower), None)
            if not record_type or not lower.endswith(".csv"):
                continue
            period = period_from_name(filename)
            for row in csv_rows(archive, filename):
                entity_id = entity_ids.get(value(row, "numero_correlativo"))
                if entity_id:
                    await insert_record(conn, entity_id, source_id, record_type, period, record_payload(row), resource["url"])
                    written += 1
    return written


async def main(args):
    conn = await get_conn()
    run_id = None
    cache = GeocodeCache()
    try:
        source_id = await ensure_source(conn, "igj", "https://datos.jus.gob.ar", 1)
        run_id = await start_sync_run(conn, source_id)
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            polygon = await get_palermo_polygon(client)
            resources = await discover_resources(client)
            if args.limit_resources:
                resources = resources[:args.limit_resources]
            if not resources:
                raise RuntimeError("No se encontraron ZIPs semestrales de IGJ")
            print(f"IGJ histórico: {len(resources)} recursos oficiales")
            semaphore = asyncio.Semaphore(args.geocode_concurrency)
            seen = written = 0
            downloads = []
            for resource in resources:
                print(f"-> {resource.get('name')}")
                path = await download_resource(client, resource)
                downloads.append((resource, path))
                current_seen, current_written = await process_period(conn, client, cache, polygon, source_id, resource, path, semaphore)
                seen += current_seen; written += current_written
                print(f"   domicilios revisados={current_seen}, hechos escritos={current_written}")
            for resource, path in downloads:
                domicile_written = await process_all_domicile_records(conn, client, cache, source_id, resource, path, semaphore)
                written += domicile_written
                records_written = await process_legal_records(conn, source_id, resource, path)
                written += records_written
                print(f"   domicilios históricos={domicile_written}, hechos legales {resource.get('name')}={records_written}")
        await finish_sync_run(conn, run_id, "completed", seen, written)
        await mark_source_synced(conn, source_id)
    except Exception as exc:
        if run_id:
            await finish_sync_run(conn, run_id, "failed", error_message=str(exc)[:4000])
        raise
    finally:
        cache.close()
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-resources", type=int, help="Útil para una prueba acotada; omitir para toda la historia")
    parser.add_argument("--geocode-concurrency", type=int, default=6)
    asyncio.run(main(parser.parse_args()))
