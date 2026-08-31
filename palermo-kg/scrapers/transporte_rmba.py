"""Estaciones de subte de Transporte Nación dentro del alcance elegido (CABA por defecto)."""
import argparse, asyncio, json, xml.etree.ElementTree as ET
import httpx
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.geo_scope import record_in_scope
SUPPORTS_SOURCE_CONTRACT=True
URL="https://datos.transporte.gob.ar/dataset/f87b93d4-ade2-44fc-a409-d3736ba9f3ba/resource/f5fe0a3d-025b-4b40-af8f-53a83cc9205f/download/estacionesdesubte.kml"
ORIGIN="https://datos.gob.ar/dataset/transporte-recorridos-lineas-transporte-region-metropolitana-buenos-aires-rmba"
def parse_args():
 p=argparse.ArgumentParser();add_source_arguments(p);return p.parse_args()
async def main():
 args=parse_args()
 async with httpx.AsyncClient(timeout=90,follow_redirects=True,verify=False) as c:data=(await c.get(URL)).content
 root=ET.fromstring(data); ns={"k":"http://www.opengis.net/kml/2.2"}; stations=[]
 for node in root.findall('.//k:Placemark',ns):
  name=(node.findtext('k:name',default='',namespaces=ns)).strip(); coord=node.findtext('.//k:coordinates',default='',namespaces=ns).strip()
  try:lng,lat,*_=map(float,coord.split(','))
  except ValueError:continue
  if not name:continue
  if not record_in_scope(lat=lat,lng=lng,scope=args.scope,neighborhood=args.neighborhood,commune=args.commune):continue
  stations.append((name,lat,lng))
 stations=bounded(stations,args.limit)
 print(f"Transporte RMBA: {len(stations)} estaciones | scope={args.scope} | write={args.write}")
 if not stations:
  print("Sin escritura: el KML oficial no publica estaciones; no se crean entidades anónimas."); return
 if not args.write:return
 conn=await get_conn()
 try:
  source=await get_source_id(conn,"transporte_rmba")
  records=[{"name":normalize_name(name),"entity_type":"Transport","subtype":"subte_station","lat":lat,"lng":lng,"origin_url":ORIGIN} for name,lat,lng in stations]
  ids=await bulk_get_or_create_entities(conn,records)
  props=[{"entity_id":ids[n],"key":"historical_status","value":"Historical Transport Network","value_type":"string","confidence":.7,"origins":[ORIGIN]} for n,*_ in stations]
  await bulk_upsert_properties(conn,props,source)
  if args.scope=="palermo":
   palermo=await conn.fetchval("SELECT id FROM entities WHERE entity_type='Location' AND LOWER(name) LIKE '%palermo%' AND canonical_id IS NULL LIMIT 1")
   if palermo:
    for name,*_ in stations:
     await conn.execute("""INSERT INTO relationships(from_entity_id,relationship_type,to_entity_id,confidence,origins,direction)
      SELECT $1,'CONNECTS_TO',$2,.7,$3,'directed' WHERE NOT EXISTS(SELECT 1 FROM relationships WHERE from_entity_id=$1 AND relationship_type='CONNECTS_TO' AND to_entity_id=$2)""",ids[normalize_name(name)],palermo,json.dumps([ORIGIN]))
  await mark_source_synced(conn,source)
 finally:await conn.close()
if __name__=="__main__":
 asyncio.run(main())
