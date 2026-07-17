"""Busca datasets en la API CKAN del portal de datos abiertos de BA."""
import httpx

# Portal CKAN de BA Data
CKAN = "https://data.buenosaires.gob.ar/api/3/action"

client = httpx.Client(follow_redirects=True, timeout=20)

terms = ["ecobici", "arbolado", "obras", "delito", "mercado", "bache", "wifi", "comisaria", "cajero"]

for term in terms:
    r = client.get(f"{CKAN}/package_search", params={"q": term, "rows": 3})
    if r.status_code != 200:
        print(f"{term}: HTTP {r.status_code}")
        continue
    results = r.json().get("result", {}).get("results", [])
    if not results:
        print(f"{term}: sin resultados")
        continue
    print(f"--- {term} ---")
    for pkg in results[:2]:
        print(f"  {pkg['name']}")
        for res in pkg.get("resources", [])[:3]:
            fmt = res.get("format", "?")
            url = res.get("url", "")
            print(f"    [{fmt}] {url[:100]}")
    print()

client.close()
