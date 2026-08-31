"""
Scraper: Boletín Oficial — Marcas y Habilitaciones en Palermo
Fuente: https://www.boletinoficial.gob.ar
Tier 3 — Descarga PDFs de la sección y extrae datos con LLM.

Secciones relevantes:
  - Segunda sección: sociedades, marcas, transferencias de fondos de comercio
  - Tercera sección: avisos oficiales, licitaciones

El scraper:
  1. Consulta la API del Boletín para listar publicaciones del día (o rango de fechas)
  2. Descarga los PDFs relevantes
  3. Extrae texto con PyMuPDF (fitz)
  4. Filtra bloques que mencionan Palermo
  5. Usa LLM para estructurar los datos extraídos
  6. Inserta en el Knowledge Graph como LegalEntity / Trademark / Organization
"""

import asyncio
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
from openai import OpenAI
from dotenv import load_dotenv

# Configurar path del proyecto para importar modulos compartidos
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("[WARNING] PyMuPDF no instalado. Instalar con: pip install pymupdf")

from scrapers.shared.db_helpers import (
    ensure_source, get_conn, get_or_create_entity, mark_source_synced, upsert_property
)
from scrapers.shared.normalizer import normalize_name, normalize_value, clean_cuit
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.geo_scope import record_in_scope
import geography_catalog as GEO

SUPPORTS_SOURCE_CONTRACT = True

OR_MODEL  = "deepseek/deepseek-v4-flash"
CACHE_DIR = Path("scrapers/boletin_cache")
CACHE_DIR.mkdir(exist_ok=True)

_llm_client = None

def _get_llm() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
    return _llm_client

# Palabras clave para filtrar bloques relevantes (ámbitodo CABA)
CABA_KEYWORDS = re.compile(
    r"COMUNA\s*\d{1,2}|"
    + "|".join(re.escape(n) for n in GEO.COMMUNES) + "|"
    r"PALERMO|SOHO|ARMENIA|HONDURAS|THAMES|SERRANO|"
    r"FITZ\s*ROY|RECOLETA|BELGRANO|VILLA\s*CRUCEL|ALMAGRO|"
    r"BELLVISTE|BALVANERA|MATRADA|MONTE\s*CASTRO|PARQUE\s*PATRICIOS|"
    r"FLORIDA|VEGA|COLEGIO|ABASTO|CASTELLANOS|PABLO|PABLO\s*ALVAREZ|"
    r"1425|1414|1426|1427",
    re.IGNORECASE
)

# API del Boletín Oficial
BOLETIN_API   = "https://www.boletinoficial.gob.ar/norma/listado"
BOLETIN_PDF   = "https://www.boletinoficial.gob.ar/pdf/linkQR/MTAwMDU="  # template
MAX_PUBLICATIONS_PER_DAY = max(1, min(int(os.getenv("BOLETIN_MAX_PUBLICATIONS", "5")), 20))


# ── Descarga de PDFs ──────────────────────────────────────────────────────────

async def fetch_publicaciones(fecha: str) -> list[dict] | None:
    """
    Consulta publicaciones del Boletín para una fecha (YYYY-MM-DD).
    Devuelve lista de {id, titulo, seccion, pdf_url}.
    """
    url = f"https://www.boletinoficial.gob.ar/norma/listado/{fecha}/2"  # sección 2
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
            return data.get("avisos", data.get("normas", []))
    except Exception as e:
        print(f"  [error] API Boletín: {e}")
        return None


async def download_pdf(pub_id: str, pdf_url: str) -> bytes | None:
    cache_file = CACHE_DIR / f"{pub_id}.pdf"
    if cache_file.exists():
        return cache_file.read_bytes()

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = await client.get(pdf_url, headers=headers)
            r.raise_for_status()
            cache_file.write_bytes(r.content)
            return r.content
    except Exception as e:
        print(f"  [error] Descarga PDF {pub_id}: {e}")
        return None


# ── Extracción de texto ───────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if not HAS_PYMUPDF:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        return "\n".join(pages)
    except Exception as e:
        print(f"  [error] PyMuPDF: {e}")
        return ""


def filter_bloques_caba(text: str) -> list[str]:
    """Extrae bloques de texto que mencionan cualquier comuna o zona de CABA."""
    blocks = re.split(r"\n{2,}", text)
    return [b.strip() for b in blocks if CABA_KEYWORDS.search(b) and len(b.strip()) > 50]


# ── Extracción estructurada con LLM ──────────────────────────────────────────

EXTRACTION_PROMPT = """Sos un extractor de datos del Boletín Oficial argentino.
Del siguiente bloque de texto, extraé SOLO la información sobre entidades localizadas en el ámbito de CABA.

Devolvé un JSON con esta estructura (sin texto extra, solo el JSON):
{
  "entidades": [
    {
      "tipo": "Marca | Sociedad | Transferencia | Habilitacion | Otro",
      "nombre": "nombre de la entidad o marca",
      "razon_social": "razón social si es sociedad",
      "cuit": "XX-XXXXXXXX-X si aparece",
      "domicilio": "dirección en CABA",
      "actividad": "rubro o actividad",
      "descripcion": "resumen breve de lo publicado",
      "nro_expediente": "si aparece"
    }
  ]
}

Si no hay entidades relevantes en CABA, devolvé {"entidades": []}.

Texto:
"""


def llm_extract(block: str) -> list[dict]:
    try:
        resp = _get_llm().chat.completions.create(
            model=OR_MODEL,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT + block[:3000]}],
            max_tokens=1000,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        return data.get("entidades", [])
    except Exception as e:
        print(f"    [LLM error] {e}")
        return []


# ── Inserción en la DB ────────────────────────────────────────────────────────

async def insert_entidad(conn, entidad: dict, source_id: str, origen_url: str):
    tipo = entidad.get("tipo", "Otro")
    nombre = entidad.get("nombre") or entidad.get("razon_social") or ""
    nombre = normalize_name(nombre)
    if not nombre:
        return

    # Determinar entity_type y subtype
    if tipo in ("Marca",):
        entity_type = "Trademark"
        subtype = "marca_registrada"
    elif tipo in ("Sociedad", "Transferencia"):
        entity_type = "LegalEntity"
        subtype = "SA"  # default, puede refinarse
    elif tipo == "Habilitacion":
        entity_type = "Organization"
        subtype = "habilitacion"
    else:
        entity_type = "LegalEntity"
        subtype = tipo.lower()

    descripcion = entidad.get("descripcion") or f"{tipo} publicada en Boletín Oficial"
    entity_id = await get_or_create_entity(
        conn, name=nombre, entity_type=entity_type, subtype=subtype,
        description=normalize_value(descripcion),
        origin_url=origen_url,
        all_names=[nombre.upper()]
    )

    props = [
        ("boletin_tipo",     entidad.get("tipo"),          "string"),
        ("address",          entidad.get("domicilio"),      "string"),
        ("cuit",             clean_cuit(entidad.get("cuit", "")), "string"),
        ("actividad",        entidad.get("actividad"),      "string"),
        ("nro_expediente",   entidad.get("nro_expediente"), "string"),
        ("razon_social",     entidad.get("razon_social"),   "string"),
    ]
    for key, val, vtype in props:
        if val:
            await upsert_property(conn, entity_id, key, normalize_value(str(val)),
                                   vtype, source_id, origins=[origen_url])

    print(f"    -> [{entity_type}] {nombre}")


# ── Scraper principal ─────────────────────────────────────────────────────────

async def scrape_boletin(conn, source_id: str, dias_atras: int = 7, limit: int | None = None):
    if not HAS_PYMUPDF:
        print("  [skip] PyMuPDF no disponible. Instalar con: pip install pymupdf")
        return False

    today = date.today()
    fechas = [(today - timedelta(days=i)).isoformat() for i in range(dias_atras)]

    total_entidades = 0
    completed = True

    for fecha in fechas:
        print(f"\n-> Procesando Boletin del {fecha}...")

        publicaciones = await fetch_publicaciones(fecha)
        if publicaciones is None:
            completed = False
            print(f"  API no respondió en formato esperado")
            continue
        if not publicaciones:
            print(f"  Sin publicaciones o API no respondió")
            continue

        print(f"  {len(publicaciones)} publicaciones encontradas")

        pub_to_process = bounded(publicaciones, limit)

        for pub in pub_to_process[:MAX_PUBLICATIONS_PER_DAY]:
            pub_id  = str(pub.get("id") or pub.get("nroNorma") or "")
            pdf_url = pub.get("pdf_url") or pub.get("urlPdf") or ""

            if not pub_id or not pdf_url:
                continue

            pdf_bytes = await download_pdf(pub_id, pdf_url)
            if not pdf_bytes:
                continue

            text = extract_text_from_pdf(pdf_bytes)
            if not text:
                continue

            bloques = filter_bloques_caba(text)
            if not bloques:
                continue

            print(f"  {len(bloques)} bloques con menciones de CABA en pub {pub_id}")

            for bloque in bloques:
                entidades = llm_extract(bloque)
                for ent in entidades:
                    await insert_entidad(conn, ent, source_id, pdf_url)
                    total_entidades += 1

    print(f"\n  [OK] {total_entidades} entidades del Boletin Oficial procesadas")
    return completed


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scraper Boletín Oficial — CABA KG")
    add_source_arguments(parser)
    parser.add_argument("--dias", type=int, default=7,
                        help="Cuántos días hacia atrás procesar (default: 7)")
    args = parser.parse_args()

    print(f"=== Scraper Boletín Oficial (últimos {args.dias} días) ===\n")

    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, "boletin_oficial", "https://www.boletinoficial.gob.ar", 3)
        completed = await scrape_boletin(conn, source_id, dias_atras=args.dias, limit=args.limit)
        if completed:
            await mark_source_synced(conn, source_id)
        else:
            print("Boletín incompleto: la fuente queda pendiente.")
        print("\n[OK] Scraper finalizado")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
