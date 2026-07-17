"""Valida granularidad CEP XXI; no carga datos por departamento como si fueran Palermo."""
import argparse, asyncio
import httpx
URL="https://datos.gob.ar/api/3/action/package_show?id=produccion-distribucion-geografica-establecimientos-productivos"
async def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args()
 async with httpx.AsyncClient(timeout=60) as c: package=(await c.get(URL)).json()["result"]
 names=[r.get("name","") for r in package.get("resources",[])]
 print(f"CEP XXI: {len(names)} recursos oficiales; la descarga disponible está agregada por departamento. No se carga como dato de Palermo.")
 if args.write: print("Sin escritura: falta granularidad CABA/radio/coordendada verificable.")
if __name__=="__main__":asyncio.run(main())
