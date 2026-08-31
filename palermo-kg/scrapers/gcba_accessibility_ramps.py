"""Rampas de accesibilidad oficiales de CABA."""
import argparse,asyncio,csv,io,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scrapers.shared.db_helpers import bulk_get_or_create_entities,bulk_upsert_properties,get_conn,get_source_id,mark_source_synced
from scrapers.shared.contract import add_source_arguments,bounded
from scrapers.shared.geo_scope import record_in_scope
SUPPORTS_SOURCE_CONTRACT=True
URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-espacio-publico-e-higiene-urbana/rampas-accesibilidad/rampas-de-accesibilidad-relevamiento-2016.csv'
def parse_args():
 p=argparse.ArgumentParser();add_source_arguments(p);return p.parse_args()
def f(v):
 try:return float(v)
 except:return None
async def main():
 args=parse_args()
 async with httpx.AsyncClient(timeout=60) as c:r=await c.get(URL);r.raise_for_status();rows=csv.DictReader(io.StringIO(r.content.decode('utf-8-sig','replace')),delimiter=';');cs=[]
 for x in rows:
  lng,lat=f(x.get('X')),f(x.get('Y'))
  if lat is None or lng is None:continue
  if not record_in_scope(lat=lat,lng=lng,scope=args.scope,neighborhood=args.neighborhood,commune=args.commune):continue
  ident=x.get('ID');address=x.get('DOM_NORMA') or x.get('CALLE','')
  cs.append({'name':f'Rampa de Accesibilidad {ident} - {address}','entity_type':'Facility','subtype':'accessibility_ramp','lat':lat,'lng':lng,'origin_url':URL,'values':(('address',address),('status',x.get('ESTADO','')),('intervention_month',x.get('MES','')),('intervention_period',x.get('SEMANA','')),('street',x.get('CALLE','')),('street_number',x.get('ALTURA','')))})
 cs=bounded(cs,args.limit)
 print(f'Rampas de accesibilidad: {len(cs)} | scope={args.scope} | write={args.write}')
 if not args.write:return
 conn=await get_conn()
 try:
  sid=await get_source_id(conn,'ba_data');ids=await bulk_get_or_create_entities(conn,cs);props=[]
  for c in cs:
   for k,v in c['values']:
    if v:props.append({'entity_id':ids[c['name']],'key':k,'value':str(v),'value_type':'string','confidence':.95,'origins':[URL]})
  await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=='__main__':asyncio.run(main())
