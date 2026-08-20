"""Ejecutor secuencial y explícito de fuentes del Palermo Knowledge Graph."""
import argparse
import asyncio
import importlib
import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.source_catalog import SOURCES, by_name
from scrapers.shared.db_helpers import ensure_source, finish_sync_run, get_conn, has_active_sync_run, mark_source_synced, register_source_policy, save_checkpoint, start_sync_run


SCHEDULE_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=31),
    "quarterly": timedelta(days=92),
    "annual": timedelta(days=366),
}

# Some legacy official connectors were deliberately dry-run by default. The
# catalog is their authorization boundary; only these reviewed modules receive
# the explicit write flag from scheduled execution.
WRITE_OPT_IN_MODULES = {
    "scrapers.gcba_urban_planning",
    "scrapers.gcba_cultural_archive",
    "scrapers.gcba_nightlife_events",
}


def is_due(source, scraped_at, now=None):
    """Return whether a freely runnable source needs its scheduled refresh."""
    interval = SCHEDULE_INTERVALS.get(source.refresh_schedule)
    if interval is None or source.mode != "public" or source.cost_policy != "free":
        return False
    if scraped_at is None:
        return True
    if scraped_at.tzinfo is None:
        scraped_at = scraped_at.replace(tzinfo=timezone.utc)
    return scraped_at <= (now or datetime.now(timezone.utc)) - interval


async def due_sources(sources=SOURCES, now=None):
    """Read last successful source timestamps and select only due public sources."""
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT source_name, scraped_at FROM sources")
    finally:
        await conn.close()
    scraped_at = {row["source_name"]: row["scraped_at"] for row in rows}
    return [source for source in sources if is_due(source, scraped_at.get(source.name), now)]


async def register_sources(sources=SOURCES):
    conn = await get_conn()
    try:
        for source in sources:
            source_id = await ensure_source(conn, source.name, source.url, source.tier)
            await register_source_policy(conn, source_id, data_class=source.data_class,
                                         refresh_schedule=source.refresh_schedule, access_mode=source.mode,
                                         cost_policy=source.cost_policy, license_url=source.license_url,
                                         enabled=source.cost_policy == "free")
    finally:
        await conn.close()


async def run_source(source, allow_paid=False):
    if source.mode == "approval":
        print(f"SKIP {source.name}: requiere autorización explícita de uso.")
        return "skipped"
    if source.cost_policy != "free" and not allow_paid:
        print(f"SKIP {source.name}: politica de costo '{source.cost_policy}' no habilitada.")
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
        await save_checkpoint(conn, source_id)
    finally:
        await conn.close()
    try:
        module = importlib.import_module(source.module)
        original_argv = sys.argv
        try:
            source_args = (*source.args, *( ("--write",) if source.module in WRITE_OPT_IN_MODULES and "--write" not in source.args else () ))
            sys.argv = [source.module, *source_args]
            result = module.main()
            if inspect.isawaitable(result):
                await result
        finally:
            sys.argv = original_argv
        print(f"OK   {source.name}")
        conn = await get_conn()
        try:
            await finish_sync_run(conn, run_id, "completed")
            await mark_source_synced(conn, source_id)
            await save_checkpoint(conn, source_id, retry_count=0)
        finally:
            await conn.close()
        return "ok"
    except Exception as exc:
        print(f"FAIL {source.name}: {type(exc).__name__}: {exc}")
        conn = await get_conn()
        try:
            await finish_sync_run(conn, run_id, "failed", error_message=f"{type(exc).__name__}: {exc}")
            await save_checkpoint(conn, source_id, error_code=type(exc).__name__, retry_count=1)
        finally:
            await conn.close()
        return "failed"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", choices=[s.name for s in SOURCES])
    parser.add_argument("--include-credentials", action="store_true")
    parser.add_argument("--allow-paid", action="store_true", help="Habilita conectores pagos tras una autorizacion explicita.")
    parser.add_argument("--register-only", action="store_true", help="Registra catalogo y politicas sin ejecutar conectores.")
    parser.add_argument("--retry-incomplete", action="store_true", help="Reintenta solo fuentes cuyo ultimo run fallo o quedo parcial.")
    parser.add_argument("--due", action="store_true", help="Ejecuta solo fuentes publicas gratuitas cuya frecuencia ya vencio.")
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
    # Always register the entire catalog: --due must also see sources never synced.
    await register_sources()
    if args.register_only:
        print({"registered": len(selected), "executed": 0})
        return
    if args.due:
        selected = await due_sources()
        print({"due": [source.name for source in selected]})
    if not args.include_credentials:
        selected = [s for s in selected if s.mode != "credential"]
    results = [await run_source(source, allow_paid=args.allow_paid) for source in selected]
    print({"ok": results.count("ok"), "skipped": results.count("skipped"), "failed": results.count("failed")})


if __name__ == "__main__":
    asyncio.run(main())
