"""Ejecutor manual de fuentes oficiales, seguro por defecto (dry-run)."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "urban_code": "scrapers/gcba_urban_code.py",
    "ramps": "scrapers/gcba_accessibility_ramps.py",
    "clubs": "scrapers/gcba_clubs.py",
    "libraries": "scrapers/gcba_libraries.py",
    "police": "scrapers/gcba_police_stations.py",
    "community": "scrapers/gcba_community_institutions.py",
    "worship": "scrapers/gcba_places_of_worship.py",
    "healthy_stations": "scrapers/gcba_healthy_stations.py",
    "labor": "scrapers/gcba_labor_integration.py",
    "inspections": "scrapers/gcba_inspections.py",
    "padron_educativo": "scrapers/national_education.py",
    "indec_censo": "scrapers/indec_census.py",
    "sinca": "scrapers/sinca_culture.py",
    "refes_historical": "scrapers/refes_historical.py",
    "transporte_rmba": "scrapers/transporte_rmba.py",
    "cep_xxi": "scrapers/cep_xxi.py",
    "enacom_context": "scrapers/enacom_context.py",
    "national_monuments": "scrapers/national_monuments.py",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    parser.add_argument("--write", action="store_true", help="Persistir; sin esta opción sólo valida cobertura.")
    args = parser.parse_args()
    selected = SOURCES if args.source == "all" else {args.source: SOURCES[args.source]}
    for name, path in selected.items():
        # -m preserva la raíz del proyecto para imports `scrapers.*`.
        command = [sys.executable, "-m", path.removesuffix(".py").replace("/", ".")]
        if args.write:
            command.append("--write")
        print(f"\n== {name} ==")
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
