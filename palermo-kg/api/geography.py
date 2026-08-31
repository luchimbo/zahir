"""Consultas territoriales consistentes sobre la jerarquía CABA."""
from __future__ import annotations

from geography_catalog import resolve_commune, resolve_neighborhood


async def resolve_scope_ids(conn, neighborhood: str | None = None, commune: str | int | None = None) -> tuple[str | None, str | None, str | None, int | None]:
    """Devuelve IDs de Location y valores canónicos; rechaza ámbitos inválidos."""
    resolved_neighborhood = resolve_neighborhood(neighborhood) if neighborhood else None
    resolved_commune = resolve_commune(commune) if commune is not None else None
    if neighborhood and not resolved_neighborhood:
        raise ValueError("Barrio de CABA no reconocido")
    if commune is not None and not resolved_commune:
        raise ValueError("Comuna debe estar entre 1 y 15")
    if resolved_neighborhood:
        expected = resolve_commune_from_neighborhood(resolved_neighborhood)
        if resolved_commune and expected != resolved_commune:
            raise ValueError("El barrio no pertenece a la comuna indicada")
        resolved_commune = expected
    neighborhood_id = None
    commune_id = None
    if resolved_neighborhood:
        neighborhood_id = await conn.fetchval(
            "SELECT id FROM entities WHERE entity_type='Location' AND name=$1 AND canonical_id IS NULL LIMIT 1",
            resolved_neighborhood,
        )
    if resolved_commune:
        commune_id = await conn.fetchval(
            "SELECT id FROM entities WHERE entity_type='Location' AND name=$1 AND canonical_id IS NULL LIMIT 1",
            f"Comuna {resolved_commune}",
        )
    return (str(neighborhood_id) if neighborhood_id else None, str(commune_id) if commune_id else None,
            resolved_neighborhood, resolved_commune)


def resolve_commune_from_neighborhood(neighborhood: str) -> int:
    from geography_catalog import NEIGHBORHOOD_TO_COMMUNE
    return NEIGHBORHOOD_TO_COMMUNE[neighborhood]


def geography_join(neighborhood_id: str | None, commune_id: str | None) -> str:
    joins = []
    if neighborhood_id:
        joins.append(f"EXISTS (SELECT 1 FROM relationships geo_n WHERE geo_n.from_entity_id=e.id AND geo_n.relationship_type='LOCATED_IN' AND geo_n.to_entity_id='{neighborhood_id}')")
    elif commune_id:
        joins.append(f"EXISTS (SELECT 1 FROM relationships geo_c WHERE geo_c.from_entity_id=e.id AND geo_c.relationship_type='LOCATED_IN' AND geo_c.to_entity_id='{commune_id}') OR EXISTS (SELECT 1 FROM relationships geo_n JOIN relationships hierarchy ON hierarchy.from_entity_id=geo_n.to_entity_id AND hierarchy.relationship_type='PART_OF' AND hierarchy.to_entity_id='{commune_id}' WHERE geo_n.from_entity_id=e.id AND geo_n.relationship_type='LOCATED_IN')")
    return " AND ".join(joins)


async def geography_for_entities(conn, entity_ids: list[str]) -> dict[str, dict]:
    if not entity_ids:
        return {}
    placeholders = ", ".join(f"${index + 1}" for index in range(len(entity_ids)))
    rows = await conn.fetch(f"""SELECT r.from_entity_id entity_id, place.name neighborhood,
        commune.name commune FROM relationships r
        JOIN entities place ON place.id=r.to_entity_id AND place.entity_type='Location'
        LEFT JOIN relationships h ON h.from_entity_id=place.id AND h.relationship_type='PART_OF'
        LEFT JOIN entities commune ON commune.id=h.to_entity_id AND commune.name LIKE 'Comuna %%'
        WHERE r.relationship_type='LOCATED_IN' AND r.from_entity_id IN ({placeholders})""", *entity_ids)
    result = {}
    for row in rows:
        item = dict(row)
        # Direct commune links are useful for aggregate data; a neighborhood is preferred.
        if str(item["neighborhood"]).startswith("Comuna "):
            result.setdefault(item["entity_id"], {"neighborhood": None, "commune": item["neighborhood"]})
        else:
            result[item["entity_id"]] = {"neighborhood": item["neighborhood"], "commune": item["commune"]}
    return result
