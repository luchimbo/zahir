"""Cliente mínimo para normalizar y geocodificar direcciones de CABA con USIG."""

import json
import re
from dataclasses import dataclass

import httpx
from scrapers.shared.georef import geocode_address as georef_address

GEOCODER_URL = "http://ws.usig.buenosaires.gob.ar/geocoder/2.2/geocoding"
CONVERTER_URL = "http://ws.usig.buenosaires.gob.ar/rest/convertir_coordenadas"


@dataclass(frozen=True)
class GeocodedAddress:
    street: str
    number: int
    lat: float
    lng: float
    backend: str = "usig"


def split_street_number(address: str) -> tuple[str, int] | None:
    """Extrae la última altura numérica de una dirección postal simple."""
    match = re.match(r"^\s*(.*?)\s+(\d{1,5})(?:\.0+)?\s*$", address or "")
    if not match:
        return None
    street = match.group(1).strip(" ,.-")
    number = int(match.group(2))
    return (street, number) if street else None


async def geocode_address(client: httpx.AsyncClient, address: str) -> GeocodedAddress | None:
    """Geocodifica una dirección CABA y convierte GKBA a lon/lat WGS84."""
    parsed = split_street_number(address)
    if not parsed:
        fallback = await georef_address(client, address)
        return GeocodedAddress(address, 0, fallback.lat, fallback.lng, "georef") if fallback else None
    street, number = parsed
    response = await client.get(GEOCODER_URL, params={"cod_calle": street, "altura": number})
    if response.status_code != 200:
        fallback = await georef_address(client, address)
        return GeocodedAddress(street, number, fallback.lat, fallback.lng, "georef") if fallback else None
    try:
        # USIG alterna entre JSON puro y un objeto envuelto en paréntesis.
        gkba = response.json() if response.text.lstrip().startswith("{") else json.loads(response.text.strip().strip("()"))
        x, y = gkba["x"], gkba["y"]
    except (TypeError, KeyError, ValueError):
        fallback = await georef_address(client, address)
        return GeocodedAddress(street, number, fallback.lat, fallback.lng, "georef") if fallback else None
    response = await client.get(CONVERTER_URL, params={"x": x, "y": y, "output": "lonlat"})
    if response.status_code != 200:
        fallback = await georef_address(client, address)
        return GeocodedAddress(street, number, fallback.lat, fallback.lng) if fallback else None
    try:
        result = response.json()["resultado"]
        return GeocodedAddress(street, number, float(result["y"]), float(result["x"]))
    except (TypeError, KeyError, ValueError):
        return None
