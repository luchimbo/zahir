"""Guardia de acceso para INPI: no automatiza consultas sin API/términos validados."""
import os
def main():
    if not os.getenv("INPI_ACCESS_TOKEN"):
        raise RuntimeError("INPI bloqueado: falta INPI_ACCESS_TOKEN y la API/licencia oficial aún debe validarse.")
    raise RuntimeError("INPI bloqueado: configurar endpoint oficial y condiciones de uso antes de habilitar la ingesta.")
if __name__ == "__main__": main()
