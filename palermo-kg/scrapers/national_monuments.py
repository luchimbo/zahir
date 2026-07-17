"""Descubrimiento seguro del registro nacional de monumentos; no ingiere sin dataset verificable."""
import argparse
REGISTRY="https://www.argentina.gob.ar/cultura/monumentos"
def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args()
 print(f"Patrimonio nacional: fuente de descubrimiento {REGISTRY}; no hay descarga georreferenciada unificada validada.")
 if args.write: print("Sin escritura: se requiere CSV/GeoJSON oficial antes de cruzar con SMP/APH GCBA.")
if __name__=="__main__":main()
