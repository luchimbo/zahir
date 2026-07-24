"""Aplica el esquema idempotente compatible con TiDB Cloud."""
import os
import ssl
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymysql
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS = [Path("db/tidb_init.sql"), Path("db/11_igj_history.sql")]


def tls_context():
    """TiDB Cloud requiere TLS; el gateway actual presenta cadena vencida."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def connect():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no configurada")
    url = urlparse(database_url)
    if url.scheme not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError("DATABASE_URL debe ser mysql:// para TiDB")
    return pymysql.connect(
        host=url.hostname, port=url.port or 4000,
        user=unquote(url.username or ""), password=unquote(url.password or ""),
        database=os.getenv("DATABASE_NAME") or url.path.lstrip("/"), ssl=tls_context(),
        autocommit=False,
    )


def main():
    conn = connect()
    try:
        with conn.cursor() as cursor:
            for migration in MIGRATIONS:
                print(f"Aplicando {migration}...")
                for statement in migration.read_text(encoding="utf-8").split(";"):
                    sql = "\n".join(
                        line for line in statement.splitlines()
                        if not line.strip().startswith("--")
                    ).strip()
                    if sql:
                        try:
                            cursor.execute(sql)
                        except pymysql.err.OperationalError as exc:
                            # TiDB no soporta CREATE INDEX IF NOT EXISTS en todas las versiones.
                            if exc.args and exc.args[0] == 1061:
                                print("  indice ya existente; se omite")
                                continue
                            raise
            conn.commit()
        print("OK migraciones aplicadas")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
