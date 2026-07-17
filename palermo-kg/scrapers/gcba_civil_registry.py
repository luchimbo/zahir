"""Sedes del Registro Civil y Centros de Documentación Rápida de Palermo."""
import argparse
import asyncio
import csv
import io
import sys
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value

URLS = [
 "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-gobierno/registro-civil/centros-de-documentacion-rapida.csv",
 "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-gobierno/registro-civil/sedes-registro-civil.csv",
]

def clean(v): return "" if v is None else str(v).strip()
def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

async def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--write',action='store_true'); args=parser.parse_args()
    candidates=[]
    async with httpx.AsyncClient(timeout=60) as client:
        for url in URLS:
            r=await client.get(url); r.raise_for_status()
            rows=csv.DictReader(io.StringIO(r.content.decode('utf-8-sig','replace')),delimiter=';')
            for row in rows:
                if clean(row.get('BARRIO')).upper()!='PALERMO' and clean(row.get('COMUNA')).upper()!='COMUNA 14': continue
                name=normalize_name(clean(row.get('CENTRO RAPIDO')) or clean(row.get('SEDE')) or clean(row.get('NOMBRE')))
                address=clean(row.get('DIRECCION'))
                if not name or not address: continue
                candidates.append({'name':f"Registro Civil {name} - {address}",'entity_type':'Facility','subtype':'civil_registry_office',
                  'lat':num(row.get('LAT')),'lng':num(row.get('LNG')),'origin_url':url,
                  'values':(('address',address),('phone',clean(row.get('TEL'))),('hours_open',clean(row.get('HORARIO'))),('services',clean(row.get('TRAMITE'))),('neighborhood','Palermo'))})
    print(f"Sedes de Registro Civil/CDR en Palermo: {len(candidates)}")
    if not args.write: return
    conn=await get_conn()
    try:
        sid=await get_source_id(conn,'ba_data'); ids=await bulk_get_or_create_entities(conn,candidates); props=[]
        for c in candidates:
            for k,v in c['values']:
                if v: props.append({'entity_id':ids[c['name']],'key':k,'value':normalize_value(v),'value_type':'string','confidence':.95,'origins':[c['origin_url']]})
        await bulk_upsert_properties(conn,props,sid); await mark_source_synced(conn,sid)
    finally: await conn.close()
if __name__=='__main__': asyncio.run(main())
