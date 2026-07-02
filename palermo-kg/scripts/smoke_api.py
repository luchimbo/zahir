"""Arranca la API local, prueba endpoints básicos y apaga el servidor."""
import subprocess
import sys
import time

import httpx


def wait_for_health(base_url: str, timeout_s: int = 30) -> dict:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"La API no respondió /health: {last_error}")


def main() -> int:
    base_url = "http://127.0.0.1:8000"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        health = wait_for_health(base_url)
        query = httpx.get(
            f"{base_url}/api/query",
            params={"entity_type": "Organization", "subtype": "restaurant", "limit": 3},
            timeout=10,
        )
        query.raise_for_status()
        payload = query.json()
        print(f"health={health}")
        print(f"restaurant_rows={len(payload.get('rows', []))}")
        for row in payload.get("rows", []):
            print(f"- {row.get('name')} ({row.get('subtype')})")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
