"""Inspecciona una fila de muestra de cada dataset ambiental."""
import httpx
import csv
import io

def inspect_csv(url, name, delimiter=','):
    print(f"=== {name} ===")
    try:
        r = httpx.get(url, follow_redirects=True, timeout=20)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig", "replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        if rows:
            print(f"Total rows: {len(rows)}")
            print(f"Keys: {list(rows[0].keys())}")
            print(f"Sample row: {dict(rows[0])}")
        else:
            print("Empty dataset")
    except Exception as e:
        print(f"Error: {e}")
    print()

def inspect_geojson(url, name):
    print(f"=== {name} ===")
    try:
        r = httpx.get(url, follow_redirects=True, timeout=20)
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        print(f"Total features: {len(features)}")
        if features:
            print(f"Keys: {list(features[0]['properties'].keys())}")
            print(f"Sample geometry: {features[0].get('geometry')}")
            print(f"Sample properties: {features[0]['properties']}")
        else:
            print("Empty features")
    except Exception as e:
        print(f"Error: {e}")
    print()

def main():
    # 1. Anegamiento (CSV)
    inspect_csv(
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/sitios-posibles-anegamiento/sitios-pasibles-de-anegamiento-por-precipitacion-2019.csv",
        "Anegamiento 2019",
        delimiter=";"
    )
    # 2. Calidad de aire - estaciones (CSV)
    inspect_csv(
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/calidad-aire/estaciones-ambientales.csv",
        "Estaciones Ambientales",
        delimiter=";"
    )
    # 3. Ruido diurno (GeoJSON o CSV)
    inspect_geojson(
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_diurno.geojson",
        "Ruido Diurno"
    )
    # 4. Arbolado espacios verdes (CSV)
    inspect_csv(
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/arbolado-espacios-verdes/arbolado-en-espacios-verdes.csv",
        "Arbolado Espacios Verdes",
        delimiter=";"
    )

if __name__ == "__main__":
    main()
