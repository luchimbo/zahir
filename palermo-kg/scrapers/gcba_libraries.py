"""Bibliotecas públicas de CABA; convierte coordenadas GCBA con USIG."""
import argparse, asyncio, sys
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.usig import CONVERTER_URL

SUPPORTS_SOURCE_CONTRACT = True

URL = 'https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-cultura/bibliotecas/bibliotecas.geojson'

def clean(v): return '' if v is None else str(v).strip()

def parse_args():
 p = argparse.ArgumentParser(description="Scraper GCBA Bibliotecas públicas (CABA)")
 add_source_arguments(p)
 return p.parse_args()

async def main():
 args = parse_args()
 candidates = []
 async with httpx.AsyncClient(timeout=60) as c:
  r = await c.get(URL); r.raise_for_status()
  for f in r.json()['features']:
   x = f.get('properties') or {}
   co = f.get('geometry', {}).get('coordinates') or []
   lat = lng = None
   if len(co) > 1:
    q = await c.get(CONVERTER_URL, params={'x': co[0], 'y': co[1], 'output': 'lonlat'})
    try:
     result = q.json()['resultado']; lng = float(result['x']); lat = float(result['y'])
    except (KeyError, TypeError, ValueError): pass
   if not record_in_scope(lat=lat, lng=lng, row_neighborhood=clean(x.get('bar')), row_commune=clean(x.get('com')),
                           scope=args.scope, neighborhood=args.neighborhood, commune=args.commune):
    continue
   name = normalize_name(clean(x.get('nam')))
   if name:
    candidates.append({'name': name, 'entity_type': 'Facility', 'subtype': 'library', 'lat': lat, 'lng': lng, 'origin_url': URL,
     'values': (('address', clean(x.get('dir'))), ('phone', clean(x.get('tel'))), ('website', clean(x.get('web'))), ('library_type', clean(x.get('tip'))), ('neighborhood', clean(x.get('bar'))), ('commune', clean(x.get('com'))))})
 candidates = bounded(candidates, args.limit)
 print(f"Bibliotecas ({args.scope}): {len(candidates)}")
 if not args.write: return
 conn = await get_conn()
 try:
  sid = await get_source_id(conn, 'ba_data'); ids = await bulk_get_or_create_entities(conn, candidates); props = []
  for c in candidates:
   for k, v in c['values']:
    if v: props.append({'entity_id': ids[c['name']], 'key': k, 'value': normalize_value(v), 'value_type': 'url' if k == 'website' else 'string', 'confidence': .95, 'origins': [URL]})
  await bulk_upsert_properties(conn, props, sid); await mark_source_synced(conn, sid)
 finally: await conn.close()

if __name__ == '__main__': asyncio.run(main())
