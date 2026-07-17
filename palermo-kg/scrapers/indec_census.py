"""Radios censales INDEC dentro de Palermo; indicadores opcionales mediante CSV oficial."""
import argparse, asyncio, csv, io, json, os
import httpx
from scrapers.shared.db_helpers import bulk_get_or_create_entities, bulk_upsert_properties, get_conn, ensure_source, mark_source_synced

WFS = "https://geonode.indec.gob.ar/geoserver/geonode/wfs"
ORIGIN = "https://geonode.indec.gob.ar/layers/geonode_data%3Ageonode%3Aradios_censales2"
BBOX = "-58.455,-34.615,-58.390,-34.555"

def contains(point, geometry):
    """Ray casting sin dependencia GIS; GeoJSON Polygon/MultiPolygon."""
    x, y = point
    polygons = geometry.get("coordinates", [])
    if geometry.get("type") == "Polygon": polygons = [polygons]
    for polygon in polygons:
        if not polygon: continue
        ring = polygon[0]; inside = False
        for index, current in enumerate(ring):
            previous = ring[index - 1]
            xi, yi = current; xj, yj = previous
            if ((yi > y) != (yj > y)) and x < (xj-xi)*(y-yi)/(yj-yi)+xi: inside = not inside
        if inside: return True
    return False

async def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--write",action="store_true"); args=parser.parse_args()
    params={"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":"geonode:radios_censales2","outputFormat":"application/json","srsName":"EPSG:4326","bbox":f"{BBOX},EPSG:4326"}
    async with httpx.AsyncClient(timeout=90) as client:
        response=await client.get(WFS,params=params); response.raise_for_status(); features=response.json().get("features",[])
    # Palermo pertenece a Comuna 14. El bbox sólo reduce el tráfico y no es el filtro final.
    features=[f for f in features if "COMUNA 14" in str((f.get("properties") or {}).get("dpto", "")).upper()]
    print(f"{len(features)} radios censales intersectan Palermo | write={args.write}")
    if not args.write:return
    conn=await get_conn()
    try:
        source_id=await ensure_source(conn,"indec_censo",ORIGIN)
        records=[]; props=[]
        for feature in features:
            attrs=feature.get("properties") or {}; code=str(attrs.get("cod_indec") or attrs.get("id") or "")
            if not code: continue
            name=f"Radio Censal {code}"; records.append({"name":name,"entity_type":"Location","subtype":"radio_censal","origin_url":ORIGIN})
            geom=json.dumps(feature.get("geometry"),separators=(",",":"))
            for key,value,kind in [("indec_radio_code",code,"string"),("census_year","2022","number"),("geometry_geojson",geom,"string")]:
                props.append((name,key,value,kind))
        ids=await bulk_get_or_create_entities(conn,records)
        await bulk_upsert_properties(conn,[{"entity_id":ids[name],"key":key,"value":value,"value_type":kind,"origins":[ORIGIN],"confidence":.95} for name,key,value,kind in props],source_id)
        # Relación espacial determinística: una entidad geocodificada queda en su radio INDEC.
        points=await conn.fetch("SELECT id,lat,lng FROM entities WHERE canonical_id IS NULL AND is_active AND lat BETWEEN -34.615 AND -34.555 AND lng BETWEEN -58.455 AND -58.390")
        radio_geometries=[(ids[f"Radio Censal {str((f.get('properties') or {}).get('cod_indec') or (f.get('properties') or {}).get('id'))}"], f.get("geometry") or {}) for f in features]
        links=[]
        for point in points:
            for radio_id, geometry in radio_geometries:
                if contains((float(point['lng']),float(point['lat'])),geometry):
                    links.append((point['id'],radio_id,[ORIGIN])); break
        if links:
            await conn.executemany("""INSERT INTO relationships (from_entity_id, relationship_type, to_entity_id, confidence, origins, direction)
                SELECT $1,'LOCATED_IN',$2,.95,$3,'directed' WHERE NOT EXISTS (SELECT 1 FROM relationships WHERE from_entity_id=$1 AND relationship_type='LOCATED_IN' AND to_entity_id=$2)""",links)
        await mark_source_synced(conn,source_id)
    finally: await conn.close()
if __name__=="__main__":asyncio.run(main())
