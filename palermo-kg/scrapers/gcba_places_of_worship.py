"""Lugares de culto de Palermo desde datos abiertos GCBA."""
import argparse, asyncio, csv, io, sys
from pathlib import Path
import httpx
ROOT_DIR=Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:sys.path.insert(0,str(ROOT_DIR))
from scrapers.shared.db_helpers import bulk_get_or_create_entities,bulk_upsert_properties,get_conn,get_source_id,mark_source_synced
from scrapers.shared.normalizer import normalize_name,normalize_value
URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-general-y-relaciones-internacionales/lugares-culto/lugares-de-culto.csv'
def clean(v):return '' if v is None else str(v).strip()
def num(v):
 try:return float(v)
 except (TypeError,ValueError):return None
async def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args()
 async with httpx.AsyncClient(timeout=60) as c:
  r=await c.get(URL);r.raise_for_status();text=r.content.decode('utf-8-sig','replace');d=csv.Sniffer().sniff(text[:4096],delimiters=';,|');rows=csv.DictReader(io.StringIO(text),delimiter=d.delimiter)
  cs=[]
  for x in rows:
   if clean(x.get('barrio')).upper()!='PALERMO':continue
   name=normalize_name(clean(x.get('nombre_institucion')))
   if name:cs.append({'name':name,'entity_type':'Facility','subtype':'place_of_worship','lat':num(x.get('lat')),'lng':num(x.get('long')),'origin_url':URL,'values':(('address',clean(x.get('domicilio'))),('faith_group',clean(x.get('grupo'))),('denomination',clean(x.get('culto'))),('neighborhood','Palermo'))})
 print(f"Lugares de culto de Palermo: {len(cs)}")
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
