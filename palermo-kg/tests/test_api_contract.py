"""Tests de contrato de la API contra la DB real (solo lectura)."""
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurada"
)


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_geographies_are_available(client):
    response = await client.get("/api/geographies")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["communes"]) == 15
    assert len(payload["neighborhoods"]) == 48


async def test_search_devuelve_resultados_con_shape(client):
    response = await client.get("/api/search", params={"q": "Don Julio", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert "results" in payload
    assert len(payload["results"]) >= 1
    first = payload["results"][0]
    for key in ("id", "name", "entity_type"):
        assert key in first


async def test_search_query_corta_rechazada(client):
    response = await client.get("/api/search", params={"q": "a"})
    assert response.status_code == 422


async def test_entity_search(client):
    response = await client.get("/api/entity/search", params={"name": "Don Julio"})
    assert response.status_code == 200
    assert "entities" in response.json()


async def test_retrieve_entity_shape(client):
    search = await client.get("/api/search", params={"q": "Don Julio", "limit": 1})
    entity_id = search.json()["results"][0]["id"]

    response = await client.get(f"/api/entity/{entity_id}")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"entity", "properties", "relationships", "tags", "legal_records_summary", "geography"}
    assert payload["entity"]["id"] == entity_id
    assert isinstance(payload["properties"], list)
    assert isinstance(payload["relationships"], list)
    assert isinstance(payload["tags"], list)


async def test_retrieve_entity_uuid_inexistente_404(client):
    response = await client.get(f"/api/entity/{uuid4()}")
    assert response.status_code == 404


async def test_query_shape(client):
    response = await client.get(
        "/api/query", params={"entity_type": "Organization", "limit": 5}
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"total", "limit", "offset", "rows"}
    assert len(payload["rows"]) <= 5
    for row in payload["rows"]:
        assert row["entity_type"] == "Organization"


async def test_insights_data_quality(client):
    response = await client.get("/api/insights/data-quality")
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "duplicates",
        "canonical_without_coordinates",
        "expired_properties",
        "low_confidence_relationships",
    ):
        assert key in payload
        assert isinstance(payload[key], int)


async def test_insights_source_health(client):
    response = await client.get("/api/insights/source-health")
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) >= 1
    for key in ("source_name", "properties", "entities"):
        assert key in rows[0]
