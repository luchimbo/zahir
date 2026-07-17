"""Contrato de /api/search/natural contra la DB real (solo lectura)."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurada"
)

REQUIRED_KEYS = {
    "answer",
    "answer_markdown",
    "citations",
    "entities_used",
    "mentioned_entities",
    "explainability",
}


async def test_search_natural_contrato(client):
    response = await client.get(
        "/api/search/natural",
        params={"q": "Qué monumentos hay en Palermo?", "max_entities": 4},
    )
    assert response.status_code == 200
    payload = response.json()
    assert REQUIRED_KEYS <= payload.keys()
    assert isinstance(payload["answer"], str) and payload["answer"]
    assert isinstance(payload["citations"], list)
    assert isinstance(payload["mentioned_entities"], list)


async def test_search_natural_citas_bien_formadas(client):
    response = await client.get(
        "/api/search/natural",
        params={"q": "Qué monumentos hay en Palermo?", "max_entities": 4},
    )
    assert response.status_code == 200
    for citation in response.json()["citations"]:
        assert "entity_id" in citation
        assert "entity_name" in citation
        for source in citation.get("sources") or []:
            assert source.get("url")
