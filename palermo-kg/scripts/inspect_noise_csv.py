"""Inspecciona mediciones de ruido CSV."""
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

def main():
    inspect_csv(
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_diurno.csv",
        "Medicion Ruido Diurno CSV"
    )
    inspect_csv(
        "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_nocturno.csv",
        "Medicion Ruido Nocturno CSV"
    )

if __name__ == "__main__":
    main()
