"""Sonda de la API pública de Estadísticas BCRA (v4.0) y Estadísticas Cambiarias.

Sólo lectura. El proyecto tiene registrado en SOURCE_OPERATIONS.md que BCRA
"no respondió de forma confiable desde este entorno" en una exploración previa
de otro endpoint (padrón de entidades). Esta sonda vuelve a probar, esta vez
contra las APIs de estadísticas monetarias/cambiarias, y deja constancia del
resultado para decidir si se crea scrapers/bcra_estadisticas.py.
"""
import time

import httpx

HEADERS = {"User-Agent": "PalermoKGBot/1.0 (luciotambo@gmail.com)"}

CANDIDATES = [
    ("monetarias catálogo", "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias", None),
    ("monetarias var 1", "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/1",
     {"desde": "2024-01-01", "hasta": "2024-02-01"}),
    ("cambiarias maestro", "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Maestros/Divisas", None),
    ("cambiarias cotizaciones", "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones", None),
]


def try_request(client: httpx.Client, label: str, url: str, params: dict | None):
    try:
        r = client.get(url, params=params or {})
        print(f"  {label}: {r.status_code} ({len(r.content)} bytes)")
        if r.status_code == 200:
            try:
                data = r.json()
                if isinstance(data, dict):
                    print(f"    keys: {list(data.keys())}")
                    results = data.get("results")
                    if isinstance(results, list) and results:
                        print(f"    primer resultado: {results[0]}")
                    elif isinstance(results, dict):
                        print(f"    results (dict) keys: {list(results.keys())}")
                else:
                    print(f"    preview: {str(data)[:300]}")
            except Exception:
                print(f"    (no es JSON) preview: {r.text[:200]}")
        else:
            print(f"    body: {r.text[:200]}")
        return r
    except httpx.ConnectError as exc:
        print(f"  {label}: CONNECT ERROR -> {exc}")
    except Exception as exc:
        print(f"  {label}: ERROR {type(exc).__name__}: {exc}")
    return None


def main():
    print("=== 1. Intento con verificación TLS normal ===")
    ok = False
    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for label, url, params in CANDIDATES:
            r = try_request(client, label, url, params)
            if r is not None and r.status_code == 200:
                ok = True

    if not ok:
        print("\n=== 2. Reintento con verify=False para diagnosticar (sólo diagnóstico, no para producción) ===")
        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True, verify=False) as client:
            for label, url, params in CANDIDATES:
                try_request(client, label, url, params)
        print("\n[NOTA] Si esto respondió y lo anterior no, el problema es la cadena de certificados.")
        print("       Nunca desplegar con verify=False; en ese caso usar certifi actualizado o el cert de BCRA.")

    print("\n=== 3. Comportamiento ante llamadas consecutivas (10x, mismo endpoint) ===")
    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        codes = []
        for i in range(10):
            try:
                r = client.get("https://api.bcra.gob.ar/estadisticas/v4.0/monetarias")
                codes.append(r.status_code)
            except Exception as exc:
                codes.append(f"ERR:{type(exc).__name__}")
            time.sleep(0.2)
        print(f"  códigos: {codes}")

    print("\n=== Fin de la sonda BCRA API ===")
    print("Si todo falló: NO crear scrapers/bcra_estadisticas.py.")
    print("Registrar este resultado (con fecha) en SOURCE_OPERATIONS.md, sección")
    print("'Fuentes evaluadas y no activadas', junto a la nota previa sobre BCRA.")


if __name__ == "__main__":
    main()
