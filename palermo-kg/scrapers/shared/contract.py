"""Contrato seguro y observable para adaptadores de fuentes.

Los adaptadores nuevos deben devolver :class:`SourceResult`.  El runner usa ese
resultado para decidir la promoción de un piloto y para guardar métricas sin
inferirlas de los mensajes de consola.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field


@dataclass
class SourceResult:
    seen: int = 0
    accepted: int = 0
    written: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    coverage: dict[str, int] = field(default_factory=dict)
    checkpoint: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return asdict(self)


def add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--write", action="store_true", help="Persiste los datos; sin esta opción sólo valida.")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de registros aceptados.")
    parser.add_argument("--since", default=None, help="Cursor o fecha de origen, si la fuente la soporta.")
    parser.add_argument("--scope", choices=("caba", "palermo", "national"), default="caba", help="Ámbito territorial; CABA es el valor operativo por defecto. 'national' es para fuentes sin geografía (ver db/RULES.md §11).")
    parser.add_argument("--neighborhood", help="Barrio oficial de CABA para acotar una ejecución.")
    parser.add_argument("--commune", type=int, choices=range(1, 16), help="Comuna para acotar una ejecución.")


def bounded(items, limit: int | None):
    """Aplica el límite después del filtro territorial, para que el piloto sea útil."""
    if limit is None:
        return items
    return items[:max(0, limit)]
