"""Tests de los filtros include_history/source/historical de /api/entity/{id}."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurada"
)


async def _get_entity_id(client) -> str:
    response = await client.get("/api/search", params={"q": "Don Julio", "limit": 1})
    results = response.json()["results"]
    assert results, "Se esperaba al menos una entidad para probar filtros"
    return results[0]["id"]


async def test_include_history_es_superset(client):
    entity_id = await _get_entity_id(client)
    default = (await client.get(f"/api/entity/{entity_id}")).json()
    with_history = (
        await client.get(f"/api/entity/{entity_id}", params={"include_history": "true"})
    ).json()
    assert len(with_history["properties"]) >= len(default["properties"])


async def test_filtro_source(client):
    entity_id = await _get_entity_id(client)
    default = (await client.get(f"/api/entity/{entity_id}")).json()
    source_names = [p["source_name"] for p in default["properties"] if p.get("source_name")]
    if not source_names:
        pytest.skip("La entidad de prueba no tiene propiedades con fuente")
    source = source_names[0]
    filtered = (
        await client.get(f"/api/entity/{entity_id}", params={"source": source})
    ).json()
    assert len(filtered["properties"]) >= 1
    assert all(p["source_name"] == source for p in filtered["properties"])


async def test_filtro_historical_false(client):
    entity_id = await _get_entity_id(client)
    filtered = (
        await client.get(f"/api/entity/{entity_id}", params={"historical": "false"})
    ).json()
    for prop in filtered["properties"]:
        assert prop["valid_until"] is None
        assert prop.get("source_name") != "sinca"


async def test_relationships_tienen_relation_side(client):
    entity_id = await _get_entity_id(client)
    payload = (await client.get(f"/api/entity/{entity_id}")).json()
    for rel in payload["relationships"]:
        assert rel["relation_side"] in ("incoming", "outgoing")
