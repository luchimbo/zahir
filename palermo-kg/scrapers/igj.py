"""
Scraper: IGJ — Entidades Constituidas
Fuente: https://datos.jus.gob.ar (datos abiertos del Ministerio de Justicia)
Tier 1 — Dataset público en CSV, sin autenticación.

Descarga el ZIP semestral, extrae el CSV de entidades y autoridades,
y filtra las sociedades con domicilio en Palermo, CABA.
"""

import asyncio
import csv
import io
import os
import zipfile
import httpx
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id
)
from scrapers.shared.normalizer import normalize_name, normalize_value, clean_cuit

# ZIP con datos del último semestre
ZIP_URL = "https://datos.jus.gob.ar/dataset/da045e06-35cb-4bdd-9b5e-ddee6712c86c/resource/fbcb0917-d298-479b-8fda-c314b4af33eb/download/igj-2025-semestre-2.zip"

PALERMO_CALLES = {
    "ARMENIA", "HONDURAS", "GURRUCHAGA", "THAMES", "SERRANO",
    "FITZ ROY", "MALABIA", "GODOY CRUZ", "JORGE NEWBERY",
    "SOLER", "SCALABRINI ORTIZ", "RAVIGNANI", "HUMBOLDT", "BONPLAND",
    "NICARAGUA", "COSTA RICA", "EL SALVADOR", "GUATEMALA", "CABRERA",
    "Thames", "JULIÁN ÁLVAREZ", "JULIAN ALVAREZ", "URIARTE", "ACEVEDO",
    "LOYOLA", "ANGEL CARRANZA", "CARRANZA", "FRAY JUSTO SARMIENTO",
    "LAFINUR", "CERVINO", "RUFINO DE ELIZALDE", "MIGUELETES",
    "CORONEL DIAZ", "BULLRICH", "SALGUERO", "DORREGO",
}

PALERMO_CP = {"1425", "1414", "1426", "1427", "1172", "1176"}

TIPO_MAP = {
    "SOCIEDAD ANONIMA": "SA",
    "SOC. ANONIMA": "SA",
    "SOC.ANONIMA": "SA",
    "S.A.": "SA",
    "SOCIEDAD DE RESPONSABILIDAD LIMITADA": "SRL",
    "SOC. DE RESP. LIMITADA": "SRL",
    "SOC.DE RESP.LIMITADA": "SRL",
    "S.R.L.": "SRL",
    "SOCIEDAD POR ACCIONES SIMPLIFICADA": "SAS",
    "S.A.S.": "SAS",
    "SOCIEDAD COLECTIVA": "SC",
    "SOCIEDAD EN COMANDITA SIMPLE": "SCS",
    "SOCIEDAD EN COMANDITA POR ACCIONES": "SCA",
    "ASOCIACION CIVIL": "Asociacion Civil",
    "FUNDACION": "Fundacion",
}


def is_palermo(row: dict) -> bool:
    cp = row.get("codigo_postal", "").strip()
    if cp in PALERMO_CP:
        return True
    calle = row.get("calle", "").upper().strip()
    return any(kw in calle for kw in PALERMO_CALLES)


def detect_tipo(row: dict) -> str:
    desc = row.get("descripcion_tipo_societario", "").upper()
    for k, v in TIPO_MAP.items():
        if k in desc:
            return v
    return desc[:20] if desc else "OTRO"


CACHE_PATH = "scrapers/igj_cache.zip"

async def download_and_extract(url: str) -> dict[str, bytes]:
    """Descarga el ZIP (con cache en disco) y devuelve {filename: content}."""
    if os.path.exists(CACHE_PATH):
        print(f"  Usando cache local: {CACHE_PATH}")
        with open(CACHE_PATH, "rb") as f:
            data = f.read()
    else:
        print(f"  Descargando ZIP ({url})...")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
        data = r.content
        with open(CACHE_PATH, "wb") as f:
            f.write(data)
        print(f"  Descargado y guardado ({len(data) / 1024 / 1024:.1f} MB)")

    zf = zipfile.ZipFile(io.BytesIO(data))
    return {name: zf.read(name) for name in zf.namelist() if name.endswith(".csv")}


async def scrape_igj(conn, source_id: str):
    print("→ Scrapeando IGJ...")

    try:
        csv_files = await download_and_extract(ZIP_URL)
    except Exception as e:
        print(f"  [error] No se pudo descargar el ZIP: {e}")
        return

    print(f"  Archivos CSV en el ZIP: {list(csv_files.keys())}")

    # Usar el mes más reciente disponible (202512 o 202511)
    mes = "202512" if any("202512" in n for n in csv_files) else "202511"
    print(f"  Usando mes: {mes}")

    entidades_csv  = csv_files.get(f"igj-entidades-{mes}.csv")
    domicilios_csv = csv_files.get(f"igj-domicilios-{mes}.csv")

    if not entidades_csv or not domicilios_csv:
        print(f"  [error] No se encontraron archivos para el mes {mes}")
        return

    # Parsear entidades
    rows_ent = list(csv.DictReader(io.StringIO(
        entidades_csv.decode("utf-8-sig", errors="replace")
    )))
    print(f"  Entidades: {len(rows_ent)} filas | Columnas: {list(rows_ent[0].keys()) if rows_ent else []}")

    # Parsear domicilios y filtrar Palermo
    rows_dom = list(csv.DictReader(io.StringIO(
        domicilios_csv.decode("utf-8-sig", errors="replace")
    )))
    print(f"  Domicilios: {len(rows_dom)} filas | Columnas: {list(rows_dom[0].keys()) if rows_dom else []}")

    # IDs con domicilio en Palermo
    palermo_ids = set()
    for d in rows_dom:
        if is_palermo(d):
            palermo_ids.add(d.get("numero_correlativo", "").strip())

    print(f"  Entidades con domicilio en Palermo: {len(palermo_ids)}")

    # Cruzar entidades con domicilios Palermo
    palermo_rows = [r for r in rows_ent
                    if r.get("numero_correlativo", "").strip() in palermo_ids]
    print(f"  Entidades en Palermo después del cruce: {len(palermo_rows)}")

    # Preparar datos normalizados
    parsed = []
    for row in palermo_rows:
        razon_social = normalize_name(row.get("razon_social", "").strip())
        if not razon_social:
            continue
        tipo     = detect_tipo(row)
        estado   = "Baja" if row.get("dada_de_baja") else "Activa"
        parsed.append({
            "name":         razon_social,
            "tipo":         tipo,
            "estado":       estado,
            "cuit":         clean_cuit(row.get("cuit", "")),
            "numero":       row.get("numero_correlativo", "").strip(),
            "detalle_baja": normalize_value(row.get("detalle_baja", "").strip()) or None,
        })

    print(f"  Insertando {len(parsed)} entidades en batch...")

    # Batch insert entities
    BATCH = 500
    entity_records = [
        (r["name"], "LegalEntity", r["tipo"],
         f"{r['tipo']} registrada en IGJ — {r['estado']}", ZIP_URL)
        for r in parsed
    ]

    for i in range(0, len(entity_records), BATCH):
        chunk = entity_records[i:i+BATCH]
        await conn.executemany(
            """
            INSERT INTO entities (name, entity_type, subtype, description, origin_url)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING
            """,
            chunk
        )
        print(f"  Entidades: {min(i+BATCH, len(entity_records))}/{len(entity_records)}")

    # Obtener IDs insertados y hacer batch de properties
    print("  Insertando properties...")
    props_records = []
    for r in parsed:
        row_id = await conn.fetchval(
            "SELECT id FROM entities WHERE name = $1 AND entity_type = 'LegalEntity' AND canonical_id IS NULL LIMIT 1",
            r["name"]
        )
        if not row_id:
            continue
        for key, vtype, val in [
            ("tipo_sociedad",  "string", r["tipo"]),
            ("status",         "string", r["estado"]),
            ("cuit",           "string", r["cuit"]),
            ("igj_number",     "string", r["numero"]),
            ("closure_reason", "string", r["detalle_baja"]),
        ]:
            if val:
                props_records.append((str(row_id), key, val, vtype, source_id, [ZIP_URL]))

    for i in range(0, len(props_records), BATCH):
        chunk = props_records[i:i+BATCH]
        await conn.executemany(
            """
            INSERT INTO properties (entity_id, key, value, value_type, source_id, origins, valid_from)
            VALUES ($1, $2, $3, $4, $5, $6, CURRENT_DATE)
            ON CONFLICT DO NOTHING
            """,
            chunk
        )
        if i % 5000 == 0:
            print(f"  Properties: {min(i+BATCH, len(props_records))}/{len(props_records)}")

    print(f"  ✓ {len(parsed)} entidades IGJ procesadas")


async def main():
    print("=== Scraper IGJ ===")
    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "igj")
        await scrape_igj(conn, source_id)
        print("\n✓ Scraper finalizado")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
