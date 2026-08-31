"""Agenda oficial de Música GCBA; publica eventos aún vigentes en CABA."""
import argparse, asyncio, csv, io, sys
from datetime import date
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value

SUPPORTS_SOURCE_CONTRACT = True

URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-cultura/eventos-direccion-general-musica/calendario-de-eventos-dir-gral-de-musica.csv"

def clean(v): return "" if v is None else str(v).strip()

def current(v):
 try: return date.fromisoformat(clean(v)) >= date.today()
 except ValueError: return False

def num(v):
 try: return float(clean(v))
 except ValueError: return None

def parse_args():
 p = argparse.ArgumentParser(description="Scraper GCBA Agenda de música (CABA)")
 add_source_arguments(p)
 return p.parse_args()

async def main():
 args = parse_args()
 candidates = []
 async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
  r = await c.get(URL); r.raise_for_status()
  rows = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", "replace")))
  for row in rows:
   if not current(row.get("fecha_hasta") or row.get("fecha_desde")): continue
   if not record_in_scope(lat=num(row.get("lat")), lng=num(row.get("long")), row_neighborhood=clean(row.get("barrio")), row_commune=clean(row.get("comuna")),
                          scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
    continue
   title = normalize_name(clean(row.get("evento")))
   if title: candidates.append({"name": f"Agenda Música {title} - {clean(row.get('fecha_desde'))}", "entity_type": "Event", "subtype": "music_event", "lat": num(row.get("lat")), "lng": num(row.get("long")), "origin_url": URL, "row": row})
 candidates = bounded(candidates, args.limit)
 print(f"Agenda de música vigente ({args.scope}): {len(candidates)}")
 if not args.write: return
 conn = await get_conn()
 try:
  sid = await get_source_id(conn, "ba_data"); ids = await bulk_get_or_create_entities(conn, candidates); props = []
  for x in candidates:
   for key in ("evento", "fecha_desde", "fecha_hasta", "dia_sem", "descripcion", "direccion", "barrio", "comuna", "observaciones"):
    if clean(x["row"].get(key)): props.append({"entity_id": ids[x["name"]], "key": {"evento": "title", "fecha_desde": "start_date", "fecha_hasta": "end_date", "dia_sem": "days", "descripcion": "description", "direccion": "address", "barrio": "neighborhood", "comuna": "commune", "observaciones": "observations"}[key], "value": normalize_value(x["row"][key]), "value_type": "date" if key in {"fecha_desde", "fecha_hasta"} else "string", "confidence": .95, "origins": [URL]})
  await bulk_upsert_properties(conn, props, sid); await mark_source_synced(conn, sid)
 finally: await conn.close()

if __name__ == "__main__": asyncio.run(main())
