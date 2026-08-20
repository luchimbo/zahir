"""Guardia de acceso ARCA: exige credenciales WSAA de una organización autorizada."""
import os
def main():
    missing=[key for key in ("ARCA_CERT_PATH","ARCA_PRIVATE_KEY_PATH","ARCA_CUIT") if not os.getenv(key)]
    if missing: raise RuntimeError("ARCA bloqueado: faltan " + ", ".join(missing))
    raise RuntimeError("ARCA bloqueado: falta configurar WSAA y la representación autorizada.")
if __name__ == "__main__": main()
