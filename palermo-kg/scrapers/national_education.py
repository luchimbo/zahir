"""Padrón Oficial de Establecimientos Educativos (Nación), filtrado Palermo.

La URL se obtiene desde PADRON_EDUCATIVO_URL para no fijar un enlace de descarga
que el Ministerio puede rotar. Dry-run por defecto; --write persiste.
"""
import argparse, asyncio, csv, io, os
import httpx
from scrapers.shared.db_helpers import get_conn, get_or_create_entity, ensure_source, mark_source_synced, upsert_property
from scrapers.shared.normalizer import normalize_name, normalize_value

SOURCE = "padron_educativo"
ORIGIN = "https://www.argentina.gob.ar/node/246613"
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = -34.615, -34.555, -58.455, -58.390

def value(row, *keys):
    for key in keys:
        raw = str(row.get(key, "") or "").strip()
        if raw: return raw
    return ""

def number(raw):
    try: return float(str(raw).replace(",", "."))
    except ValueError: return None

def in_palermo(row):
    lat, lng = number(value(row, "latitud", "lat", "latitude")), number(value(row, "longitud", "lon", "lng", "longitude"))
    commune = value(row, "comuna", "comune")
    return commune == "14" or (lat is not None and lng is not None and LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX), lat, lng

async def find_by_code(conn, code):
    if not code: return None
    return await conn.fetchval("""SELECT p.entity_id FROM active_properties p JOIN entities e ON e.id=p.entity_id
        WHERE p.key IN ('school_cue','school_cui','national_school_id') AND p.value=$1
        AND e.canonical_id IS NULL AND e.is_active LIMIT 1""", code)

async def main():
    args = argparse.ArgumentParser(); args.add_argument("--write", action="store_true"); parsed = args.parse_args()
    url = os.getenv("PADRON_EDUCATIVO_URL")
    if not url:
        print("PADRON_EDUCATIVO_URL no configurada: adaptador listo, sin descarga."); return
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        response = await client.get(url); response.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig", "replace"))))
    candidates = [(r, *in_palermo(r)[1:]) for r in rows if in_palermo(r)[0]]
    print(f"{len(rows)} filas | {len(candidates)} candidatas Palermo | write={parsed.write}")
    if not parsed.write: return
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, SOURCE, ORIGIN)
        for row, lat, lng in candidates:
            name = normalize_name(value(row, "nombre", "nombre_establecimiento", "establecimiento"))
            if not name: continue
            cue, cui = value(row, "cue", "CUE"), value(row, "cui", "CUI")
            entity_id = await find_by_code(conn, cue) or await find_by_code(conn, cui)
            if not entity_id:
                entity_id = await get_or_create_entity(conn, name, "Facility", "escuela", lat, lng, origin_url=ORIGIN)
            props = {"national_school_id": value(row, "id", "id_establecimiento"), "school_cue": cue,
                     "school_cui": cui, "education_level": value(row, "nivel", "nivel_educativo"),
                     "management": value(row, "gestion", "sector"), "address": value(row, "domicilio", "direccion"),
                     "phone": value(row, "telefono"), "education_offer": value(row, "oferta", "oferta_educativa")}
            for key, raw in props.items():
                if raw: await upsert_property(conn, str(entity_id), key, normalize_value(raw), "string", source_id, [ORIGIN], .95)
        await mark_source_synced(conn, source_id)
    finally: await conn.close()

if __name__ == "__main__": asyncio.run(main())
