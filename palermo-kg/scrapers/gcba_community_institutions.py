"""Instituciones de colectividades de CABA, fuente oficial GCBA."""
import argparse, asyncio, csv, io, sys
from pathlib import Path
import httpx
ROOT_DIR=Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path: sys.path.insert(0,str(ROOT_DIR))
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value
SUPPORTS_SOURCE_CONTRACT=True
URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/vicejefatura-de-gobierno/instituciones-colectividades/instituciones-de-colectividades.csv'
def clean(v): return '' if v is None else str(v).strip()
def num(v):
    try: return float(v)
    except (TypeError,ValueError): return None
def parse_args():
    p=argparse.ArgumentParser(description="Scraper Instituciones de Colectividades (CABA)")
    add_source_arguments(p); return p.parse_args()
async def main():
    args=parse_args()
    async with httpx.AsyncClient(timeout=60) as c:
     r=await c.get(URL); r.raise_for_status(); rows=csv.DictReader(io.StringIO(r.content.decode('utf-8-sig','replace')),delimiter=',')
     candidates=[]
     for x in rows:
      neighborhood=clean(x.get('barrio')); commune=clean(x.get('comuna'))
      lat=num(x.get('lat')); lng=num(x.get('long'))
      if not record_in_scope(lat=lat,lng=lng,row_neighborhood=neighborhood,row_commune=commune,
                              scope=args.scope,neighborhood=args.neighborhood,commune=args.commune): continue
      name=normalize_name(clean(x.get('nombre'))); address=f"{clean(x.get('calle_nombre'))} {clean(x.get('calle_altura'))}".strip()
      if not name: continue
      candidates.append({'name':name,'entity_type':'Organization','subtype':'community_institution','lat':lat,'lng':lng,'origin_url':URL,
       'values':(('address',address),('phone',clean(x.get('telefono'))),('website',clean(x.get('web'))),('institution_type',clean(x.get('tipo'))),('community',clean(x.get('colectividad'))),('neighborhood',neighborhood),('commune',commune))})
    candidates=bounded(candidates,args.limit)
    print(f"Instituciones comunitarias ({args.scope}): {len(candidates)}")
    if not args.write: return
    conn=await get_conn()
    try:
     sid=await get_source_id(conn,'ba_data'); ids=await bulk_get_or_create_entities(conn,candidates); props=[]
     for c in candidates:
      for k,v in c['values']:
       if v: props.append({'entity_id':ids[c['name']],'key':k,'value':normalize_value(v),'value_type':'url' if k=='website' else 'string','confidence':.95,'origins':[URL]})
     await bulk_upsert_properties(conn,props,sid); await mark_source_synced(conn,sid)
    finally: await conn.close()
if __name__=='__main__': asyncio.run(main())
