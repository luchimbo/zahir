"""
Scraper: Argenprop via Nstbrowser + Playwright
Fuente: https://www.argenprop.com
Tier 2 — Anti-bot bypass con Nstbrowser.

Argenprop embebe los listings en window.__NEXT_DATA__ (Next.js).
"""

import asyncio
import json
import os
import re
import httpx
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from scrapers.shared.db_helpers import (
    get_conn, get_or_create_entity, upsert_property, get_source_id
)

load_dotenv()

API_KEY = os.getenv("NSTBROWSER_API_KEY")
NSTBROWSER_HOST = "http://localhost:8848"
BASE_URL = "https://www.argenprop.com"

SEARCHES = [
    {"url": f"{BASE_URL}/departamento-alquiler-en-palermo", "listing_type": "rental"},
    {"url": f"{BASE_URL}/departamento-venta-en-palermo",   "listing_type": "sale"},
    {"url": f"{BASE_URL}/ph-alquiler-en-palermo",          "listing_type": "rental"},
    {"url": f"{BASE_URL}/ph-venta-en-palermo",             "listing_type": "sale"},
]


async def get_cdp_endpoint() -> str:
    headers = {"x-api-key": API_KEY}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{NSTBROWSER_HOST}/api/v2/browsers", headers=headers)
        r.raise_for_status()
        browsers = r.json().get("data", [])
        if not browsers:
            raise RuntimeError("No hay browsers corriendo en Nstbrowser.")
        browser = next((b for b in browsers if b.get("running")), browsers[0])
        port = browser["remoteDebuggingPort"]
        print(f"  Usando perfil: '{browser.get('name')}' (puerto {port})")
        r2 = await client.get(f"http://localhost:{port}/json/version")
        ws_url = r2.json().get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("No se pudo obtener webSocketDebuggerUrl")
    return ws_url


def extract_next_data(html: str) -> dict | None:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def get_listings_from_next_data(data: dict) -> list:
    try:
        props = data["props"]["pageProps"]
        return (
            props.get("listings") or
            props.get("data", {}).get("listings") or
            props.get("searchResults", {}).get("listings") or
            []
        )
    except (KeyError, TypeError):
        return []


def parse_listing(listing: dict, listing_type: str) -> dict | None:
    try:
        title = (listing.get("title") or listing.get("postingDescription") or "").strip()
        if not title:
            return None

        geo = listing.get("geo") or listing.get("location") or {}
        lat = geo.get("lat") or geo.get("latitude")
        lng = geo.get("lng") or geo.get("longitude") or geo.get("lon")

        address  = listing.get("address") or listing.get("postingAddress") or ""
        zone     = listing.get("zone") or listing.get("neighborhood") or "Palermo"
        url_path = listing.get("url") or listing.get("postingUrl") or ""
        full_url = BASE_URL + url_path if url_path.startswith("/") else url_path

        # Precio
        price_data = listing.get("price") or listing.get("prices") or {}
        if isinstance(price_data, list):
            price_data = price_data[0] if price_data else {}
        currency   = price_data.get("currency", "")
        amount     = price_data.get("amount") or price_data.get("value")
        price_usd  = str(amount) if currency == "USD" and amount else None
        price_ars  = str(amount) if currency == "ARS" and amount else None

        # Atributos
        features = listing.get("features") or listing.get("mainFeatures") or []
        feat_map = {}
        for f in features:
            feat_map[f.get("label", "").lower()] = f.get("value") or f.get("text") or ""

        area_m2      = feat_map.get("superficie total") or feat_map.get("superficie")
        covered_m2   = feat_map.get("superficie cubierta")
        rooms        = feat_map.get("ambientes") or feat_map.get("rooms")
        bathrooms    = feat_map.get("baños") or feat_map.get("bathrooms")
        parking      = feat_map.get("cocheras") or feat_map.get("parking")

        expenses_ars = None
        exp = listing.get("expenses") or listing.get("expensas")
        if exp:
            expenses_ars = str(exp.get("amount") or exp.get("value") or "")

        property_type = (listing.get("realEstateType") or
                         listing.get("propertyType") or "inmueble").lower()

        return {
            "title": title,
            "lat": float(lat) if lat else None,
            "lng": float(lng) if lng else None,
            "address": address, "zone": zone, "url": full_url,
            "listing_type": listing_type, "property_type": property_type,
            "price_usd": price_usd, "price_ars": price_ars,
            "expenses_ars": expenses_ars or None,
            "area_m2": str(area_m2) if area_m2 else None,
            "covered_area_m2": str(covered_m2) if covered_m2 else None,
            "rooms": str(rooms) if rooms else None,
            "bathrooms": str(bathrooms) if bathrooms else None,
            "parking": str(parking) if parking else None,
        }
    except Exception:
        return None


async def wait_for_page(page, url: str) -> str | None:
    """Navega y espera hasta que cargue (con pausa para captcha si aparece)."""
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print("    [esperando... resolvé el captcha si aparece]")
    for i in range(24):
        await page.wait_for_timeout(5000)
        try:
            content = await page.content()
        except Exception:
            continue
        if "__NEXT_DATA__" in content:
            return content
        if i == 2:
            # Mostrar qué scripts hay en la página para debuggear
            scripts = await page.eval_on_selector_all("script[id]", "els => els.map(e => e.id)")
            print(f"    [debug] script ids: {scripts}")
            title = await page.title()
            print(f"    [debug] título: {title}")
        print(f"    [esperando... intento {i+1}/24]")
    print("    [timeout]")
    return None


async def scrape_page(page, url: str, listing_type: str, conn, source_id: str) -> int:
    html = await wait_for_page(page, url)
    if not html:
        return 0

    data = extract_next_data(html)
    if not data:
        print(f"  [warn] No se encontró __NEXT_DATA__ en {url}")
        return 0

    listings = get_listings_from_next_data(data)
    if not listings:
        print(f"  [warn] 0 listings en {url} — keys disponibles: {list(data.get('props', {}).get('pageProps', {}).keys())}")
        return 0

    count = 0
    for raw in listings:
        parsed = parse_listing(raw, listing_type)
        if not parsed:
            continue

        entity_id = await get_or_create_entity(
            conn, name=parsed["title"], entity_type="Property",
            subtype=parsed["property_type"] or "inmueble",
            lat=parsed["lat"], lng=parsed["lng"],
            description=f"{parsed['listing_type'].title()} en {parsed['zone']}",
            origin_url=parsed["url"], all_names=[]
        )

        origin = [parsed["url"]]
        for key, (vtype, val) in {
            "listing_type":    ("string", parsed["listing_type"]),
            "address":         ("string", parsed["address"]),
            "zone":            ("string", parsed["zone"]),
            "source_url":      ("url",    parsed["url"]),
            "price_usd":       ("number", parsed["price_usd"]),
            "price_ars":       ("number", parsed["price_ars"]),
            "expenses_ars":    ("number", parsed["expenses_ars"]),
            "area_m2":         ("number", parsed["area_m2"]),
            "covered_area_m2": ("number", parsed["covered_area_m2"]),
            "rooms":           ("number", parsed["rooms"]),
            "bathrooms":       ("number", parsed["bathrooms"]),
            "parking":         ("number", parsed["parking"]),
        }.items():
            if val:
                await upsert_property(conn, entity_id, key, val, vtype,
                                       source_id, origins=origin)
        count += 1
    return count


async def main():
    print("=== Scraper Argenprop (Nstbrowser) ===")
    print("→ Conectando a Nstbrowser...")
    ws_url = await get_cdp_endpoint()
    print(f"  CDP: {ws_url}")

    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "argenprop")

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            total = 0
            for search in SEARCHES:
                listing_type = search["listing_type"]
                print(f"\n→ {listing_type.upper()} — {search['url']}")

                # Página 1
                count = await scrape_page(page, search["url"], listing_type, conn, source_id)
                print(f"  Página 1: {count} propiedades")
                total += count

                # Páginas 2 y 3
                for page_num in range(2, 4):
                    page_url = f"{search['url']}-pagina-{page_num}"
                    count = await scrape_page(page, page_url, listing_type, conn, source_id)
                    print(f"  Página {page_num}: {count} propiedades")
                    total += count
                    await asyncio.sleep(2)

            await browser.close()

        print(f"\n✓ Total: {total} propiedades procesadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
