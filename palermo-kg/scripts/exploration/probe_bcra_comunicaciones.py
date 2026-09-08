"""Sonda de la estructura de URLs de Comunicaciones BCRA (normativa PDF).

Sólo lectura. Confirma:
  - qué familia de URL responde para una comunicación reciente y una vieja,
  - si el PDF índice mensual lista letra+número+fecha+asunto en texto extraíble
    (cosecha dirigida por índice) o si haría falta un barrido A{n} incremental,
  - si los PDFs tienen texto real o son escaneos (en cuyo caso no se hace OCR).
"""
import httpx

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("[aviso] PyMuPDF no instalado; no se puede validar extracción de texto.")

HEADERS = {"User-Agent": "PalermoKGBot/1.0 (luciotambo@gmail.com)"}

# Una comunicación reciente conocida y una vieja, para probar ambas familias de URL.
COMUNICACIONES_TEST = ["A8062", "A6000"]
URL_FAMILIES = [
    "https://www.bcra.gob.ar/pdfs/comytexord/{code}.pdf",
    "https://www.bcra.gob.ar/archivos/Pdfs/comytexord/{code}.pdf",
    "https://www.bcra.gob.ar/Pdfs/comytexord/{code}.pdf",
]

# Índice mensual de comunicaciones (formato ind{MMYY}.pdf visto en resultados de búsqueda).
INDICE_TEST = [
    "https://www.bcra.gob.ar/archivos/Pdfs/SistemasFinancierosYdePagos/Comunicaciones/ind0526.pdf",
    "https://www.bcra.gob.ar/archivos/Pdfs/SistemasFinancierosYdePagos/Comunicaciones/ind1225.pdf",
]


def check_pdf_text(content: bytes, label: str):
    if not HAS_PYMUPDF:
        return
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        total_chars = sum(len(page.get_text()) for page in doc)
        print(f"    páginas: {doc.page_count}, caracteres extraídos: {total_chars}")
        if total_chars < 50:
            print("    [ALERTA] Muy poco texto extraído -> probablemente escaneo. No se hace OCR.")
        else:
            first_page_text = doc[0].get_text()
            print(f"    muestra página 1: {first_page_text[:300]!r}")
    except Exception as exc:
        print(f"    [error] PyMuPDF no pudo abrir el PDF: {exc}")


def main():
    print("=== 1. Familias de URL para comunicaciones puntuales ===")
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for code in COMUNICACIONES_TEST:
            print(f"\n -- {code} --")
            for template in URL_FAMILIES:
                url = template.format(code=code)
                try:
                    r = client.get(url)
                    print(f"  {r.status_code} ({len(r.content)} bytes)  {url}")
                    if r.status_code == 200 and len(r.content) > 500:
                        check_pdf_text(r.content, code)
                except Exception as exc:
                    print(f"  ERROR {type(exc).__name__}: {exc}  {url}")

        print("\n=== 2. Índices mensuales (para cosecha dirigida por índice) ===")
        for url in INDICE_TEST:
            try:
                r = client.get(url)
                print(f"\n  {r.status_code} ({len(r.content)} bytes)  {url}")
                if r.status_code == 200 and len(r.content) > 500:
                    check_pdf_text(r.content, url)
            except Exception as exc:
                print(f"  ERROR {type(exc).__name__}: {exc}  {url}")

    print("\n=== Fin de la sonda BCRA comunicaciones ===")
    print("Si el índice mensual tiene texto extraíble con letra+número+fecha+asunto:")
    print("  -> cosecha dirigida por índice (preferida).")
    print("Si sólo las comunicaciones puntuales resuelven pero no el índice:")
    print("  -> habría que barrer A{n} incrementalmente (más frágil, evaluar antes de construir).")
    print("Si los PDFs son escaneos sin texto: NO se agrega OCR; cortar acá.")


if __name__ == "__main__":
    main()
