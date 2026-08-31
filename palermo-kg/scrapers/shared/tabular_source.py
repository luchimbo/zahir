"""Adaptador conservador para datasets oficiales CSV/JSON/GeoJSON.

No adivina campos: sólo ingesta nombres y propiedades que estén presentes, y
conserva la URL del dataset como origen de cada valor.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import httpx

from geography_catalog import resolve_commune, resolve_neighborhood
from scrapers.shared.contract import SourceResult, bounded
from scrapers.shared.db_helpers import (
    bulk_get_or_create_entities, bulk_upsert_properties, ensure_source,
    get_conn, mark_source_synced,
)
from scrapers.shared.normalizer import normalize_name, normalize_value

PALERMO_BBOX = (-34.615, -34.555, -58.455, -58.390)
NAME_KEYS = ("name", "nombre", "titulo", "title", "establecimiento", "denominacion")
LAT_KEYS = ("lat", "latitud", "latitude", "y")
LNG_KEYS = ("lng", "lon", "long", "longitud", "longitude", "x")
NEIGHBORHOOD_KEYS = ("barrio", "neighborhood", "comuna")


@dataclass(frozen=True)
class TabularConfig:
    source_name: str
    url: str
    tier: int
    entity_type: str
    subtype: str
    origin_url: str | None = None


def _value(row: dict, keys: tuple[str, ...]):
    lowered = {str(k).lower(): v for k, v in row.items()}
    return next((lowered[key] for key in keys if lowered.get(key) not in (None, "")), None)


def _number(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _in_scope(row: dict, lat, lng, *, scope="caba", neighborhood=None, commune=None) -> bool:
    if scope == "caba":
        # El polígono oficial se aplica posteriormente al persistir; para un
        # tabular sin coordenadas aceptamos sólo los barrios/comunas oficiales.
        row_neighborhood = resolve_neighborhood(str(_value(row, NEIGHBORHOOD_KEYS) or ""))
        row_commune = resolve_commune(_value(row, NEIGHBORHOOD_KEYS))
        if neighborhood and row_neighborhood != resolve_neighborhood(neighborhood):
            return False
        if commune and row_commune not in (None, commune):
            return False
        return row_neighborhood is not None or row_commune is not None or (lat is not None and lng is not None)
    neighborhood = str(_value(row, NEIGHBORHOOD_KEYS) or "").upper()
    if "PALERMO" in neighborhood or neighborhood == "14":
        return True
    return lat is not None and lng is not None and PALERMO_BBOX[0] <= lat <= PALERMO_BBOX[1] and PALERMO_BBOX[2] <= lng <= PALERMO_BBOX[3]


def _in_palermo(row: dict, lat, lng) -> bool:
    """Compatibilidad temporal para adaptadores y tests anteriores."""
    return _in_scope(row, lat, lng, scope="palermo")


def parse_rows(content: bytes, content_type: str) -> list[dict]:
    if "json" in content_type or content.lstrip().startswith((b"{", b"[")):
        payload = __import__("json").loads(content)
        if isinstance(payload, dict) and isinstance(payload.get("features"), list):
            return [{**(item.get("properties") or {}), "_geometry": item.get("geometry") or {}} for item in payload["features"]]
        if isinstance(payload, dict):
            for key in ("results", "data", "items", "records"):
                if isinstance(payload.get(key), list):
                    return [item for item in payload[key] if isinstance(item, dict)]
        return payload if isinstance(payload, list) else []
    text = content.decode("utf-8-sig", "replace")
    first = text.partition("\n")[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


async def run_tabular(config: TabularConfig, *, write: bool, limit: int | None, scope="caba", neighborhood=None, commune=None) -> SourceResult:
    result = SourceResult()
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(config.url, headers={"User-Agent": "PalermoKG/1.0 (+data-quality)"})
        response.raise_for_status()
    rows = parse_rows(response.content, response.headers.get("content-type", ""))
    result.seen = len(rows)
    records, properties = [], []
    for row in rows:
        lat, lng = _number(_value(row, LAT_KEYS)), _number(_value(row, LNG_KEYS))
        geometry = row.get("_geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) >= 2 and geometry.get("type") == "Point":
            lng, lat = _number(coords[0]), _number(coords[1])
        if not _in_scope(row, lat, lng, scope=scope, neighborhood=neighborhood, commune=commune):
            result.skipped += 1
            continue
        name = normalize_name(str(_value(row, NAME_KEYS) or ""))
        if not name:
            result.skipped += 1
            continue
        records.append({"name": name, "entity_type": config.entity_type, "subtype": config.subtype,
                        "lat": lat, "lng": lng, "origin_url": config.origin_url or config.url})
    records = bounded(records, limit)
    result.accepted = len(records)
    result.coverage = {"scope": scope, "accepted_records": result.accepted}
    if not write or not records:
        return result
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, config.source_name, config.origin_url or config.url, config.tier)
        ids = await bulk_get_or_create_entities(conn, records)
        for record in records:
            properties.append({"entity_id": ids[record["name"]], "key": "source_url", "value": config.origin_url or config.url,
                               "value_type": "url", "origins": [config.origin_url or config.url], "confidence": 0.95})
        await bulk_upsert_properties(conn, properties, source_id)
        await mark_source_synced(conn, source_id)
        result.written = len(records)
    finally:
        await conn.close()
    return result
