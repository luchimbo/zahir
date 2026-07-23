"""Ejecutor secuencial y explícito de fuentes del Palermo Knowledge Graph."""
import argparse
import asyncio
import importlib
import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.source_catalog import SOURCES, by_name
from scrapers.shared.db_helpers import ensure_source, finish_sync_run, get_conn, has_active_sync_run, start_sync_run


async def register_sources(sources=SOURCES):
    conn = await get_conn()
    try:
        for source in sources:
            await ensure_source(conn, source.name, source.url, source.tier)
    finally:
        await conn.close()


async def run_source(source):
    if source.mode == "approval":
        print(f"SKIP {source.name}: requiere autorización explícita de uso.")
        return "skipped"
    if source.env_key and not os.getenv(source.env_key):
        print(f"SKIP {source.name}: falta {source.env_key}.")
        return "skipped"
    print(f"RUN  {source.name}: {source.description}")
    conn = await get_conn()
    try:
        source_id = await ensure_source(conn, source.name, source.url, source.tier)
        if await has_active_sync_run(conn, source_id):
            print(f"SKIP {source.name}: ya tiene una sincronizacion activa.")
            return "skipped"
        run_id = await start_sync_run(conn, source_id)
    finally:
        await conn.close()
    try:
        module = importlib.import_module(source.module)
        original_argv = sys.argv
        try:
            sys.argv = [source.module, *source.args]
            result = module.main()
            if inspect.isawaitable(result):
                await result
        finally:
            sys.argv = original_argv
        print(f"OK   {source.name}")
        conn = await get_conn()
        try:
            await finish_sync_run(conn, run_id, "completed")
        finally:
            await conn.close()
        return "ok"
    except Exception as exc:
        print(f"FAIL {source.name}: {type(exc).__name__}: {exc}")
        conn = await get_conn()
        try:
            await finish_sync_run(conn, run_id, "failed", error_message=f"{type(exc).__name__}: {exc}")
        finally:
            await conn.close()
        return "failed"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", choices=[s.name for s in SOURCES])
    parser.add_argument("--include-credentials", action="store_true")
    parser.add_argument("--retry-incomplete", action="store_true", help="Reintenta solo fuentes cuyo ultimo run fallo o quedo parcial.")
    args = parser.parse_args()
    if args.source:
        selected = [by_name(name) for name in args.source]
    elif args.retry_incomplete:
        conn = await get_conn()
        try:
            rows = await conn.fetch("""SELECT s.source_name FROM sources s
                JOIN source_sync_runs r ON r.source_id=s.id
                WHERE r.id=(SELECT r2.id FROM source_sync_runs r2 WHERE r2.source_id=s.id ORDER BY r2.started_at DESC LIMIT 1)
                AND r.status IN ('partial','failed')""")
            selected = [by_name(row["source_name"]) for row in rows if row["source_name"] in {item.name for item in SOURCES}]
        finally:
            await conn.close()
    else:
        selected = list(SOURCES)
    await register_sources(selected)
    if not args.include_credentials:
        selected = [s for s in selected if s.mode != "credential"]
    results = [await run_source(source) for source in selected]
    print({"ok": results.count("ok"), "skipped": results.count("skipped"), "failed": results.count("failed")})


if __name__ == "__main__":
    asyncio.run(main())
