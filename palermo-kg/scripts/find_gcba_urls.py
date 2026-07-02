"""Encuentra las URLs correctas de los datasets GCBA y muestra sus keys."""
import httpx

# Farmacias - ya funciona, ver keys
FARMACIAS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-salud/farmacias/farmacias.geojson"

# Intentar variantes de URL para cada dataset
CANDIDATES = {
    "educacion": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/establecimientos-educativos/establecimientos-educativos-de-gestion-estatal.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-educacion/establecimientos-educativos/establecimientos-educativos-de-gestion-privada.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/establecimientos-educativos/establecimientos-educativos.geojson",
    ],
    "salud": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-salud/establecimientos-de-salud/establecimientos-de-salud.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-salud/red-hospitalaria/red-hospitalaria.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-salud/hospitales/hospitales.geojson",
    ],
    "ecobici": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/bicicletas-publicas/bicicletas-publicas.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/estaciones-bicicletas-publicas/estaciones-bicicletas-publicas.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-transporte/ecobici/ecobici-estaciones.geojson",
    ],
    "museos": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-cultura/museos/museos-espacios-culturales.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/museos/museos.geojson",
    ],
    "bibliotecas": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-cultura/bibliotecas/bibliotecas.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/bibliotecas-publicas/bibliotecas-publicas.geojson",
    ],
    "wifi": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-innovacion-y-transformacion-digital/puntos-de-wifi-publico/puntos-de-wifi-publico.geojson",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/wifi-publico/wifi-publico.geojson",
    ],
}

client = httpx.Client(follow_redirects=True, timeout=20)

# Farmacias — ver keys reales
r = client.get(FARMACIAS_URL)
features = r.json().get("features", [])
print(f"FARMACIAS keys: {list(features[0]['properties'].keys())}")
print(f"  sample: {features[0]['properties']}")
print()

# Buscar URLs correctas
for category, urls in CANDIDATES.items():
    print(f"--- {category} ---")
    for url in urls:
        try:
            r = client.get(url)
            if r.status_code == 200:
                f = r.json().get("features", [{}])[0]
                keys = list((f.get("properties") or {}).keys())
                print(f"  OK {url.split('datasets/')[-1]}")
                print(f"     keys: {keys[:8]}")
            else:
                print(f"  {r.status_code} {url.split('datasets/')[-1]}")
        except Exception as e:
            print(f"  ERR {e}")
    print()

client.close()
