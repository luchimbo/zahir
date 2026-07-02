"""Prueba las URLs CSV/GeoJSON encontradas via CKAN."""
import httpx

CANDIDATES = {
    "ecobici_estaciones": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/estaciones-bicicletas-publicas/estaciones-bicicletas-publicas.csv",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/estaciones-bicicletas-publicas/nuevas-estaciones-bicicletas-publicas.csv",
    ],
    "arbolado": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/atencion-ciudadana/arbolado-publico-lineal/arbolado-publico-lineal.csv",
    ],
    "wifi": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/puntos-wi-fi-publico/puntos-wi-fi-publico.csv",
    ],
    "cajeros": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/cajeros-automaticos/cajeros-automaticos.csv",
    ],
    "comisarias": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/divisiones-comisarias-vecinales/divisiones-comisarias-vecinales.csv",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/departamentos-comisarias-comunales/departamentos-comisarias-comunales.csv",
    ],
    "obras": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/obras-registradas/obras-registradas.csv",
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-legal-y-tecnica/ba-obras/dataset_baobras.csv",
    ],
    "mercado_inmobiliario": [
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/instituto-de-vivienda/mercado-inmobiliario/actividades-inmobiliarias.csv",
    ],
}

client = httpx.Client(follow_redirects=True, timeout=20)

for category, urls in CANDIDATES.items():
    print(f"--- {category} ---")
    for url in urls:
        try:
            r = client.get(url)
            short = url.split("datasets/")[-1]
            if r.status_code == 200:
                lines = r.text.split("\n")
                print(f"  OK [{len(r.content)//1024}KB, {len(lines)} lineas] {short}")
                print(f"     header: {lines[0][:150]}")
                if len(lines) > 1:
                    print(f"     row1:   {lines[1][:150]}")
            else:
                print(f"  {r.status_code} {short}")
        except Exception as e:
            print(f"  ERR {e}")
    print()

client.close()
