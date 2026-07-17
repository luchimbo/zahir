"""Cliente de respaldo para la API oficial nacional GeorefAR.

USIG sigue siendo la fuente preferida dentro de CABA. Este cliente sólo se usa
cuando USIG no puede resolver una dirección o para añadir códigos territoriales.
"""
from dataclasses import dataclass
import httpx

BASE_URL = "https://apis.datos.gob.ar/georef/api/v2.0"


@dataclass(frozen=True)
class GeorefAddress:
    normalized: str
    lat: float
    lng: float
    province_id: str | None = None
    department_id: str | None = None


async def geocode_address(client: httpx.AsyncClient, address: str) -> GeorefAddress | None:
    response = await client.get(f"{BASE_URL}/direcciones", params={"direccion": address, "max": 1})
    if response.status_code != 200:
        return None
    rows = response.json().get("direcciones") or []
    if not rows:
        return None
    row = rows[0]
    point = row.get("ubicacion") or {}
    try:
        return GeorefAddress(
            normalized=row.get("nomenclatura") or address,
            lat=float(point["lat"]), lng=float(point["lon"]),
            province_id=(row.get("provincia") or {}).get("id"),
            department_id=(row.get("departamento") or {}).get("id"),
        )
    except (KeyError, TypeError, ValueError):
        return None


async def reverse_geocode(client: httpx.AsyncClient, lat: float, lng: float) -> dict:
    """Devuelve unidades territoriales oficiales disponibles para un punto."""
    response = await client.get(f"{BASE_URL}/ubicacion", params={"lat": lat, "lon": lng})
    return response.json() if response.status_code == 200 else {}
