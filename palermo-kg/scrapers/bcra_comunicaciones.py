"""
Scraper: BCRA — Comunicaciones A/B/C (normativa)
Fuente: https://www.bcra.gob.ar
Tier 3 — credential (OPENROUTER_API_KEY para el resumen), paid, weekly.
Hermano de scrapers/boletin_oficial.py, sin el filtro territorial de CABA
(esta fuente es nacional por definición).

Cosecha dirigida por índice, confirmada por sonda (probe_bcra_comunicaciones.py,
2026-09-08): el PDF mensual ind{MMYY}.pdf lista letra+número+fecha+asunto en
texto extraíble (no es un escaneo), así que no hace falta barrer A{n} a ciegas
ni usar el LLM para descubrir documentos — sólo para resumirlos.

Modelo: una entidad Regulation por comunicación (documento, no un punto de
serie): no va en `observations`. Sin OPENROUTER_API_KEY igual se escriben
número, letra, fecha y URL desde el índice; el resumen queda vacío y
coverage["summarised"]=0 — nunca bloquea la ingesta por falta de LLM.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from scrapers.shared.contract import SourceResult, add_source_arguments, bounded
from scrapers.shared.db_helpers import ensure_source, get_conn, get_or_create_entity, mark_source_synced, upsert_property

SOURCE_NAME = "bcra_comunicaciones"
SOURCE_URL = "https://www.bcra.gob.ar"
INDICE_URL = "https://www.bcra.gob.ar/archivos/Pdfs/SistemasFinancierosYdePagos/Comunicaciones/ind{mmyy}.pdf"
COMUNICACION_URL = "https://www.bcra.gob.ar/pdfs/comytexord/{code}.pdf"
CACHE_DIR = Path("scrapers/bcra_cache")
CACHE_DIR.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "PalermoKGBot/1.0 (luciotambo@gmail.com)"}

MAX_DOCS_PER_RUN = max(1, min(int(os.getenv("BCRA_MAX_COMUNICACIONES", "25")), 100))
OR_MODEL = "deepseek/deepseek-v4-flash"

# "A8433 06.05.26" o "A8358 \n01.12.25": letra+número, luego fecha DD.MM.YY,
# separados por espacio/salto de línea variable según el año del índice.
ENTRY_PATTERN = re.compile(r"([ABC])\s*(\d{3,5})\s*\n?\s*(\d{2})\.(\d{2})\.(\d{2})")

_llm_client = None


def _get_llm():
    global _llm_client
    if _llm_client is None:
        from openai import OpenAI
        _llm_client = OpenAI(base_url="https://openrouter.ai/api/v1",
                             api_key=os.environ.get("OPENROUTER_API_KEY", ""))
    return _llm_client


def parse_index_pdf_text(text: str) -> list[dict]:
    """Función pura: extrae {letter, number, date, title} del texto del índice
    mensual. Testeable sin red (ver tests/test_bcra_parsing.py)."""
    matches = list(ENTRY_PATTERN.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        letter, number, dd, mm, yy = m.groups()
        year = 2000 + int(yy)
        try:
            fecha = date(year, int(mm), int(dd))
        except ValueError:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = re.sub(r"\s+", " ", text[m.end():end]).strip()
        entries.append({"letter": letter, "number": int(number), "date": fecha, "title": title})
    return entries


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if not HAS_PYMUPDF:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        print(f"  [error] PyMuPDF: {exc}")
        return ""


async def download(client: httpx.AsyncClient, url: str, cache_name: str) -> bytes | None:
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        return cache_file.read_bytes()
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        cache_file.write_bytes(r.content)
        return r.content
    except Exception as exc:
        print(f"  [error] descarga {url}: {exc}")
        return None


SUMMARY_PROMPT = """Sos un resumidor de normativa del Banco Central de la República Argentina.
Del siguiente texto de una Comunicación del BCRA, devolvé SOLO un JSON (sin texto extra):
{"resumen": "resumen de 1-2 oraciones", "temas": ["tema1", "tema2"]}

Texto:
"""


def llm_summarize(text: str) -> dict:
    try:
        resp = _get_llm().chat.completions.create(
            model=OR_MODEL,
            messages=[{"role": "user", "content": SUMMARY_PROMPT + text[:4000]}],
            max_tokens=400, temperature=0, response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content.strip())
    except Exception as exc:
        print(f"    [LLM error] {exc}")
        return {}


async def already_ingested(conn, source_id: str, code: str) -> bool:
    row = await conn.fetchrow("SELECT entity_id FROM external_ids WHERE source_id=$1 AND external_id=$2 LIMIT 1",
                              source_id, code)
    return row is not None


async def main():
    parser = argparse.ArgumentParser(description="BCRA — Comunicaciones A/B/C")
    add_source_arguments(parser)
    parser.add_argument("--months-back", type=int, default=3,
                        help="Cuántos meses de índice escanear hacia atrás (default: 3).")
    args = parser.parse_args()

    if args.neighborhood or args.commune:
        return SourceResult(skipped=1, errors=["Fuente nacional: no admite acotar por barrio/comuna."])
    if not HAS_PYMUPDF:
        return SourceResult(errors=["PyMuPDF no instalado: pip install pymupdf"])

    result = SourceResult()
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, SOURCE_NAME, SOURCE_URL, 3)
        has_llm = bool(os.environ.get("OPENROUTER_API_KEY"))
        summarised = 0

        today = date.today()
        months = []
        cursor = today
        for _ in range(args.months_back):
            months.append(cursor)
            prev_month = cursor.month - 1 or 12
            prev_year = cursor.year - 1 if cursor.month == 1 else cursor.year
            cursor = date(prev_year, prev_month, 1)

        async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            all_entries = []
            for month in months:
                mmyy = f"{month.month:02d}{month.year % 100:02d}"
                idx_bytes = await download(client, INDICE_URL.format(mmyy=mmyy), f"ind{mmyy}.pdf")
                if not idx_bytes:
                    continue
                text = extract_text_from_pdf(idx_bytes)
                all_entries.extend(parse_index_pdf_text(text))
                await asyncio.sleep(1)

            result.seen = len(all_entries)
            entries = bounded(all_entries, args.limit or MAX_DOCS_PER_RUN)

            if not args.write:
                result.accepted = len(entries)
                result.coverage = {"summarised": 0, "has_llm": has_llm, "mode": "validate"}
                print(f"[OK] bcra_comunicaciones (validate): {result.seen} en índice, "
                      f"{result.accepted} en la ventana pedida | write=False")
                return result

            for entry in entries:
                code = f"{entry['letter']}{entry['number']}"
                if await already_ingested(conn, source_id, code):
                    continue
                result.accepted += 1

                pdf_url = COMUNICACION_URL.format(code=code)
                pdf_bytes = await download(client, pdf_url, f"{code}.pdf")
                summary = topic = None
                if pdf_bytes and has_llm:
                    text = extract_text_from_pdf(pdf_bytes)
                    if text:
                        data = llm_summarize(text)
                        summary = data.get("resumen")
                        topic = ", ".join(data.get("temas") or []) or None
                        if summary:
                            summarised += 1

                entity_id = await get_or_create_entity(
                    conn, name=f"Comunicación {entry['letter']} {entry['number']}",
                    entity_type="Regulation", subtype=f"comunicacion_{entry['letter'].lower()}",
                    origin_url=pdf_url, source_id=source_id, external_id=code,
                )
                props = [
                    ("document_number", str(entry["number"]), "string"),
                    ("document_letter", entry["letter"], "string"),
                    ("publication_date", entry["date"].isoformat(), "date"),
                    ("document_url", pdf_url, "url"),
                    ("publisher", "BCRA", "string"),
                ]
                if entry.get("title"):
                    props.append(("title", entry["title"][:255], "string"))
                if summary:
                    props.append(("summary", summary, "string"))
                if topic:
                    props.append(("topic", topic, "string"))
                for key, value, vtype in props:
                    if value:
                        await upsert_property(conn, entity_id, key, value, vtype, source_id, origins=[pdf_url])
                result.written += 1
                await asyncio.sleep(1.5)

        result.coverage = {"summarised": summarised, "has_llm": has_llm}
        if result.ok:
            await mark_source_synced(conn, source_id)
        print(f"[OK] bcra_comunicaciones: {result.seen} en índice, {result.accepted} nuevas, "
              f"{result.written} escritas, {summarised} resumidas | write={args.write}")
        return result
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
