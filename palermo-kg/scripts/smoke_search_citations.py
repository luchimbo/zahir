"""Smoke test de busqueda, citas y contrato de /api/search/natural."""
import subprocess
import sys
import time
from collections.abc import Iterable

import httpx


BASE_URL = "http://127.0.0.1:8027"
REQUIRED_NATURAL_KEYS = {
    "answer",
    "answer_markdown",
    "citations",
    "entities_used",
    "mentioned_entities",
    "explainability",
}

CASES = [
    {
        "query": "Qué zonas tienen más ruido nocturno?",
        "expected_subtypes": {"zona_ruido"},
        "allow_empty_citations": False,
    },
    {
        "query": "Qué decks gastronómicos hay en Palermo?",
        "expected_subtypes": {"deck_gastronomico"},
        "allow_empty_citations": False,
    },
    {
        "query": "Qué monumentos hay en Palermo?",
        "expected_subtypes": {"monumento"},
        "allow_empty_citations": False,
    },
    {
        "query": "Qué habilitaciones tipo café hay en Palermo?",
        "expected_subtypes": {"comercio_habilitado", "permiso_gastronomico"},
        "allow_empty_citations": False,
    },
]


def wait_for_health(timeout_s: int = 45) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=5)
            response.raise_for_status()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"La API no respondió /health: {last_error}")


def assert_required_keys(payload: dict, query: str) -> None:
    missing = REQUIRED_NATURAL_KEYS - payload.keys()
    if missing:
        raise AssertionError(f"{query}: faltan keys en search/natural: {sorted(missing)}")


def assert_subtype_hit(results: Iterable[dict], expected_subtypes: set[str], query: str) -> None:
    actual = {row.get("subtype") for row in results if row.get("subtype")}
    if actual.isdisjoint(expected_subtypes):
        raise AssertionError(
            f"{query}: esperaba algun subtype de {sorted(expected_subtypes)}, recibi {sorted(actual)}"
        )


def assert_citations(payload: dict, query: str, allow_empty: bool) -> None:
    citations = payload.get("citations") or []
    if not citations and not allow_empty:
        raise AssertionError(f"{query}: esperaba citas")

    for citation in citations:
        if "entity_id" not in citation or "entity_name" not in citation:
            raise AssertionError(f"{query}: cita incompleta: {citation}")
        sources = citation.get("sources") or []
        for source in sources:
            if not source.get("url"):
                raise AssertionError(f"{query}: source sin url: {source}")


def main() -> int:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8027",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_for_health()
        client = httpx.Client(timeout=20)
        for case in CASES:
            query = case["query"]
            search = client.get(
                f"{BASE_URL}/api/search",
                params={"q": query, "limit": 10, "min_score": 0.2},
            )
            search.raise_for_status()
            search_payload = search.json()
            results = search_payload.get("results") or []
            assert_subtype_hit(results, case["expected_subtypes"], query)

            natural = client.get(
                f"{BASE_URL}/api/search/natural",
                params={"q": query, "max_entities": 6},
            )
            natural.raise_for_status()
            natural_payload = natural.json()
            assert_required_keys(natural_payload, query)
            assert_citations(natural_payload, query, case["allow_empty_citations"])
            if natural_payload.get("answer") == "No tengo datos suficientes para responder.":
                raise AssertionError(f"{query}: devolvio fallback sin datos pese a resultados estructurados")

            print(
                f"ok query={query!r} results={len(results)} "
                f"citations={len(natural_payload.get('citations') or [])}"
            )

        print("Smoke search/citations OK")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
