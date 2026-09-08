"""Sonda de Ámbito Financiero como fuente secundaria de series de mercado.

Sólo lectura. La política del proyecto (ver CABA_SOURCE_RESEARCH.md y el
precedente de bloqueo de CNV en SOURCE_OPERATIONS.md) prohíbe automatizar un
portal de consulta sin una URL de dataset explícita y una licencia
identificable. Esta sonda NO adivina endpoints: vuelca todo lo que encuentre
en la página (scripts embebidos, URLs de mercados.ambito.com o /api/) y los
términos/robots.txt, para que la decisión de admitir o no la fuente se tome
con evidencia y no con un guess de URL.
"""
import re

import httpx

HEADERS = {"User-Agent": "Mozilla/5.0 PalermoKGBot/1.0 (luciotambo@gmail.com)"}
PAGE_URL = "https://www.ambito.com/contenidos/merval-historico.html"

URL_PATTERN = re.compile(r"https?://(?:mercados\.)?ambito\.com[^\s\"'<>]*(?:/api/|mercados)[^\s\"'<>]*", re.IGNORECASE)
SCRIPT_JSON_PATTERN = re.compile(r"<script[^>]*type=\"application/(?:ld\+json|json)\"[^>]*>(.*?)</script>", re.DOTALL)


def main():
    print(f"=== 1. Página objetivo: {PAGE_URL} ===")
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        try:
            r = client.get(PAGE_URL)
            print(f"  {r.status_code} ({len(r.content)} bytes)")
        except Exception as exc:
            print(f"  ERROR {type(exc).__name__}: {exc}")
            return

        if r.status_code == 200:
            html = r.text
            urls = sorted(set(URL_PATTERN.findall(html)))
            print(f"\n  URLs candidatas encontradas ({len(urls)}):")
            for u in urls:
                print(f"    {u}")

            json_blobs = SCRIPT_JSON_PATTERN.findall(html)
            print(f"\n  Bloques <script type=json> encontrados: {len(json_blobs)}")
            for i, blob in enumerate(json_blobs[:5]):
                print(f"  -- bloque {i} (primeros 300 chars) --\n  {blob.strip()[:300]}")

        print("\n=== 2. robots.txt ===")
        try:
            rr = client.get("https://www.ambito.com/robots.txt")
            print(f"  {rr.status_code}\n{rr.text[:1500]}")
        except Exception as exc:
            print(f"  ERROR {type(exc).__name__}: {exc}")

        print("\n=== 3. Términos y condiciones ===")
        for path in ("/informacion/terminos-y-condiciones.html", "/terminos-y-condiciones",
                     "/informacion/politica-de-privacidad.html"):
            try:
                rt = client.get(f"https://www.ambito.com{path}")
                print(f"  {path}: {rt.status_code} ({len(rt.content)} bytes)")
            except Exception as exc:
                print(f"  {path}: ERROR {type(exc).__name__}: {exc}")

    print("\n=== Fin de la sonda Ámbito ===")
    print("Regla fija de antemano (no improvisar después de ver el resultado):")
    print("  - Si aparece un endpoint JSON estable Y los términos no lo prohíben")
    print("    -> agregar ambito_merval como tier 3, mode=approval, gateado por AMBITO_SERIES_URL.")
    print("  - Si no hay endpoint claro o los términos lo prohíben")
    print("    -> NO escribir el adaptador; documentar en 'Fuentes evaluadas y no activadas' junto a CNV.")


if __name__ == "__main__":
    main()
