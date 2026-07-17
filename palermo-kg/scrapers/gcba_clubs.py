"""Clubes de Palermo desde el registro abierto GCBA."""
import argparse, asyncio, sys
from pathlib import Path
import httpx
ROOT_DIR=Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path: sys.path.insert(0,str(ROOT_DIR))
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value
URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/vicejefatura-de-gobierno/clubes/clubes.geojson'
def clean(v): return '' if v is None else str(v).strip()
async def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args()
 async with httpx.AsyncClient(timeout=60) as c:
  r=await c.get(URL);r.raise_for_status();fs=r.json()['features']
 candidates=[]
 for f in fs:
  x=f.get('properties') or {}
  if clean(x.get('barrio')).upper()!='PALERMO': continue
  name=normalize_name(clean(x.get('nombre'))); coords=(f.get('geometry') or {}).get('coordinates') or []
  if not name: continue
  candidates.append({'name':name,'entity_type':'Facility','subtype':'sports_club','lat':coords[1] if len(coords)>1 else None,'lng':coords[0] if coords else None,'origin_url':URL,
   'values':(('address',clean(x.get('direccion'))),('phone',clean(x.get('telefono'))),('website',clean(x.get('web'))),('sports',clean(x.get('actividade'))),('facilities',clean(x.get('instalacio'))),('neighborhood','Palermo'))})
 print(f"Clubes de Palermo: {len(candidates)}")
 if not args.write:return
 conn=await get_conn()
 try:
  sid=await get_source_id(conn,'ba_data');ids=await bulk_get_or_create_entities(conn,candidates);props=[]
  for c in candidates:
   for k,v in c['values']:
    if v:props.append({'entity_id':ids[c['name']],'key':k,'value':normalize_value(v),'value_type':'url' if k=='website' else 'string','confidence':.95,'origins':[URL]})
  await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=='__main__':asyncio.run(main())
