"""Estaciones de subte de Transporte Nación que caen dentro de Palermo."""
import argparse, asyncio, json, xml.etree.ElementTree as ET
import httpx
from scrapers.shared.db_helpers import ensure_source,get_conn,get_or_create_entity,mark_source_synced,upsert_property
from scrapers.shared.normalizer import normalize_name
URL="https://datos.transporte.gob.ar/dataset/f87b93d4-ade2-44fc-a409-d3736ba9f3ba/resource/f5fe0a3d-025b-4b40-af8f-53a83cc9205f/download/estacionesdesubte.kml"
ORIGIN="https://datos.gob.ar/dataset/transporte-recorridos-lineas-transporte-region-metropolitana-buenos-aires-rmba"
def inside(lat,lng):return -34.615<=lat<=-34.555 and -58.455<=lng<=-58.390
async def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args()
 async with httpx.AsyncClient(timeout=90,follow_redirects=True,verify=False) as c:data=(await c.get(URL)).content
 root=ET.fromstring(data); ns={"k":"http://www.opengis.net/kml/2.2"}; stations=[]
 for node in root.findall('.//k:Placemark',ns):
  name=(node.findtext('k:name',default='',namespaces=ns)).strip(); coord=node.findtext('.//k:coordinates',default='',namespaces=ns).strip()
  try:lng,lat,*_=map(float,coord.split(','))
  except ValueError:continue
  if name and inside(lat,lng):stations.append((name,lat,lng))
 print(f"Transporte RMBA: {len(stations)} estaciones con identificador Palermo | write={args.write}")
 if not stations:
  print("Sin escritura: el KML oficial no publica nombre/ID de estaciones; no se crean entidades anónimas."); return
 if not args.write:return
 conn=await get_conn()
 try:
  source=await ensure_source(conn,"transporte_rmba",ORIGIN,4); palermo=await conn.fetchval("SELECT id FROM entities WHERE entity_type='Location' AND LOWER(name) LIKE '%palermo%' AND canonical_id IS NULL LIMIT 1")
  for name,lat,lng in stations:
   entity=await get_or_create_entity(conn,normalize_name(name),"Transport","subte_station",lat,lng,origin_url=ORIGIN)
   await upsert_property(conn,entity,"historical_status","Historical Transport Network","string",source,[ORIGIN],.7)
   if palermo: await conn.execute("""INSERT INTO relationships(from_entity_id,relationship_type,to_entity_id,confidence,origins,direction)
    SELECT $1,'CONNECTS_TO',$2,.7,$3,'directed' WHERE NOT EXISTS(SELECT 1 FROM relationships WHERE from_entity_id=$1 AND relationship_type='CONNECTS_TO' AND to_entity_id=$2)""",entity,palermo,json.dumps([ORIGIN]))
  await mark_source_synced(conn,source)
 finally:await conn.close()
if __name__=="__main__":asyncio.run(main())
