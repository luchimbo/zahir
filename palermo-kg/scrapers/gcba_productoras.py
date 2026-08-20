"""Productoras de eventos masivos AGC, geocodificadas antes de filtrar Palermo."""
import argparse, asyncio, csv, io, sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scrapers.shared.db_helpers import bulk_get_or_create_entities,bulk_upsert_properties,get_conn,get_source_id,mark_source_synced
from scrapers.shared.normalizer import normalize_name,normalize_value
from scrapers.shared.usig import geocode_address
URL="https://cdn.buenosaires.gob.ar/datosabiertos/datasets/agencia-gubernamental-de-control/productoras-eventos-masivos/productoras-de-eventos-masivos.csv"
def clean(v):return "" if v is None else str(v).strip()
def palermo(g):return g and -34.615<=g.lat<=-34.555 and -58.455<=g.lng<=-58.390
async def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");p.add_argument("--limit",type=int,default=0);args=p.parse_args()
 async with httpx.AsyncClient(timeout=90,follow_redirects=True) as c:
  r=await c.get(URL);r.raise_for_status();text=r.content.decode("utf-8-sig","replace");rows=list(csv.DictReader(io.StringIO(text),delimiter=";"))
 print(f"Productoras AGC: {len(rows)} registros oficiales")
 if not args.write:return
 if args.limit:rows=rows[:args.limit]
 async with httpx.AsyncClient(timeout=30) as c:
  locations=await asyncio.gather(*(geocode_address(c,clean(x.get("DIRECCION"))) for x in rows))
 candidates=[]
 for row,geo in zip(rows,locations):
  name=normalize_name(clean(row.get("RAZON SOCIAL")))
  if not name or not palermo(geo):continue
  candidates.append({"name":name,"entity_type":"Organization","subtype":"event_producer","lat":geo.lat,"lng":geo.lng,"origin_url":URL,"values":(("address",clean(row.get("DIRECCION")),"string"),("phone",clean(row.get("TELEFONO")),"string"),("registration_resolution",clean(row.get("ULTIMA DISPOSICION")),"string"),("registration_expiry",clean(row.get("VENCIMIENTO INSCRIPCION")),"string"))})
 print(f"Productoras en Palermo: {len(candidates)}")
 conn=await get_conn()
 try:
  sid=await get_source_id(conn,"ba_data");ids=await bulk_get_or_create_entities(conn,candidates);props=[]
  for x in candidates:
   for key,value,typ in x["values"]:
    if clean(value):props.append({"entity_id":ids[x["name"]],"key":key,"value":normalize_value(value),"value_type":typ,"confidence":.95,"origins":[URL]})
  await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=="__main__":asyncio.run(main())
