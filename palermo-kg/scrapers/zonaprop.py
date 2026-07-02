"""
Scraper: Zonaprop via Nstbrowser + Playwright
Fuente: https://www.zonaprop.com.ar
Tier 2 — Anti-bot bypass con Nstbrowser.

Nstbrowser lanza un browser con fingerprint real.
Nos conectamos via CDP y usamos Playwright para navegar.
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

BASE_URL = "https://www.zonaprop.com.ar"

SEARCHES = [
    {"url": f"{BASE_URL}/inmuebles-alquiler-palermo.html", "listing_type": "rental"},
    {"url": f"{BASE_URL}/inmuebles-venta-palermo.html",   "listing_type": "sale"},
]


async def get_cdp_endpoint() -> str:
    """Obtiene el CDP websocket URL de un browser ya corriendo en Nstbrowser."""
    headers = {"x-api-key": API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        # Listar browsers activos
        r = await client.get(f"{NSTBROWSER_HOST}/api/v2/browsers", headers=headers)
        r.raise_for_status()
        browsers = r.json().get("data", [])

        if not browsers:
            raise RuntimeError("No hay browsers corriendo en Nstbrowser. Abrí uno desde la app.")

        # Usar el primer browser activo
        browser = next((b for b in browsers if b.get("running")), browsers[0])
        port = browser["remoteDebuggingPort"]
        profile = browser.get("name", "unknown")
        print(f"  Usando perfil: '{profile}' (puerto {port})")

        # Obtener el websocket URL via CDP
        r2 = await client.get(f"http://localhost:{port}/json/version")
        r2.raise_for_status()
        ws_url = r2.json().get("webSocketDebuggerUrl")

    if not ws_url:
        raise RuntimeError("No se pudo obtener webSocketDebuggerUrl")
    return ws_url


def extract_preloaded_state(html: str) -> dict | None:
    match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def parse_listing(listing: dict, listing_type: str) -> dict | None:
    try:
        title = listing.get("title", "").strip()
        if not title:
            return None

        geo = listing.get("geo", {})
        lat = geo.get("lat")
        lng = geo.get("lon")

        address = listing.get("address", "")
        zone = listing.get("zone", "")
        url = BASE_URL + listing.get("url", "")

        prices = listing.get("prices", [])
        price_usd, price_ars = None, None
        for p in prices:
            currency = p.get("currency", "")
            amount = p.get("amount")
            if currency == "USD" and amount:
                price_usd = amount
            elif currency == "ARS" and amount:
                price_ars = amount

        attrs = {a.get("id"): a.get("value") for a in listing.get("attributes", [])}
        area_total   = attrs.get("TOTAL_SURFACE") or attrs.get("ROOFED_SURFACE")
        area_covered = attrs.get("ROOFED_SURFACE")
        rooms        = attrs.get("ROOMS")
        bathrooms    = attrs.get("FULL_BATHROOMS") or attrs.get("BATHROOMS")
        parking      = attrs.get("PARKING_LOTS")

        expenses     = listing.get("expenses", {})
        expenses_ars = expenses.get("amount") if expenses else None
        property_type = listing.get("realEstateType", {}).get("name", "").lower()

        return {
            "title": title, "lat": float(lat) if lat else None,
            "lng": float(lng) if lng else None,
            "address": address, "zone": zone, "url": url,
            "listing_type": listing_type, "property_type": property_type,
            "price_usd": str(price_usd) if price_usd else None,
            "price_ars": str(price_ars) if price_ars else None,
            "expenses_ars": str(expenses_ars) if expenses_ars else None,
            "area_m2": str(area_total) if area_total else None,
            "covered_area_m2": str(area_covered) if area_covered else None,
            "rooms": str(rooms) if rooms else None,
            "bathrooms": str(bathrooms) if bathrooms else None,
            "parking": str(parking) if parking else None,
        }
    except Exception:
        return None


async def scrape_page(page, url: str, listing_type: str, conn, source_id: str) -> int:
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Esperar hasta que desaparezca el captcha (máx 2 minutos)
    print("    [esperando página... resolvé el captcha si aparece]")
    for _ in range(24):
        await page.wait_for_timeout(5000)
        content = await page.content()
        if "__PRELOADED_STATE__" in content:
            break
        print("    [esperando...]")
    else:
        print("    [timeout esperando captcha]")
        return 0

    html = await page.content()
    state = extract_preloaded_state(html)

    if not state:
        print(f"  [warn] No se encontró __PRELOADED_STATE__ en {url}")
        return 0

    listings = (
        state.get("listPostings") or
        state.get("postings") or
        state.get("posting", {}).get("postings") or
        []
    )
    if not listings:
        for key in state:
            if isinstance(state[key], dict):
                candidate = state[key].get("postings", [])
                if candidate:
                    listings = candidate
                    break

    count = 0
    for raw in listings:
        parsed = parse_listing(raw, listing_type)
        if not parsed:
            continue

        entity_id = await get_or_create_entity(
            conn, name=parsed["title"], entity_type="Property",
            subtype=parsed["property_type"] or "inmueble",
            lat=parsed["lat"], lng=parsed["lng"],
            description=f"{parsed['listing_type'].title()} en {parsed['zone'] or 'Palermo'}",
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
    print("=== Scraper Zonaprop (Nstbrowser) ===")

    print("→ Conectando a Nstbrowser...")
    ws_url = await get_cdp_endpoint()
    print(f"  CDP: {ws_url}")

    conn = await get_conn()
    try:
        source_id = await get_source_id(conn, "zonaprop")

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            total = 0
            for search in SEARCHES:
                listing_type = search["listing_type"]
                print(f"\n→ {listing_type.upper()}")

                for page_num in range(1, 4):
                    if page_num == 1:
                        url = search["url"]
                    else:
                        url = search["url"].replace(".html", f"-pagina-{page_num}.html")

                    print(f"  Página {page_num}: {url}")
                    count = await scrape_page(page, url, listing_type, conn, source_id)
                    print(f"    → {count} propiedades")
                    total += count
                    await asyncio.sleep(2)

            await browser.close()

        print(f"\n✓ Total: {total} propiedades procesadas")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
