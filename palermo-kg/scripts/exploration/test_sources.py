"""Test rápido de conectividad de las fuentes nuevas."""
import httpx

# Wikidata SPARQL
q = """SELECT ?item ?itemLabel WHERE {
  ?item wdt:P31 wd:Q33506 .
  ?item wdt:P131* wd:Q1486 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es". }
} LIMIT 5"""

r = httpx.get(
    "https://query.wikidata.org/sparql",
    params={"query": q},
    headers={"Accept": "application/sparql-results+json", "User-Agent": "PalermoKG/1.0"},
    timeout=20,
)
print(f"Wikidata: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    results = data.get("results", {}).get("bindings", [])
    for row in results[:3]:
        print(f"  {row.get('itemLabel', {}).get('value', '?')}")
else:
    print(f"  Error: {r.text[:200]}")

# BCRA — buscar URL correcta
for url in [
    "https://www.bcra.gob.ar/Pdfs/SistemasFinancieros/PadronEntidades.csv",
    "https://www.bcra.gob.ar/archivos/Pdfs/SistemasFinancieros/PadronEntidades.csv",
    "https://www.bcra.gob.ar/SistemasFinancieros/sf020302.asp",
]:
    try:
        r2 = httpx.get(url, timeout=10, follow_redirects=True)
        print(f"BCRA {url[-40:]}: {r2.status_code} ({len(r2.content)} bytes)")
    except Exception as e:
        print(f"BCRA {url[-40:]}: ERROR {e}")
