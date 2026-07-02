"""Busca datasets ambientales en la API CKAN de BA Data."""
import httpx

CKAN = "https://data.buenosaires.gob.ar/api/3/action"

def main():
    client = httpx.Client(follow_redirects=True, timeout=20)
    terms = ["ruido", "anegamiento", "calidad-aire", "arbolado"]
    for term in terms:
        print(f"=== {term} ===")
        try:
            r = client.get(f"{CKAN}/package_search", params={"q": term, "rows": 5})
            r.raise_for_status()
            results = r.json().get("result", {}).get("results", [])
            for pkg in results:
                print(f"Package: {pkg['name']}")
                for res in pkg.get("resources", []):
                    fmt = res.get("format", "?")
                    url = res.get("url", "")
                    print(f"  [{fmt}] {url}")
        except Exception as e:
            print(f"Error: {e}")
        print()
    client.close()

if __name__ == "__main__":
    main()
