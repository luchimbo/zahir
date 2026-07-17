"""Encuentra URLs correctas de datasets GCBA grupo B."""
import httpx

CANDIDATES = {
    "ecobici": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/bicicletas-publicas/estaciones-bicicletas-publicas.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/ecobici/ecobici-estaciones.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-transporte/bicicletas-publicas/bicicletas-publicas.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/bicicletas-publicas/nueva-bicicleta-publica.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/bicicletas-publicas/recorridos-realizados-2023.csv",
    ],
    "colectivos_paradas": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos/paradas-de-colectivo.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos/colectivos.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-transporte/colectivos/paradas-colectivos.geojson",
    ],
    "obras": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-desarrollo-urbano/obras-en-construccion/obras-en-construccion.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/obras-publicas/obras-publicas.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/obras/obras.geojson",
    ],
    "mapa_delito": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/delitos/delitos-2023.csv",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/mapa-del-delito/mapa-del-delito.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/delitos/delitos.csv",
    ],
    "arbolado": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/arbolado-en-espacios-verdes/arbolado-en-espacios-verdes.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/arbolado-publico-lineal/arbolado-publico-lineal.geojson",
    ],
    "cementerios": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/cementerios/cementerios.geojson",
    ],
    "mercados": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/mercados/mercados.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-desarrollo-economico/mercados/mercados.geojson",
    ],
    "baches": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/baches/baches.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/baches/baches.geojson",
    ],
}

client = httpx.Client(follow_redirects=True, timeout=15)

for category, urls in CANDIDATES.items():
    print(f"--- {category} ---")
    for url in urls:
        try:
            r = client.get(url)
            short = url.split("datasets/")[-1]
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                size = len(r.content)
                if "json" in ct or url.endswith(".geojson"):
                    try:
                        features = r.json().get("features", [])
                        keys = list((features[0].get("properties") or {}).keys()) if features else []
                        print(f"  OK [{size//1024}KB, {len(features)} features] {short}")
                        print(f"     keys: {keys[:10]}")
                    except Exception:
                        print(f"  OK [{size//1024}KB] {short} (no JSON)")
                else:
                    lines = r.text.split("\n")
                    print(f"  OK [{size//1024}KB, {len(lines)} lineas] {short}")
                    print(f"     header: {lines[0][:120]}")
            else:
                print(f"  {r.status_code} {short}")
        except Exception as e:
            print(f"  ERR {e} — {url.split('datasets/')[-1]}")
    print()

client.close()
