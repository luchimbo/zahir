"""Inspecciona el arbolado publico lineal."""
import httpx
import csv
import io

def main():
    url = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/atencion-ciudadana/arbolado-publico-lineal/arbolado-publico-lineal-2017-2018.csv"
    print("Fetching head of lineal trees...")
    try:
        # Fetch first 100KB to get headers and some rows
        headers = {"Range": "bytes=0-102400"}
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=20)
        # Parse CSV from the partial content
        text = r.content.decode("utf-8-sig", "replace")
        # Split lines, discard last line if it's incomplete
        lines = text.splitlines()
        if len(lines) > 1:
            lines = lines[:-1]
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        rows = list(reader)
        print(f"Total parsed sample rows: {len(rows)}")
        print(f"Keys: {list(rows[0].keys()) if rows else []}")
        if rows:
            print(f"Sample row: {dict(rows[0])}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
