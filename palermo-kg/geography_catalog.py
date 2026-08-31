"""Catálogo territorial oficial de CABA compartido por API e ingestas."""
from __future__ import annotations

import re
import unicodedata


CITY_NAME = "Ciudad Autónoma de Buenos Aires"

# Fuente: división administrativa oficial de GCBA.  El nombre es la clave
# canónica; el slug sólo es una interfaz estable para la API y la UI.
COMMUNES: dict[int, tuple[str, ...]] = {
    1: ("Retiro", "San Nicolás", "Puerto Madero", "San Telmo", "Monserrat", "Constitución"),
    2: ("Recoleta",),
    3: ("Balvanera", "San Cristóbal"),
    4: ("La Boca", "Barracas", "Parque Patricios", "Nueva Pompeya"),
    5: ("Almagro", "Boedo"),
    6: ("Caballito",),
    7: ("Flores", "Parque Chacabuco"),
    8: ("Villa Soldati", "Villa Riachuelo", "Villa Lugano"),
    9: ("Liniers", "Mataderos", "Parque Avellaneda"),
    10: ("Villa Real", "Monte Castro", "Versalles", "Floresta", "Vélez Sarsfield", "Villa Luro"),
    11: ("Villa General Mitre", "Villa Devoto", "Villa del Parque", "Villa Santa Rita"),
    12: ("Coghlan", "Saavedra", "Villa Urquiza", "Villa Pueyrredón"),
    13: ("Núñez", "Belgrano", "Colegiales"),
    14: ("Palermo",),
    15: ("Chacarita", "Villa Crespo", "La Paternal", "Villa Ortúzar", "Agronomía", "Parque Chas"),
}

# Denominaciones de uso habitual. No son barrios oficiales ni se usan para
# clasificar un punto sin geometría; permiten que el buscador preserve UX.
SUBAREA_ALIASES = {
    "palermo soho": "Palermo",
    "palermo hollywood": "Palermo",
    "palermo chico": "Palermo",
    "las canitas": "Palermo",
    "alto palermo": "Palermo",
    "las cañitas": "Palermo",
}

# Variantes presentes en datasets oficiales históricos o sin tildes.
DATASET_ALIASES = {
    "paternal": "La Paternal",
    "villa gral mitre": "Villa General Mitre",
    "nunez": "Núñez",
    "nu ez": "Núñez",
}


def normalize_geography(value: str | int | None) -> str:
    text = str(value or "").strip().lower()
    text = "".join(char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def slugify(value: str) -> str:
    return normalize_geography(value).replace(" ", "-")


NEIGHBORHOOD_TO_COMMUNE = {
    neighborhood: commune for commune, neighborhoods in COMMUNES.items() for neighborhood in neighborhoods
}
_NEIGHBORHOODS_BY_NORMALIZED = {normalize_geography(name): name for name in NEIGHBORHOOD_TO_COMMUNE}
_NEIGHBORHOODS_BY_NORMALIZED.update(
    {normalize_geography(alias): canonical for alias, canonical in SUBAREA_ALIASES.items()}
)
_NEIGHBORHOODS_BY_NORMALIZED.update(
    {normalize_geography(alias): canonical for alias, canonical in DATASET_ALIASES.items()}
)


def resolve_neighborhood(value: str | None) -> str | None:
    return _NEIGHBORHOODS_BY_NORMALIZED.get(normalize_geography(value))


def resolve_commune(value: str | int | None) -> int | None:
    normalized = normalize_geography(value)
    match = re.search(r"(?:comuna )?(1[0-5]|[1-9])$", normalized)
    return int(match.group(1)) if match else None


def geography_rows() -> list[dict]:
    rows = [{"name": CITY_NAME, "slug": "caba", "level": "city", "commune": None}]
    for commune, neighborhoods in COMMUNES.items():
        rows.append({"name": f"Comuna {commune}", "slug": f"comuna-{commune}", "level": "commune", "commune": commune})
        rows.extend({"name": name, "slug": slugify(name), "level": "neighborhood", "commune": commune} for name in neighborhoods)
    return rows
