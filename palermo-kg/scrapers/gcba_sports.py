"""Ingesta oficial de polideportivos y programas deportivos GCBA en CABA."""
import argparse, asyncio, csv, io, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scrapers.shared.contract import SourceResult, add_source_arguments, bounded
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, ensure_source, get_conn, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.tabular_source import _in_scope

URLS = {
 "sports_center": "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/vicejefatura-de-gobierno/polideportivos/polideportivos.csv",
 "sports_program": "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/vicejefatura-de-gobierno/programas-deportivos/programas_deportivos.csv",
}
BBOX = (-34.615, -34.555, -58.455, -58.390)
def clean(v): return "" if v is None else str(v).strip()
def num(v):
 try: return float(clean(v).replace(",", "."))
 except ValueError: return None
def palermo(row, lat, lng):
 return "PALERMO" in clean(row.get("barr") or row.get("barrio")).upper() or (lat is not None and lng is not None and BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lng <= BBOX[3])
async def fetch(client, url):
 r = await client.get(url); r.raise_for_status()
 text = r.content.decode("utf-8-sig", "replace")
 delimiter = ";" if text.partition("\n")[0].count(";") >= text.partition("\n")[0].count(",") else ","
 return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))

SUPPORTS_SOURCE_CONTRACT = True

async def main():
 parser=argparse.ArgumentParser(); add_source_arguments(parser); args=parser.parse_args(); candidates=[]; result=SourceResult()
 async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
  for subtype, url in URLS.items():
   rows = await fetch(client, url); result.seen += len(rows)
   for row in rows:
    lat,lng=num(row.get("lat")),num(row.get("long"))
    if not _in_scope(row, lat, lng, scope=args.scope, neighborhood=args.neighborhood, commune=args.commune): continue
    title=clean(row.get("nom") or row.get("programa")); venue=clean(row.get("sede"))
    name=normalize_name(f"{title} - {venue}" if venue else title)
    if not name: continue
    address = clean(row.get("dir") or row.get("calle_nombre"))
    candidates.append({"name":name,"identity_key":f"{name}|{address}|{lat}|{lng}","entity_type":"Facility" if subtype=="sports_center" else "Event","subtype":subtype,"lat":lat,"lng":lng,"origin_url":url,"values":(("address",address,"string"),("neighborhood",clean(row.get("barr") or row.get("barrio")),"string"),("activity",clean(row.get("act") or row.get("actividad")),"string"),("hours",clean(row.get("horario")),"string"),("phone",clean(row.get("tel") or row.get("telefono")),"string"),("website",clean(row.get("web")),"url"))})
 candidates=bounded(candidates,args.limit); result.accepted=len(candidates); result.coverage={"scope":args.scope,"accepted_records":len(candidates)}
 print(f"Deportes GCBA en {args.scope}: {len(candidates)}")
 if not args.write: return result
 conn=await get_conn()
 try:
  sid=await ensure_source(conn,"gcba_sports","https://data.buenosaires.gob.ar",1); ids=await bulk_get_or_create_entities(conn,candidates); props=[]
  for c in candidates:
   for key,value,value_type in c["values"]:
    if clean(value): props.append({"entity_id":ids[c["name"]],"key":key,"value":normalize_value(value),"value_type":value_type,"confidence":.95,"origins":[c["origin_url"]]})
  await bulk_upsert_properties(conn,props,sid); await mark_source_synced(conn,sid); result.written=len(candidates)
 finally: await conn.close()
 return result
if __name__=="__main__": asyncio.run(main())
