"""Sonda de conectividad y forma de datos de BYMA Open Data.

Sólo lectura: no escribe en la DB ni se registra como fuente. Confirma:
  - verbo HTTP real de cada endpoint candidato (la API "REST" de BYMA es
    mayormente POST con body JSON, no GET con querystring),
  - si hace falta relajar el contexto TLS (nunca se desactiva la verificación),
  - profundidad real del histórico disponible en chart/historical-series/history,
  - nombres de campos exactos para mapear a series_key.
"""
import json
import ssl
import time
from datetime import datetime, timezone

import httpx

BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PalermoKGBot/1.0 (luciotambo@gmail.com)",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://open.bymadata.com.ar",
    "Referer": "https://open.bymadata.com.ar/",
}


def make_client(seclevel1: bool) -> httpx.Client:
    ctx = ssl.create_default_context()
    if seclevel1:
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except ssl.SSLError as exc:
            print(f"  [aviso] no se pudo bajar SECLEVEL: {exc}")
    return httpx.Client(verify=ctx, headers=HEADERS, timeout=20, follow_redirects=True)


def try_request(client: httpx.Client, method: str, path: str, body: dict | None = None, params: dict | None = None):
    url = BASE + path
    try:
        if method == "POST":
            r = client.post(url, json=body or {})
        else:
            r = client.get(url, params=params or {})
        print(f"  {method} {path} -> {r.status_code} ({len(r.content)} bytes)")
        if r.status_code == 200:
            try:
                data = r.json()
                preview = json.dumps(data, ensure_ascii=False)[:500]
                print(f"    preview: {preview}")
                return data
            except Exception:
                print(f"    (no es JSON) preview: {r.text[:200]}")
        else:
            print(f"    body: {r.text[:200]}")
    except Exception as exc:
        print(f"  {method} {path} -> ERROR {type(exc).__name__}: {exc}")
    return None


def main():
    print("=== 1. Handshake TLS ===")
    ok_default = ok_seclevel1 = False
    try:
        with make_client(seclevel1=False) as c:
            r = c.get(BASE + "index-price")
            ok_default = True
            print(f"  Contexto por defecto: OK (status {r.status_code})")
    except Exception as exc:
        print(f"  Contexto por defecto: FALLA -> {type(exc).__name__}: {exc}")
    try:
        with make_client(seclevel1=True) as c:
            r = c.get(BASE + "index-price")
            ok_seclevel1 = True
            print(f"  SECLEVEL=1: OK (status {r.status_code})")
    except Exception as exc:
        print(f"  SECLEVEL=1: FALLA -> {type(exc).__name__}: {exc}")

    if not ok_default and not ok_seclevel1:
        print("\n[DECISION] BYMA no es alcanzable desde este entorno ni con TLS relajado.")
        print("           No construir scrapers/byma_*.py; documentar en SOURCE_OPERATIONS.md.")
        return

    client = make_client(seclevel1=not ok_default)
    print(f"\n(usando cliente con seclevel1={not ok_default} para el resto de las pruebas)\n")

    print("=== 2. Índices (MERVAL) ===")
    try_request(client, "POST", "index-price", {"index": "MERVAL"})
    try_request(client, "GET", "index-price")

    print("\n=== 3. Especies líderes / generales (para ubicar YPFD) ===")
    try_request(client, "POST", "leading-equity", {"excludeZeroPxAndQty": True, "T2": True})
    try_request(client, "POST", "general-equity", {"excludeZeroPxAndQty": True, "T2": True})

    print("\n=== 4. Ficha técnica / cotización puntual YPFD ===")
    try_request(client, "POST", "bnown/fichatecnica/especies/cotizacion", {"symbol": "YPFD"})

    print("\n=== 5. Histórico (chart/historical-series/history) ===")
    now = int(time.time())
    epoch_2000 = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp())
    for symbol in ("MERVAL", "YPFD"):
        print(f"  -- symbol={symbol} --")
        try_request(client, "GET", "chart/historical-series/history",
                    params={"symbol": symbol, "resolution": "D", "from": epoch_2000, "to": now})
        try_request(client, "POST", "chart/historical-series/history",
                    {"symbol": symbol, "resolution": "D", "from": epoch_2000, "to": now})

    client.close()
    print("\n=== Fin de la sonda BYMA ===")
    print("Revisar arriba: verbo que respondió 200, forma del JSON (t/o/h/l/c/v?),")
    print("y si 'from' epoch 2000 devuelve datos desde esa fecha o BYMA los recorta.")


if __name__ == "__main__":
    main()
