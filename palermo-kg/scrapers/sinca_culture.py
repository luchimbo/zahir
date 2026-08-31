"""Importa el Mapa Cultural SINCA como registros históricos visibles."""
import argparse, asyncio
import httpx
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, get_source_id, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.geo_scope import record_in_scope

SUPPORTS_SOURCE_CONTRACT = True
API = "https://datos.gob.ar/api/3/action/package_show?id=cultura-mapa-cultural-espacios-culturales"
ORIGIN = "https://www.datos.gob.ar/dataset/cultura-mapa-cultural-espacios-culturales"
KINDS = {"bibliotecas": "biblioteca", "museo": "museo", "teatro": "teatro", "cine": "cine", "librerias": "libreria", "galerias": "galeria_arte", "centros": "centro_cultural", "monumentos": "monumento"}

def parse_args():
    parser = argparse.ArgumentParser(); add_source_arguments(parser); return parser.parse_args()

def pick(row, *keys):
    for key in keys:
        if row.get(key) not in (None, ""): return str(row[key]).strip()
    return ""
def flt(v):
    try: return float(str(v).replace(",", "."))
    except ValueError: return None

async def main():
    args = parse_args()
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        package = (await client.get(API)).json()["result"]
        resources = package.get("resources", [])
        selected = [r for r in resources if any(token in (r.get("name", "") + r.get("description", "")).lower() for token in KINDS)]
        rows = []
        for resource in selected:
            try:
                data = (await client.get(resource["url"])).text
                import csv, io
                for row in csv.DictReader(io.StringIO(data)):
                    lat, lng = flt(pick(row, "latitud", "lat", "latitude")), flt(pick(row, "longitud", "lng", "lon", "longitude"))
                    if not lat or not lng: continue
                    if not record_in_scope(lat=lat, lng=lng, scope=args.scope, neighborhood=args.neighborhood, commune=args.commune): continue
                    rows.append((row, lat, lng, resource["url"]))
            except Exception as exc: print(f"recurso omitido: {exc}")
    rows = bounded(rows, args.limit)
    print(f"{len(rows)} espacios culturales históricos | scope={args.scope} | write={args.write}")
    if not args.write: return
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "sinca")
        records=[]; props=[]
        for row, lat, lng, origin in rows:
            name = normalize_name(pick(row, "nombre", "nombre_espacio", "denominacion"))
            if not name: continue
            category = pick(row, "categoria", "tipo", "subcategoria").lower()
            subtype = next((value for token, value in KINDS.items() if token in category), "espacio_cultural")
            records.append({"name":name,"entity_type":"HistoricalRecord","subtype":subtype,"lat":lat,"lng":lng,"origin_url":origin})
            for key, raw in {"address": pick(row,"direccion","domicilio"), "sinca_category": category,
                             "historical_source_updated_year": pick(row,"actualizacion","anio_actualizacion"),
                             "historical_status": "Historical Source"}.items():
                if raw: props.append((name,key,normalize_value(raw),origin))
        ids=await bulk_get_or_create_entities(conn,records)
        await bulk_upsert_properties(conn,[{"entity_id":ids[name],"key":key,"value":value,"value_type":"string","origins":[origin],"confidence":.65} for name,key,value,origin in props],source_id)
        await mark_source_synced(conn, source_id)
    finally: await conn.close()
if __name__ == "__main__": asyncio.run(main())
