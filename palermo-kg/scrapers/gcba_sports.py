"""Ingesta oficial de polideportivos y programas deportivos GCBA en Palermo."""
import argparse, asyncio, csv, io, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value

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

async def main():
 parser=argparse.ArgumentParser(); parser.add_argument("--write",action="store_true"); args=parser.parse_args(); candidates=[]
 async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
  for subtype, url in URLS.items():
   for row in await fetch(client, url):
    lat,lng=num(row.get("lat")),num(row.get("long"))
    if not palermo(row,lat,lng): continue
    title=clean(row.get("nom") or row.get("programa")); venue=clean(row.get("sede"))
    name=normalize_name(f"{title} - {venue}" if venue else title)
    if not name: continue
    candidates.append({"name":name,"entity_type":"Facility" if subtype=="sports_center" else "Event","subtype":subtype,"lat":lat,"lng":lng,"origin_url":url,"values":(("address",clean(row.get("dir") or row.get("calle_nombre")),"string"),("neighborhood",clean(row.get("barr") or row.get("barrio")),"string"),("activity",clean(row.get("act") or row.get("actividad")),"string"),("hours",clean(row.get("horario")),"string"),("phone",clean(row.get("tel") or row.get("telefono")),"string"),("website",clean(row.get("web")),"url"))})
 print(f"Deportes GCBA en Palermo: {len(candidates)}")
 if not args.write: return
 conn=await get_conn()
 try:
  sid=await get_source_id(conn,"ba_data"); ids=await bulk_get_or_create_entities(conn,candidates); props=[]
  for c in candidates:
   for key,value,value_type in c["values"]:
    if clean(value): props.append({"entity_id":ids[c["name"]],"key":key,"value":normalize_value(value),"value_type":value_type,"confidence":.95,"origins":[c["origin_url"]]})
  await bulk_upsert_properties(conn,props,sid); await mark_source_synced(conn,sid)
 finally: await conn.close()
if __name__=="__main__": asyncio.run(main())
