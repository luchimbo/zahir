"""Parcelas catastrales oficiales de CABA; conserva SMP para cruces urbanísticos."""
import argparse, asyncio, csv, re, sys
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scrapers.shared.contract import add_source_arguments
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.geo_scope import record_in_scope

SUPPORTS_SOURCE_CONTRACT = True

URL="https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/parcelas/parcelas_catastrales.csv"
def clean(v): return "" if v is None else str(v).strip()
def point(wkt):
 values=re.findall(r"(-?\d+\.\d+)",clean(wkt))
 if len(values)<2:return None,None
 lng,lat=float(values[0]),float(values[1]); return (lat,lng) if -35<lat<-34 and -59<lng<-58 else (None,None)

def parse_args():
 p=argparse.ArgumentParser()
 add_source_arguments(p)
 p.add_argument("--stream-limit",type=int,default=0,help="early stop de streaming para costo/depuración")
 return p.parse_args()

async def main():
 args=parse_args()
 async with httpx.AsyncClient(timeout=240,follow_redirects=True) as c:
  candidates=[]
  async with c.stream("GET",URL) as r:
   r.raise_for_status(); lines=r.aiter_lines(); header=next(csv.reader([await anext(lines)]))
   async for line in lines:
    values=next(csv.reader([line])); row=dict(zip(header,values))
    smp=clean(row.get("smp"))
    if not smp:continue
    lat,lng=point(row.get("geometry"))
    if not record_in_scope(lat=lat,lng=lng,row_neighborhood=clean(row.get("barrio")),row_commune=clean(row.get("comuna")),scope=args.scope,neighborhood=args.neighborhood,commune=args.commune):
     continue
    candidates.append({"name":f"Parcela {smp}","entity_type":"Parcel","subtype":"cadastral_parcel","lat":lat,"lng":lng,"origin_url":URL,"smp":smp,"row":row})
    if args.stream_limit and len(candidates)>=max(args.stream_limit,args.limit or 0):break
  print(f"Parcelas ({args.scope}): {len(candidates)} (limit={args.limit})")
  if not args.write:return
  conn=await get_conn()
  try:
   sid=await get_source_id(conn,"ba_data");ids=await bulk_get_or_create_entities(conn,candidates);props=[]
   for c in candidates:
    for key,value in (("smp",c["smp"]),("cadastral_section",clean(c["row"].get("seccion"))),("cadastral_block",clean(c["row"].get("manzana"))),("cadastral_parcel",clean(c["row"].get("parcela"))),("commune",clean(c["row"].get("comuna"))),("neighborhood",clean(c["row"].get("barrio")))):
     if value:props.append({"entity_id":ids[c["name"]],"key":key,"value":value,"value_type":"string","confidence":.95,"origins":[URL]})
   await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
  finally:await conn.close()
if __name__=="__main__":asyncio.run(main())
