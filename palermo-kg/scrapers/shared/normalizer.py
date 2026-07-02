"""
Normalizador de datos para el Knowledge Graph Palermo.

REGLAS (ver db/RULES.md sección 9):
  - Nombres de entidades y valores de texto → Title Case
  - Keys de properties → inglés, snake_case (no tocar aquí, definir en el scraper)
  - Siglas conocidas se preservan en UPPER: SA, SRL, SAS, CABA, IGJ, etc.
  - Booleanos → "true" / "false"
  - Números → string limpio sin formato
"""

import re

# Siglas que deben mantenerse en UPPER aunque estén en medio del texto
SIGLAS = {
    "SA", "SRL", "SAS", "SAU", "SCR", "SCA",
    "CABA", "IGJ", "INPI", "ARBA", "AGIP", "GCBA",
    "SA.", "SRL.", "S.A.", "S.R.L.", "S.A.S.",
}

# Preposiciones y artículos en español que van en minúscula (como en Title Case español)
LOWER_WORDS = {
    "de", "del", "la", "las", "los", "el", "y", "e", "en",
    "a", "al", "por", "para", "con", "sin", "sobre", "entre",
}


def normalize_name(text: str) -> str:
    """
    Convierte un nombre de entidad a Title Case respetando siglas.
    Ej: "EL DESNIVEL PALERMO" → "El Desnivel Palermo"
        "GLOBAL OIL S.R.L." → "Global Oil S.R.L."
    """
    if not text:
        return ""

    text = text.strip()
    words = text.split()
    result = []

    for i, word in enumerate(words):
        upper = word.upper().rstrip(".")
        # Preservar siglas conocidas tal como vienen (con puntos si las tenían)
        if upper in SIGLAS or word.upper() in SIGLAS:
            result.append(word.upper())
        # Preposiciones/artículos en minúscula (excepto primera palabra)
        elif word.lower() in LOWER_WORDS and i > 0:
            result.append(word.lower())
        else:
            result.append(word.capitalize())

    return " ".join(result)


def normalize_value(text: str) -> str:
    """
    Convierte un valor de texto a Title Case simple.
    Ej: "ACTIVA" → "Activa", "capital federal" → "Capital Federal"
    """
    if not text:
        return ""
    return text.strip().title()


def normalize_bool(value) -> str:
    """Convierte cualquier booleano a 'true' o 'false'."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return "true" if value.lower() in ("true", "1", "yes", "si", "sí") else "false"
    return "true" if value else "false"


def normalize_number(value) -> str | None:
    """Convierte número a string limpio."""
    if value is None:
        return None
    try:
        f = float(str(value).replace(",", ".").strip())
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except (ValueError, TypeError):
        return None


def clean_cuit(cuit: str) -> str | None:
    """Normaliza CUIT: elimina guiones y espacios."""
    if not cuit:
        return None
    cleaned = re.sub(r"[^0-9]", "", cuit.strip())
    return cleaned if len(cleaned) == 11 else cleaned or None
