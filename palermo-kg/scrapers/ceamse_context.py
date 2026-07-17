"""Control de granularidad de Ambiente Nación/CEAMSE."""
import argparse
def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args()
 print("CEAMSE: los indicadores evaluados son agregados de CABA; no se asignan a entidades ni barrios de Palermo.")
 if args.write: print("Sin escritura: requiere serie oficial con cobertura CABA identificada y período verificable.")
if __name__=="__main__":main()
