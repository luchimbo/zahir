"""
Scraper: Boletín Oficial CABA (BOCBA) — Ingesta de Datos Locales
Fuente: https://boletinoficial.buenosaires.gob.ar
Tier 3 — Consulta API REST de BOCBA, filtra normas y extrae entidades con LLM.

Este scraper:
  1. Consulta la API REST del Boletín Oficial de CABA para obtener las normas publicadas en un rango de fechas.
  2. Filtra mediante expresiones regulares las normas que mencionan "Palermo", "Comuna 14", "Soho", etc.
  3. Para cada norma que coincida, descarga su PDF específico.
  4. Extrae el texto del PDF utilizando PyMuPDF (fitz).
  5. Envía el texto a DeepSeek (vía OpenRouter) para extraer entidades estructuradas (Obras, Fiestas/Ferias, Clausuras, Comercios, etc.).
   6. Registra/actualiza las entidades en la base de datos de CABA.
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

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, ensure_source
)
from scrapers.shared.contract import add_source_arguments, bounded
from scrapers.shared.geo_scope import record_in_scope
from scrapers.shared.normalizer import normalize_name, normalize_value, clean_cuit
import geography_catalog as GEO

SUPPORTS_SOURCE_CONTRACT = True

load_dotenv()

OR_MODEL = "deepseek/deepseek-v4-flash"
CACHE_DIR = Path("scrapers/boletin_caba_cache")
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

# Palabras clave para filtrado inicial de metadatos (evita descargar PDFs irrelevantes)
CABA_KEYWORDS = re.compile("|".join(
    [r"COMUNA\s*\d{1,2}"]
    + [re.escape(name) for name in GEO.COMMUNES]
), re.IGNORECASE)

# ── Extracción recursiva de la jerarquía de normas del JSON de BOCBA ──────────

def extract_norms(node) -> list[dict]:
    """Extrae de forma recursiva todas las normas (hojas del árbol JSON)."""
    norms = []
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and "id_norma" in item:
                norms.append(item)
            else:
                norms.extend(extract_norms(item))
    elif isinstance(node, dict):
        for k, v in node.items():
            if k == "id_norma":
                norms.append(node)
                break
            else:
                norms.extend(extract_norms(v))
    return norms


# ── Descarga y lectura de PDFs individuales ───────────────────────────────────

async def download_norm_pdf(norm_id: int, url_pdf: str) -> bytes | None:
    cache_file = CACHE_DIR / f"{norm_id}.pdf"
    if cache_file.exists():
        return cache_file.read_bytes()

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = await client.get(url_pdf, headers=headers)
            r.raise_for_status()
            cache_file.write_bytes(r.content)
            return r.content
    except Exception as e:
        print(f"  [error] Descarga PDF de norma {norm_id}: {e}")
        return None


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
        print(f"  [error] PyMuPDF al leer PDF: {e}")
        return ""


# ── Estructuración mediante LLM ──────────────────────────────────────────────

EXTRACTION_PROMPT = """Sos un extractor de datos del Boletín Oficial de la Ciudad de Buenos Aires (CABA).
Del siguiente bloque de texto (que corresponde a una norma particular), extraé la información relevante sobre entidades físicas o jurídicas, locales, obras, permisos, multas, clausuras o eventos ubicados o con impacto directo en CABA.

Devolvé un JSON con esta estructura (sin texto extra, solo el JSON):
{
  "entidades": [
    {
      "tipo": "Obra | Comercio | Feria | Arbolado | Sociedad | Clausura | Multa | Otro",
      "nombre": "Nombre descriptivo de la entidad, local o sujeto (ej: 'Obra Godoy Cruz 2869', 'Puesto Feria Palermo Viejo', 'Mantelectric Corp')",
      "razon_social": "Razón social del titular o empresa involucrada (si aparece)",
      "cuit": "XX-XXXXXXXX-X (si aparece)",
      "domicilio": "Dirección en CABA (calle y número aproximado)",
      "rubro": "Actividad, rubro o tipo de obra (ej: 'Venta de artesanías', 'Obra Nueva', 'Extracción de árboles')",
      "descripcion": "Resumen conciso y claro de lo dispuesto en la norma (ej: 'Se aprueba factibilidad de obra nueva residencial', 'Se autoriza suplencia en puesto de feria')",
      "nro_expediente": "Número de expediente (si aparece)",
      "fecha_norma": "Fecha de la resolución o disposición"
    }
  ]
}

Si no encontrás ninguna entidad en CABA dentro del texto, devolvé {"entidades": []}.
Texto:
"""

def llm_extract_bocba(text: str) -> list[dict]:
    # Si no hay API key o no está configurada, saltear
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("  [warning] OPENROUTER_API_KEY no seteada. Saltando LLM.")
        return []
        
    try:
        resp = _get_llm().chat.completions.create(
            model=OR_MODEL,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT + text[:4000]}],
            max_tokens=1000,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        return data.get("entidades", [])
    except Exception as e:
        print(f"  [LLM error] {e}")
        return []


# ── Ingesta en la Base de Datos ───────────────────────────────────────────────

async def insert_bocba_entidad(conn, entidad: dict, source_id: str, origen_url: str):
    tipo = entidad.get("tipo", "Otro")
    nombre = entidad.get("nombre") or entidad.get("razon_social") or ""
    nombre = normalize_name(nombre)
    if not nombre:
        return

    # Mapeo a tipos del grafo: Location, Facility, Organization, LegalEntity, Event, Transport
    if tipo == "Obra":
        entity_type = "Facility"
        subtype = "obra_publica" if "publica" in (entidad.get("rubro") or "").lower() else "obra_privada"
    elif tipo == "Feria":
        entity_type = "Facility"
        subtype = "feria"
    elif tipo == "Arbolado":
        entity_type = "Facility"
        subtype = "arbol"
    elif tipo in ("Comercio", "Clausura", "Multa"):
        entity_type = "Organization"
        subtype = "comercio_habilitado"
    elif tipo == "Sociedad":
        entity_type = "LegalEntity"
        subtype = "SA"
    else:
        entity_type = "LegalEntity"
        subtype = "bocba_registro"

    descripcion = entidad.get("descripcion") or f"{tipo} publicada en el Boletin de CABA"
    
    entity_id = await get_or_create_entity(
        conn,
        name=nombre,
        entity_type=entity_type,
        subtype=subtype,
        description=normalize_value(descripcion),
        origin_url=origen_url,
        all_names=[nombre.upper()]
    )

    # Ingestar propiedades dinámicas
    props = [
        ("bocba_tipo",        entidad.get("tipo"),          "string"),
        ("address",           entidad.get("domicilio"),      "string"),
        ("cuit",              clean_cuit(entidad.get("cuit", "")), "string"),
        ("business_activity", entidad.get("rubro"),         "string"),
        ("nro_expediente",    entidad.get("nro_expediente"), "string"),
        ("razon_social",      entidad.get("razon_social"),   "string"),
        ("resolution_date",   entidad.get("fecha_norma"),    "string"),
    ]
    
    for key, val, vtype in props:
        if val:
            await upsert_property(
                conn,
                entity_id,
                key,
                normalize_value(str(val)),
                vtype,
                source_id,
                origins=[origen_url],
                confidence=0.95
            )

    print(f"    -> Ingestado [{entity_type}/{subtype}]: {nombre}")


# ── Ejecución del Scraper ─────────────────────────────────────────────────────

async def scrape_bocba(conn, source_id: str, dias_atras: int = 7, limit: int | None = None):
    if not HAS_PYMUPDF:
        print("  [skip] PyMuPDF no disponible. Por favor instala pymupdf.")
        return

    today = date.today()
    total_procesadas = 0

    for i in range(dias_atras):
        fecha_obj = today - timedelta(days=i)
        fecha_str = fecha_obj.strftime("%d-%m-%Y")
        print(f"\n-> Buscando Boletin CABA del {fecha_str}...")

        url_listado = f"https://api-restboletinoficial.buenosaires.gob.ar/obtenerBoletin/{fecha_str}/true"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url_listado, headers=headers)
                if r.status_code != 200:
                    print(f"  [skip] No se encontro boletin o error HTTP {r.status_code}")
                    continue
                data = r.json()
        except Exception as e:
            print(f"  [error] Fallo conexion a API BOCBA: {e}")
            continue

        raw_normas = data.get("normas", {}).get("normas", {})
        all_norms = extract_norms(raw_normas)
        if not all_norms:
            print("  Sin normas en el boletin de esta fecha.")
            continue

        # Filtrar normas que mencionan CABA en metadatos
        matching_norms = []
        for n in all_norms:
            text_meta = f"{n.get('nombre', '')} {n.get('sumario', '')}"
            if CABA_KEYWORDS.search(text_meta):
                matching_norms.append(n)

        matching_norms = bounded(matching_norms, limit)
        print(f"  Total normas: {len(all_norms)} | Coinciden con CABA: {len(matching_norms)}")

        for norm in matching_norms:
            norm_id = norm.get("id_norma")
            url_pdf = norm.get("url_norma")
            nombre_norma = norm.get("nombre", "Norma sin nombre")
            
            if not norm_id or not url_pdf:
                continue

            print(f"  Procesando: {nombre_norma} (ID: {norm_id})...")

            # 1. Descargar PDF individual de la norma
            pdf_bytes = await download_norm_pdf(norm_id, url_pdf)
            if not pdf_bytes:
                continue

            # 2. Extraer texto del PDF
            text = extract_text_from_pdf(pdf_bytes)
            if not text:
                continue

            # 3. Extraer estructurado usando LLM
            entidades = llm_extract_bocba(text)
            if not entidades:
                print("    Sin entidades identificadas en CABA por el LLM.")
                continue

            # 4. Registrar en la DB
            for ent in entidades:
                await insert_bocba_entidad(conn, ent, source_id, url_pdf)
                total_procesadas += 1

            await asyncio.sleep(0.5)  # Respeto entre llamadas al LLM

    print(f"\n[OK] Scrape BOCBA finalizado. Se cargaron {total_procesadas} entidades.")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scraper Boletín Oficial CABA (BOCBA) — CABA KG")
    parser.add_argument("--dias", type=int, default=3,
                        help="Cuántos días hacia atrás procesar (default: 3)")
    add_source_arguments(parser)
    args = parser.parse_args()

    print(f"=== Scraper Boletin Oficial CABA (BOCBA) — Ultimos {args.dias} dias ===\n")

    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, "boletin_oficial", "https://boletinoficial.buenosaires.gob.ar", tier=3)
        await scrape_bocba(conn, source_id, dias_atras=args.dias, limit=args.limit)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
