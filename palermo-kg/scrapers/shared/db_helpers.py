"""Operaciones de escritura compartidas, compatibles con TiDB/MySQL."""
import json
import re
from uuid import uuid4

import pymysql
from fastapi.concurrency import run_in_threadpool
from api.db import _params, get_pool


class ScraperConnection:
    """Una única conexión persistente para cargas secuenciales de un scraper.

    Los scrapers largos (geocodificación fila por fila) pasan minutos entre
    escrituras; TiDB corta conexiones inactivas antes de eso. ``ping`` revive
    la conexión de forma transparente y el commit se hace en lotes chicos
    para no perder trabajo si igual se corta a mitad de un lote.
    """
    COMMIT_EVERY = 20

    def __init__(self, config: dict):
        self.conn = pymysql.connect(**config)
        self.pending_writes = 0

    def _run(self, sql, args, one=False, value=False):
        self.conn.ping(reconnect=True)
        with self.conn.cursor() as cursor:
            cursor.execute(_params(sql), args)
            if value:
                row = cursor.fetchone()
                return next(iter(row.values())) if row else None
            if one:
                return cursor.fetchone()
            if cursor.description:
                return cursor.fetchall()
            self.pending_writes += 1
            if self.pending_writes >= self.COMMIT_EVERY:
                self.conn.commit()
                self.pending_writes = 0
            return cursor.rowcount

    async def fetch(self, sql, *args): return await run_in_threadpool(self._run, sql, args)
    async def fetchrow(self, sql, *args): return await run_in_threadpool(self._run, sql, args, True)
    async def fetchval(self, sql, *args): return await run_in_threadpool(self._run, sql, args, False, True)
    async def execute(self, sql, *args): return await run_in_threadpool(self._run, sql, args)
    def _executemany(self, sql, rows):
        self.conn.ping(reconnect=True)
        with self.conn.cursor() as cursor:
            cursor.executemany(_params(sql), rows)
            self.pending_writes += len(rows)
            if self.pending_writes >= self.COMMIT_EVERY:
                self.conn.commit()
                self.pending_writes = 0
            return cursor.rowcount
    async def executemany(self, sql, rows):
        if not rows:
            return 0
        return await run_in_threadpool(self._executemany, sql, rows)
    def _close(self):
        if self.pending_writes:
            self.conn.ping(reconnect=True)
            self.conn.commit()
        self.conn.close()
    async def close(self):
        await run_in_threadpool(self._close)

    def _flush(self):
        if self.pending_writes:
            self.conn.ping(reconnect=True)
            self.conn.commit()
            self.pending_writes = 0

    async def flush(self):
        """Hace visibles registros de control antes de consultarlos de nuevo."""
        await run_in_threadpool(self._flush)


async def get_conn() -> ScraperConnection:
    pool = await get_pool()
    return await run_in_threadpool(ScraperConnection, pool.config)


async def get_or_create_entity(conn, name: str, entity_type: str, subtype: str = None,
                               lat: float = None, lng: float = None, description: str = None,
                               origin_url: str = None, all_names: list | None = None,
                               source_id: str | None = None, external_id: str | None = None) -> str:
    if (lat is None) != (lng is None):
        lat = lng = None
    if lat is not None and not (-90 <= float(lat) <= 90 and -180 <= float(lng) <= 180):
        lat = lng = None
    if source_id and external_id:
        external = await conn.fetchrow(
            """SELECT entity_id FROM external_ids WHERE source_id=$1 AND external_id=$2 LIMIT 1""",
            source_id, str(external_id),
        )
        if external:
            return str(external["entity_id"])
    # A name is not an identity in CABA: chains regularly have many branches.
    # If no stable provider ID exists, only reuse a homonym when it is at the
    # same point (or when neither record has coordinates).
    coordinate_condition = "" if entity_type == "Location" else (
        "AND ((lat IS NULL AND lng IS NULL) OR (ABS(lat-$4) < 0.00015 AND ABS(lng-$5) < 0.00015))"
        if lat is not None else "AND lat IS NULL AND lng IS NULL"
    )
    identity_args = ((entity_type, name, name) if entity_type == "Location" else
                     ((entity_type, name, name, lat, lng) if lat is not None else (entity_type, name, name)))
    row = await conn.fetchrow(
        f"""SELECT id FROM entities WHERE is_active=TRUE AND canonical_id IS NULL
           AND entity_type=$1 AND (LOWER(name)=LOWER($2)
           OR JSON_SEARCH(COALESCE(all_names, JSON_ARRAY()), 'one', $3) IS NOT NULL)
           {coordinate_condition} LIMIT 1""",
        *identity_args,
    )
    if row:
        entity_id = str(row["id"])
    else:
        entity_id = str(uuid4())
        await conn.execute(
            """INSERT INTO entities (id,name,entity_type,subtype,lat,lng,description,origin_url,all_names)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            entity_id, name, entity_type, subtype, lat, lng, description, origin_url,
            json.dumps(all_names or []),
        )
    if source_id and external_id:
        await conn.execute(
            """INSERT INTO external_ids (id,entity_id,source_id,external_id) VALUES ($1,$2,$3,$4)
               ON DUPLICATE KEY UPDATE entity_id=entity_id""",
            str(uuid4()), entity_id, source_id, str(external_id),
        )
    return entity_id


async def _insert_property(conn, entity_id, key, value, value_type, source_id, origins, confidence):
    await conn.execute(
        """INSERT INTO properties (id,entity_id,`key`,value,value_type,source_id,origins,confidence,valid_from)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,CURRENT_DATE())""",
        str(uuid4()), entity_id, key, str(value), value_type, source_id,
        json.dumps(origins or []), confidence,
    )


async def upsert_property(conn, entity_id: str, key: str, value: str, value_type: str,
                          source_id: str, origins: list | None = None, confidence: float = 0.5,
                          valid_from: str | None = None):
    """Preserva historial: cierra el valor activo si cambió e inserta otro."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,149}", key):
        raise ValueError(f"Property key inválida: {key!r}")
    if value_type not in {"string", "number", "boolean", "date", "url", "json"}:
        raise ValueError(f"value_type inválido: {value_type!r}")
    value = str(value).strip()
    if not value:
        return
    existing = await conn.fetchrow(
        """SELECT id,value FROM active_properties
           WHERE entity_id=$1 AND `key`=$2 AND source_id=$3 LIMIT 1""", entity_id, key, source_id)
    if existing and existing["value"] == str(value):
        await conn.execute("UPDATE properties SET last_seen_at=CURRENT_TIMESTAMP WHERE id=$1", existing["id"])
    else:
        if existing:
            if valid_from:
                await conn.execute("UPDATE properties SET valid_until=DATE_SUB($1, INTERVAL 1 DAY) WHERE id=$2 AND valid_until IS NULL", valid_from, existing["id"])
            else:
                await conn.execute("UPDATE properties SET valid_until=CURRENT_DATE() WHERE id=$1 AND valid_until IS NULL", existing["id"])
        if valid_from:
            await conn.execute(
                """INSERT INTO properties (id,entity_id,`key`,value,value_type,source_id,origins,confidence,valid_from)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                str(uuid4()), entity_id, key, value, value_type, source_id,
                json.dumps(origins or []), confidence, valid_from,
            )
        else:
            await _insert_property(conn, entity_id, key, value, value_type, source_id, origins, confidence)


async def get_source_id(conn, source_name: str) -> str:
    row = await conn.fetchrow("SELECT id FROM sources WHERE source_name=$1", source_name)
    if not row:
        raise ValueError(f"Fuente '{source_name}' no encontrada en la DB")
    return str(row["id"])


async def ensure_source(conn, source_name: str, source_url: str, tier: int = 1) -> str:
    existing = await conn.fetchrow("SELECT id FROM sources WHERE source_name=$1", source_name)
    if existing:
        await conn.execute("UPDATE sources SET source_url=$1, tier=$2 WHERE id=$3", source_url, tier, existing["id"])
        return str(existing["id"])
    await conn.execute(
        """INSERT INTO sources (id,source_name,source_url,tier) VALUES ($1,$2,$3,$4)
           ON DUPLICATE KEY UPDATE source_url=VALUES(source_url)""", str(uuid4()), source_name, source_url, tier)
    # TiDB puede diferir la visibilidad de la inserción del registro de control
    # hasta el commit; el catálogo necesita el id en la misma operación.
    await conn.flush()
    return await get_source_id(conn, source_name)


async def register_source_policy(conn, source_id: str, *, data_class="current", refresh_schedule="manual",
                                 access_mode="public", cost_policy="free", license_url=None, enabled=True):
    await conn.execute(
        """INSERT INTO source_policies (source_id,data_class,refresh_schedule,access_mode,cost_policy,license_url,enabled)
           VALUES ($1,$2,$3,$4,$5,$6,$7)
           ON DUPLICATE KEY UPDATE data_class=VALUES(data_class),refresh_schedule=VALUES(refresh_schedule),
             access_mode=VALUES(access_mode),cost_policy=VALUES(cost_policy),license_url=VALUES(license_url)""",
        source_id, data_class, refresh_schedule, access_mode, cost_policy, license_url, enabled,
    )


async def save_checkpoint(conn, source_id: str, cursor_value=None, content_hash=None, error_code=None, retry_count=0):
    await conn.execute(
        """INSERT INTO source_checkpoints (source_id,cursor_value,content_hash,last_heartbeat_at,last_error_code,retry_count)
           VALUES ($1,$2,$3,CURRENT_TIMESTAMP,$4,$5)
           ON DUPLICATE KEY UPDATE cursor_value=VALUES(cursor_value),content_hash=VALUES(content_hash),
             last_heartbeat_at=CURRENT_TIMESTAMP,last_error_code=VALUES(last_error_code),retry_count=VALUES(retry_count)""",
        source_id, cursor_value, content_hash, error_code, retry_count,
    )


async def mark_source_synced(conn, source_id: str):
    await conn.execute("UPDATE sources SET scraped_at=CURRENT_TIMESTAMP WHERE id=$1", source_id)


async def start_sync_run(conn, source_id: str) -> str:
    run_id = str(uuid4())
    await conn.execute(
        "INSERT INTO source_sync_runs (id,source_id,status) VALUES ($1,$2,'running')",
        run_id, source_id,
    )
    return run_id


async def has_active_sync_run(conn, source_id: str) -> bool:
    return bool(await conn.fetchval(
        "SELECT COUNT(*) FROM source_sync_runs WHERE source_id=$1 AND status='running'", source_id
    ))


async def finish_sync_run(conn, run_id: str, status: str, records_seen: int = 0,
                          records_written: int = 0, error_message: str | None = None):
    if status not in {"completed", "partial", "failed"}:
        raise ValueError(f"Estado de sincronización inválido: {status}")
    await conn.execute(
        """UPDATE source_sync_runs SET status=$1, completed_at=CURRENT_TIMESTAMP,
           records_seen=$2, records_written=$3, error_message=$4 WHERE id=$5""",
        status, records_seen, records_written, error_message, run_id,
    )


async def save_run_metrics(conn, run_id: str, *, coverage=None, error_code=None, checkpoint_after=None):
    """Guarda métricas del adaptador, incluso para ejecuciones parciales."""
    await conn.execute(
        """INSERT INTO source_run_metrics (run_id,coverage,error_code,checkpoint_after)
           VALUES ($1,$2,$3,$4)
           ON DUPLICATE KEY UPDATE coverage=VALUES(coverage), error_code=VALUES(error_code),
             checkpoint_after=VALUES(checkpoint_after)""",
        run_id, json.dumps(coverage or {}), error_code, checkpoint_after,
    )


async def set_source_enabled(conn, source_id: str, enabled: bool):
    await conn.execute("UPDATE source_policies SET enabled=$1 WHERE source_id=$2", enabled, source_id)


async def upsert_relationship(conn, from_entity_id: str, relationship_type: str, to_entity_id: str,
                              *, confidence: float = 0.95, origins: list | None = None,
                              direction: str = "directed", weight: float = 1.0) -> None:
    """Crea una arista una sola vez y actualiza su evidencia al reejecutar."""
    if from_entity_id == to_entity_id:
        return
    await conn.execute(
        """INSERT INTO relationships (id,from_entity_id,relationship_type,to_entity_id,weight,confidence,origins,direction)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
           ON DUPLICATE KEY UPDATE confidence=GREATEST(confidence,VALUES(confidence)),
             origins=VALUES(origins), weight=VALUES(weight), direction=VALUES(direction)""",
        str(uuid4()), from_entity_id, relationship_type, to_entity_id, weight, confidence,
        json.dumps(origins or []), direction,
    )


async def bulk_get_or_create_entities(conn, records: list[dict]) -> dict[str, str]:
    """Resuelve entidades por nombre en bloque; evita un round-trip por fila."""
    unique = {}
    for record in records:
        name = str(record["name"]).strip()
        if name:
            # ``identity_key`` is supplied by high-volume sources when they
            # have an address or provider record key. It prevents branches
            # called alike from collapsing into a single entity.
            identity_key = str(record.get("identity_key") or name.lower())
            unique.setdefault((record["entity_type"], identity_key), {**record, "name": name})
    if not unique:
        return {}

    clauses, params = [], []
    by_type = {}
    for entity_type, identity_key in unique:
        by_type.setdefault(entity_type, []).append(identity_key)
    # Fetch candidate homonyms; coordinates are checked below instead of
    # treating their names as a globally unique key.
    for entity_type, identities in by_type.items():
        names = [unique[(entity_type, key)]["name"].lower() for key in identities]
        placeholders = ", ".join(f"${len(params) + index + 2}" for index in range(len(names)))
        clauses.append(f"(entity_type=${len(params) + 1} AND LOWER(name) IN ({placeholders}))")
        params.extend([entity_type, *names])
    existing_rows = await conn.fetch(
        f"SELECT id, name, entity_type, lat, lng FROM entities WHERE is_active=TRUE AND canonical_id IS NULL AND ({' OR '.join(clauses)})",
        *params,
    )
    result = {}
    for key, record in unique.items():
        for row in existing_rows:
            if row["entity_type"] != record["entity_type"] or str(row["name"]).lower() != record["name"].lower():
                continue
            lat, lng = record.get("lat"), record.get("lng")
            if lat is None and row["lat"] is None:
                result[key] = str(row["id"]); break
            if lat is not None and row["lat"] is not None and abs(float(row["lat"]) - float(lat)) < 0.00015 and abs(float(row["lng"]) - float(lng)) < 0.00015:
                result[key] = str(row["id"]); break
    inserts = []
    for key, record in unique.items():
        if key in result:
            continue
        entity_id = str(uuid4())
        result[key] = entity_id
        lat, lng = record.get("lat"), record.get("lng")
        if (lat is None) != (lng is None) or (lat is not None and not (-90 <= float(lat) <= 90 and -180 <= float(lng) <= 180)):
            lat = lng = None
        inserts.append((
            entity_id, record["name"], record["entity_type"], record.get("subtype"), lat, lng,
            record.get("description"), record.get("origin_url"), json.dumps(record.get("all_names") or []),
        ))
    await conn.executemany(
        """INSERT INTO entities (id,name,entity_type,subtype,lat,lng,description,origin_url,all_names)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        inserts,
    )
    resolved = {}
    for record in records:
        key = (record["entity_type"], str(record.get("identity_key") or record["name"].lower()))
        resolved[str(record.get("record_key") or record["name"])] = result[key]
    return resolved


async def bulk_upsert_properties(conn, props: list[dict], source_id: str):
    """Actualiza propiedades de una fuente en pocos viajes de red a TiDB."""
    normalized = []
    for prop in props:
        key = prop["key"]
        value_type = prop["value_type"]
        value = str(prop["value"]).strip()
        if not value:
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,149}", key):
            raise ValueError(f"Property key invÃ¡lida: {key!r}")
        if value_type not in {"string", "number", "boolean", "date", "url", "json"}:
            raise ValueError(f"value_type invÃ¡lido: {value_type!r}")
        normalized.append({**prop, "value": value})
    if not normalized:
        return

    entity_ids = sorted({prop["entity_id"] for prop in normalized})
    placeholders = ", ".join(f"${index + 2}" for index in range(len(entity_ids)))
    existing_rows = await conn.fetch(
        f"""SELECT id, entity_id, `key`, value FROM active_properties
            WHERE source_id=$1 AND entity_id IN ({placeholders})""",
        source_id, *entity_ids,
    )
    existing = {(row["entity_id"], row["key"]): row for row in existing_rows}
    seen_updates, close_rows, insert_rows = [], [], []
    for prop in normalized:
        current = existing.get((prop["entity_id"], prop["key"]))
        if current and str(current["value"]) == prop["value"]:
            seen_updates.append((current["id"],))
        else:
            if current:
                close_rows.append((current["id"],))
            insert_rows.append((
                str(uuid4()), prop["entity_id"], prop["key"], prop["value"], prop["value_type"],
                source_id, json.dumps(prop.get("origins") or []), prop.get("confidence", 0.5),
            ))
    await conn.executemany("UPDATE properties SET last_seen_at=CURRENT_TIMESTAMP WHERE id=$1", seen_updates)
    await conn.executemany("UPDATE properties SET valid_until=CURRENT_DATE() WHERE id=$1 AND valid_until IS NULL", close_rows)
    await conn.executemany(
        """INSERT INTO properties (id,entity_id,`key`,value,value_type,source_id,origins,confidence,valid_from)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,CURRENT_DATE())""",
        insert_rows,
    )


async def bulk_link_external_ids(conn, links: list[tuple[str, str, str]]):
    """Asocia IDs estables de proveedores sin un viaje de red por entidad."""
    rows = [(str(uuid4()), entity_id, source_id, external_id) for entity_id, source_id, external_id in links]
    await conn.executemany(
        """INSERT INTO external_ids (id,entity_id,source_id,external_id) VALUES ($1,$2,$3,$4)
           ON DUPLICATE KEY UPDATE entity_id=VALUES(entity_id)""",
        rows,
    )
