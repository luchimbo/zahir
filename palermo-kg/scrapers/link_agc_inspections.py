"""Enlaza fiscalizaciones AGC con organizaciones sólo por dirección exacta.

La relación RELATED_TO representa co-ubicación verificada, no titularidad ni
resultado de la inspección. Es idempotente y conserva la URL oficial como origen.
"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import get_conn

ORIGIN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/fiscalizaciones/inspecciones_realizadas_2024.csv"

SQL = """
SELECT DISTINCT i.id AS inspection_id, o.id AS organization_id
FROM entities i
JOIN properties ip ON ip.entity_id = i.id AND ip.key = 'address'
JOIN properties op ON lower(trim(op.value)) = lower(trim(ip.value)) AND op.key = 'address'
JOIN entities o ON o.id = op.entity_id
WHERE i.subtype = 'agc_inspection'
  AND i.canonical_id IS NULL
  AND o.entity_type = 'Organization'
  AND o.canonical_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM relationships r
      WHERE r.from_entity_id = i.id AND r.to_entity_id = o.id
        AND r.relationship_type = 'RELATED_TO'
  )
"""


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    conn = await get_conn()
    try:
        pairs = await conn.fetch(SQL)
        print(f"Relaciones por coincidencia exacta de dirección: {len(pairs)}")
        if args.write and pairs:
            await conn.executemany(
                """INSERT INTO relationships
                   (from_entity_id, relationship_type, to_entity_id, confidence, origins, direction)
                   VALUES ($1, 'RELATED_TO', $2, 0.75, $3, 'directed')""",
                [(row["inspection_id"], row["organization_id"], [ORIGIN]) for row in pairs],
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
