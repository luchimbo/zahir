"""Comisarías vecinales de CABA desde GCBA."""
import argparse,asyncio,sys
from pathlib import Path
import httpx
ROOT_DIR=Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:sys.path.insert(0,str(ROOT_DIR))
from scrapers.shared.contract import add_source_arguments,bounded
from scrapers.shared.db_helpers import bulk_get_or_create_entities,bulk_upsert_properties,get_conn,get_source_id,mark_source_synced
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name,normalize_value

SUPPORTS_SOURCE_CONTRACT = True

URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-justicia-y-seguridad/comisarias-policia-ciudad/comisarias_policia.geojson'
def parse_args():
 p=argparse.ArgumentParser(description="Scraper GCBA Comisarías (CABA)")
 add_source_arguments(p);return p.parse_args()
async def main():
 args=parse_args()
 async with httpx.AsyncClient(timeout=60) as c:r=await c.get(URL);r.raise_for_status();fs=r.json()['features']
 cs=[]
 for f in fs:
  x=f['properties']
  co=f.get('geometry',{}).get('coordinates') or []
  neighborhood=clean(x.get('barrio',''))
  commune=str(x.get('comuna','') or '')
  if not record_in_scope(lat=co[1] if len(co)>1 else None,lng=co[0] if co else None,row_neighborhood=neighborhood,row_commune=commune,scope=args.scope,neighborhood=args.neighborhood,commune=args.commune):continue
  name=normalize_name(x.get('nombre',''))
  if name:cs.append({'name':name,'entity_type':'Facility','subtype':'police_station','lat':co[1] if len(co)>1 else None,'lng':co[0] if co else None,'origin_url':URL,'values':(('address',x.get('direccion','')),('phone',x.get('telefonos','')),('neighborhood',neighborhood),('commune',commune))})
 cs=bounded(cs,args.limit)
 print(f"Comisarías (scope={args.scope}): {len(cs)}")
 if not args.write:return
 conn=await get_conn()
 try:
  sid=await get_source_id(conn,'ba_data');ids=await bulk_get_or_create_entities(conn,cs);props=[]
  for c in cs:
   for k,v in c['values']:
    if v:props.append({'entity_id':ids[c['name']],'key':k,'value':normalize_value(v),'value_type':'string','confidence':.95,'origins':[URL]})
  await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=='__main__':asyncio.run(main())
def clean(v):return '' if v is None else str(v).strip()
