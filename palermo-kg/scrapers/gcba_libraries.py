"""Bibliotecas públicas de Palermo; convierte coordenadas GKBA con USIG."""
import argparse,asyncio,sys
from pathlib import Path
import httpx
ROOT_DIR=Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:sys.path.insert(0,str(ROOT_DIR))
from scrapers.shared.db_helpers import bulk_get_or_create_entities,bulk_upsert_properties,get_conn,get_source_id,mark_source_synced
from scrapers.shared.normalizer import normalize_name,normalize_value
from scrapers.shared.usig import CONVERTER_URL
URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-cultura/bibliotecas/bibliotecas.geojson'
async def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();cs=[]
 async with httpx.AsyncClient(timeout=60) as c:
  r=await c.get(URL);r.raise_for_status()
  for f in r.json()['features']:
   x=f['properties']
   if str(x.get('bar','')).upper()!='PALERMO':continue
   co=f.get('geometry',{}).get('coordinates') or [];lat=lng=None
   if len(co)>1:
    q=await c.get(CONVERTER_URL,params={'x':co[0],'y':co[1],'output':'lonlat'})
    try: result=q.json()['resultado'];lng=float(result['x']);lat=float(result['y'])
    except (KeyError,TypeError,ValueError):pass
   name=normalize_name(x.get('nam',''))
   if name:cs.append({'name':name,'entity_type':'Facility','subtype':'library','lat':lat,'lng':lng,'origin_url':URL,'values':(('address',x.get('dir','')),('phone',x.get('tel','')),('website',x.get('web','')),('library_type',x.get('tip','')),('neighborhood','Palermo'))})
 print(f"Bibliotecas de Palermo: {len(cs)}")
 if not args.write:return
 conn=await get_conn()
 try:
  sid=await get_source_id(conn,'ba_data');ids=await bulk_get_or_create_entities(conn,cs);props=[]
  for c in cs:
   for k,v in c['values']:
    if v:props.append({'entity_id':ids[c['name']],'key':k,'value':normalize_value(v),'value_type':'url' if k=='website' else 'string','confidence':.95,'origins':[URL]})
  await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=='__main__':asyncio.run(main())
