import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(dsn=os.getenv("DATABASE_URL"))


async def get_or_create_entity(conn, name: str, entity_type: str, subtype: str = None,
                                lat: float = None, lng: float = None,
                                description: str = None, origin_url: str = None,
                                all_names: list = None) -> str:
    """
    Busca la entidad por nombre exacto o variante (all_names).
    Si no existe, la crea. Devuelve el UUID canónico.
    """
    row = await conn.fetchrow(
        """
        SELECT id FROM entities
        WHERE is_active = true AND canonical_id IS NULL
          AND (name ILIKE $1 OR $1 = ANY(all_names))
          AND entity_type = $2
        LIMIT 1
        """,
        name, entity_type
    )
    if row:
        return str(row["id"])

    entity_id = await conn.fetchval(
        """
        INSERT INTO entities (name, entity_type, subtype, lat, lng,
                              description, origin_url, all_names)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        name, entity_type, subtype, lat, lng,
        description, origin_url, all_names or []
    )
    return str(entity_id)


async def upsert_property(conn, entity_id: str, key: str, value: str,
                           value_type: str, source_id: str,
                           origins: list = None, confidence: float = 0.5):
    """
    Si la propiedad ya existe con el mismo valor → actualiza last_seen_at.
    Si el valor cambió → cierra la anterior e inserta la nueva.
    Si no existe → inserta.
    """
    existing = await conn.fetchrow(
        """
        SELECT id, value FROM active_properties
        WHERE entity_id = $1 AND key = $2 AND source_id = $3
        LIMIT 1
        """,
        entity_id, key, source_id
    )

    if existing:
        if existing["value"] == str(value):
            await conn.execute(
                "UPDATE properties SET last_seen_at = now() WHERE id = $1",
                existing["id"]
            )
        else:
            await conn.execute(
                "SELECT close_property($1)", existing["id"]
            )
            await _insert_property(conn, entity_id, key, value, value_type,
                                   source_id, origins, confidence)
    else:
        await _insert_property(conn, entity_id, key, value, value_type,
                               source_id, origins, confidence)


async def _insert_property(conn, entity_id, key, value, value_type,
                            source_id, origins, confidence):
    await conn.execute(
        """
        INSERT INTO properties (entity_id, key, value, value_type,
                                source_id, origins, confidence, valid_from)
        VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_DATE)
        """,
        entity_id, key, str(value), value_type,
        source_id, origins or [], confidence
    )


async def get_source_id(conn, source_name: str) -> str:
    row = await conn.fetchrow(
        "SELECT id FROM sources WHERE source_name = $1", source_name
    )
    if not row:
        raise ValueError(f"Fuente '{source_name}' no encontrada en la DB")
    return str(row["id"])


async def ensure_source(conn, source_name: str, source_url: str, tier: int = 1) -> str:
    """Crea la fuente oficial si el seed aún no se aplicó al entorno."""
    return str(await conn.fetchval(
        """INSERT INTO sources (source_name, source_url, tier) VALUES ($1, $2, $3)
           ON CONFLICT (source_name) DO UPDATE SET source_url=EXCLUDED.source_url
           RETURNING id""", source_name, source_url, tier
    ))


async def mark_source_synced(conn, source_id: str):
    """Registra una ejecución exitosa sin alterar el historial de datos."""
    await conn.execute("UPDATE sources SET scraped_at = now() WHERE id = $1", source_id)


async def bulk_get_or_create_entities(conn, records: list[dict]) -> dict[str, str]:
    """
    Batch get-or-create para entidades canonicas del mismo entity_type.
    records: dicts con keys name, entity_type, subtype, lat, lng, origin_url.
    Devuelve mapping name -> entity_id.
    """
    if not records:
        return {}
    entity_type = records[0]["entity_type"]
    names = list({r["name"] for r in records})

    existing_rows = await conn.fetch(
        """
        SELECT id, name
        FROM entities
        WHERE is_active = true AND canonical_id IS NULL
          AND entity_type = $1 AND name = ANY($2)
        """,
        entity_type, names
    )
    existing = {r["name"]: str(r["id"]) for r in existing_rows}

    missing = [r for r in records if r["name"] not in existing]
    if missing:
        rows = [
            (
                r["name"], entity_type, r.get("subtype"),
                r.get("lat"), r.get("lng"), r.get("origin_url")
            )
            for r in missing
        ]
        await conn.executemany(
            """
            INSERT INTO entities (name, entity_type, subtype, lat, lng, origin_url)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            rows
        )
        inserted_rows = await conn.fetch(
            """
            SELECT id, name
            FROM entities
            WHERE is_active = true AND canonical_id IS NULL
              AND entity_type = $1 AND name = ANY($2)
            """,
            entity_type, [r["name"] for r in missing]
        )
        existing.update({r["name"]: str(r["id"]) for r in inserted_rows})

    return existing


async def bulk_upsert_properties(conn, props: list[dict], source_id: str):
    """
    Batch upsert de propiedades activas.
    props: dicts con entity_id, key, value, value_type, confidence, origins.
    Respeta el historial: valores cambiados cierran el registro anterior.
    """
    if not props:
        return
    entity_ids = list({p["entity_id"] for p in props})
    existing_rows = await conn.fetch(
        """
        SELECT id, entity_id, key, value
        FROM active_properties
        WHERE entity_id = ANY($1::uuid[]) AND source_id = $2
        """,
        entity_ids, source_id
    )
    existing = {
        (str(r["entity_id"]), r["key"]): (str(r["id"]), r["value"])
        for r in existing_rows
    }

    to_update_last_seen: list[str] = []
    to_close_and_insert: list[tuple[str, dict]] = []
    to_insert: list[dict] = []

    for p in props:
        key = (p["entity_id"], p["key"])
        if key in existing:
            prop_id, old_value = existing[key]
            if old_value == str(p["value"]):
                to_update_last_seen.append(prop_id)
            else:
                to_close_and_insert.append((prop_id, p))
        else:
            to_insert.append(p)

    if to_update_last_seen:
        await conn.executemany(
            "UPDATE properties SET last_seen_at = now() WHERE id = $1",
            [(pid,) for pid in to_update_last_seen]
        )

    for prop_id, p in to_close_and_insert:
        await conn.execute("SELECT close_property($1)", prop_id)

    all_insert = [
        (
            p["entity_id"], p["key"], str(p["value"]), p["value_type"],
            source_id, p.get("origins") or [], p.get("confidence", 0.5)
        )
        for p in to_insert + [p for _, p in to_close_and_insert]
    ]
    if all_insert:
        await conn.executemany(
            """
            INSERT INTO properties (entity_id, key, value, value_type,
                                    source_id, origins, confidence, valid_from)
            VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_DATE)
            """,
            all_insert
        )
