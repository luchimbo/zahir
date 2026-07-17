"""Enriquece SMP ya presentes con el Código Urbanístico GCBA 2024."""
import argparse, asyncio, csv, sys
from collections import defaultdict
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scrapers.shared.db_helpers import bulk_upsert_properties,get_conn,get_source_id,mark_source_synced
URL='https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/codigo-urbanistico/codigo-urbanistico.csv'
FIELDS={'uni_edif_1':'urban_height_max_m','uso_1':'urban_use_code','dist_1_grp':'urban_district','zona_1':'urban_zone','catalogado':'heritage_catalogued','rh':'hydric_risk','lep':'particular_building_line','ensanche':'future_widening','apertura':'future_opening','anac':'aeroparque_approach_area','ci_digital':'digital_belt'}
async def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();conn=await get_conn()
 try:
  known=defaultdict(set)
  for r in await conn.fetch("SELECT entity_id::text,upper(value) smp FROM properties WHERE key='smp'"):known[r['smp']].add(r['entity_id'])
  found={}
  async with httpx.AsyncClient(timeout=180) as c:
   async with c.stream('GET',URL) as res:
    res.raise_for_status();lines=[x async for x in res.aiter_lines()]
  for r in csv.DictReader(lines):
   if r.get('smp','').upper() in known:found[r['smp'].upper()]=r
  print(f'SMP con Código Urbanístico: {len(found)}')
  if not args.write:return
  sid=await get_source_id(conn,'ba_data');props=[]
  for smp,row in found.items():
   for source,key in FIELDS.items():
    value=row.get(source)
    if value not in (None,'','0','0.0'):
     typ='number' if source=='uni_edif_1' else ('boolean' if source in {'catalogado','rh','lep','ensanche','apertura','anac','ci_digital'} else 'string')
     props += [{'entity_id':eid,'key':key,'value':str(value),'value_type':typ,'confidence':.95,'origins':[URL]} for eid in known[smp]]
  await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=='__main__':asyncio.run(main())
