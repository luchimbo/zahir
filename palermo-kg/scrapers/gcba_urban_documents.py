"""Enriquece parcelas Palermo con certificados, línea oficial y banda mínima GCBA."""
import argparse, asyncio, csv, io, sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scrapers.shared.db_helpers import bulk_upsert_properties,get_conn,get_source_id,mark_source_synced

SOURCES={
 "certificate":"https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/certificados-urbanisticos/certificados_urbanisticos.csv",
 "official_line":"https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/linea-oficial/linea_oficial.csv",
 "minimum_buildable_band":"https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-desarrollo-urbano/banda-minima-edificable/banda_minima.csv",
}
def clean(v):return "" if v is None else str(v).strip()
async def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args();conn=await get_conn()
 try:
  known={r["value"].upper():r["entity_id"] for r in await conn.fetch("SELECT entity_id,value FROM active_properties WHERE `key`='smp'")}
  props=[]
  async with httpx.AsyncClient(timeout=240,follow_redirects=True) as c:
   for kind,url in SOURCES.items():
    r=await c.get(url);r.raise_for_status();text=r.content.decode("utf-8-sig","replace"); delimiter=";" if text.partition("\n")[0].count(";")>text.partition("\n")[0].count(",") else ","
    for row in csv.DictReader(io.StringIO(text),delimiter=delimiter):
     smp=clean(row.get("smp") or row.get("SMP")).upper()
     entity_id=known.get(smp)
     if not entity_id:continue
     if kind=="certificate": values=(("urban_certificate_year",clean(row.get("ANIO"))),("urban_certificate_number",clean(row.get("NUMERO"))),("urban_certificate_file",clean(row.get("NUMERO_SADE_GEDO"))),("urban_certificate_date",clean(row.get("FECHA_EGRESO"))))
     elif kind=="official_line": values=(("official_line_street",clean(row.get("calle"))),("official_line_source",clean(row.get("fuente"))))
     else: values=(("minimum_buildable_band",clean(row.get("sm"))), ("minimum_buildable_band_source",clean(row.get("fuente"))))
     for key,value in values:
      if value:props.append({"entity_id":entity_id,"key":key,"value":value,"value_type":"string","confidence":.95,"origins":[url]})
  print(f"Propiedades urbanísticas a actualizar: {len(props)}")
  if args.write:
   sid=await get_source_id(conn,"ba_data");await bulk_upsert_properties(conn,props,sid);await mark_source_synced(conn,sid)
 finally:await conn.close()
if __name__=="__main__":asyncio.run(main())
