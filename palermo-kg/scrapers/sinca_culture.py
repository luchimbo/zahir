"""Importa el Mapa Cultural SINCA como registros históricos visibles."""
import argparse, asyncio
import httpx
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, ensure_source, mark_source_synced
from scrapers.shared.normalizer import normalize_name, normalize_value

API = "https://datos.gob.ar/api/3/action/package_show?id=cultura-mapa-cultural-espacios-culturales"
ORIGIN = "https://www.datos.gob.ar/dataset/cultura-mapa-cultural-espacios-culturales"
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = -34.615, -34.555, -58.455, -58.390
KINDS = {"bibliotecas": "biblioteca", "museo": "museo", "teatro": "teatro", "cine": "cine", "librerias": "libreria", "galerias": "galeria_arte", "centros": "centro_cultural", "monumentos": "monumento"}

def pick(row, *keys):
    for key in keys:
        if row.get(key) not in (None, ""): return str(row[key]).strip()
    return ""
def flt(v):
    try: return float(str(v).replace(",", "."))
    except ValueError: return None

async def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--write", action="store_true"); args = parser.parse_args()
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
                    if lat and lng and LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX: rows.append((row, lat, lng, resource["url"]))
            except Exception as exc: print(f"recurso omitido: {exc}")
    print(f"{len(rows)} espacios culturales históricos de Palermo | write={args.write}")
    if not args.write: return
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, "sinca", ORIGIN, 4)
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
