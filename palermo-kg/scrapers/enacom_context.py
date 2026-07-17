"""Control de granularidad ENACOM para impedir atribuciones falsas a Palermo."""
import argparse
def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args()
 print("ENACOM: los indicadores publicados evaluados son nacionales/provinciales; sin geometría CABA/radio no se ingieren.")
 if args.write: print("Sin escritura: no se atribuyen promedios provinciales a Palermo.")
if __name__=="__main__":main()
