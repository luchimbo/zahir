"""Filtro territorial común para conectores de CABA.

El bounding box sólo descarta puntos claramente ajenos a CABA; la asignación
oficial barrio/comuna se realiza después con los polígonos GCBA en
``scrapers.geography``. Esto evita perder datos válidos de los bordes.
"""
from __future__ import annotations

from geography_catalog import NEIGHBORHOOD_TO_COMMUNE, resolve_commune, resolve_neighborhood

CABA_BBOX = (-34.706, -34.526, -58.531, -58.335)
PALERMO_BBOX = (-34.615, -34.555, -58.455, -58.390)


def point_in_box(lat, lng, box) -> bool:
    try:
        return box[0] <= float(lat) <= box[1] and box[2] <= float(lng) <= box[3]
    except (TypeError, ValueError):
        return False


def point_in_caba(lat, lng) -> bool:
    return point_in_box(lat, lng, CABA_BBOX)


def record_in_scope(*, lat=None, lng=None, row_neighborhood=None, row_commune=None,
                    scope="caba", neighborhood=None, commune=None) -> bool:
    """Acepta registros CABA completos y permite acotar un piloto territorial."""
    official_neighborhood = resolve_neighborhood(row_neighborhood)
    official_commune = resolve_commune(row_commune)
    point_matches = point_in_caba(lat, lng)

    if scope == "palermo":
        if official_neighborhood == "Palermo" or official_commune == 14:
            base_matches = True
        else:
            base_matches = point_in_box(lat, lng, PALERMO_BBOX)
    else:
        base_matches = point_matches or official_neighborhood is not None or official_commune in range(1, 16)
    if not base_matches:
        return False

    expected_neighborhood = resolve_neighborhood(neighborhood) if neighborhood else None
    expected_commune = resolve_commune(commune) if commune is not None else None
    if expected_neighborhood:
        return official_neighborhood == expected_neighborhood
    if expected_commune:
        if official_commune is not None:
            return official_commune == expected_commune
        return official_neighborhood is not None and NEIGHBORHOOD_TO_COMMUNE[official_neighborhood] == expected_commune
    return True
