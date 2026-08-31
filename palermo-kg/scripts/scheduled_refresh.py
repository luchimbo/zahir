"""Punto de entrada estable para Windows Task Scheduler.

Mantiene una cantidad acotada de logs y nunca ejecuta más que las fuentes ya
promovidas en `source_policies`.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
MAX_LOGS = 30


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    for old in sorted(LOG_DIR.glob("refresh-*.log"))[:-MAX_LOGS]:
        old.unlink()
    log_path = LOG_DIR / f"refresh-{datetime.now():%Y%m%d-%H%M%S}.log"
    command = [sys.executable, str(ROOT / "scripts" / "run_sources.py"), "--due"]
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
