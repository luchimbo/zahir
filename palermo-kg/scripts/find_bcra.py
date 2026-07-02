"""Encuentra la URL correcta de datos del BCRA."""
import httpx

urls = [
    "https://api.bcra.gob.ar/entidades/v1.0/listadoentidades",
    "https://api.bcra.gob.ar/catalogo/v1.0/series/repos",
    "https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/entlist.txt",
    "https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/padronentidades.csv",
    "https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/PADRON.CSV",
]

for url in urls:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": "PalermoKGBot/1.0 (luciotambo@gmail.com)"})
        print(f"{r.status_code} {len(r.content):>8} bytes  {url}")
        if r.status_code == 200 and len(r.content) > 1000:
            print(f"  Primeros 200 bytes: {r.content[:200]}")
    except Exception as e:
        print(f"ERROR  {url}: {e}")
