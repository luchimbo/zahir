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
from scrapers.shared.contract import SourceResult
from scrapers.shared.db_helpers import (ensure_source, finish_sync_run, get_conn, has_active_sync_run,
    mark_source_synced, register_source_policy, save_checkpoint, save_run_metrics, set_source_enabled,
    start_sync_run)


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
        rows = await conn.fetch("""SELECT s.source_name, s.scraped_at, COALESCE(p.enabled, FALSE) enabled
            FROM sources s LEFT JOIN source_policies p ON p.source_id=s.id""")
    finally:
        await conn.close()
    scraped_at = {row["source_name"]: row["scraped_at"] for row in rows}
    enabled = {row["source_name"]: bool(row["enabled"]) for row in rows}
    return [source for source in sources if enabled.get(source.name, False) and is_due(source, scraped_at.get(source.name), now)]


async def register_sources(sources=SOURCES):
    conn = await get_conn()
    try:
        existing_rows = await conn.fetch("SELECT id, source_name FROM sources")
        source_ids = {row["source_name"]: str(row["id"]) for row in existing_rows}
        for source in sources:
            if source.name not in source_ids:
                source_ids[source.name] = await ensure_source(conn, source.name, source.url, source.tier)
        rows = [(source_ids[source.name], source.data_class, source.refresh_schedule, source.mode,
                 source.cost_policy, source.license_url, False) for source in sources]
        await conn.executemany(
            """INSERT INTO source_policies (source_id,data_class,refresh_schedule,access_mode,cost_policy,license_url,enabled)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               ON DUPLICATE KEY UPDATE data_class=VALUES(data_class),refresh_schedule=VALUES(refresh_schedule),
                 access_mode=VALUES(access_mode),cost_policy=VALUES(cost_policy),license_url=VALUES(license_url)""", rows)
    finally:
        await conn.close()


async def run_source(source, allow_paid=False, pilot_limit=None, promote=False, validate_only=False, include_approval=False,
                     scope="caba", neighborhood=None, commune=None):
    if scope == "caba" and not source.supports_contract:
        print(f"SKIP {source.name}: adaptador heredado aún limitado a Palermo; migrarlo al contrato territorial antes de cargar CABA.")
        return "skipped"
    if source.mode == "approval" and not include_approval:
        print(f"SKIP {source.name}: requiere autorización explícita de uso.")
        return "skipped"
    if source.cost_policy != "free" and not allow_paid:
        print(f"SKIP {source.name}: politica de costo '{source.cost_policy}' no habilitada.")
        return "skipped"
    if source.env_key and not os.getenv(source.env_key):
        print(f"SKIP {source.name}: falta {source.env_key}.")
        return "skipped"
    if pilot_limit is not None and not source.supports_contract:
        print(f"SKIP {source.name}: adaptador heredado sin contrato de piloto; requiere migración explícita.")
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
            source_args = list(source.args)
            if source.module in WRITE_OPT_IN_MODULES and "--write" not in source_args:
                source_args.append("--write")
            if source.supports_contract:
                source_args.extend(("--scope", scope))
                if neighborhood:
                    source_args.extend(("--neighborhood", neighborhood))
                if commune:
                    source_args.extend(("--commune", str(commune)))
                if not validate_only and "--write" not in source_args:
                    source_args.append("--write")
                if pilot_limit is not None:
                    source_args.extend(("--limit", str(pilot_limit)))
            sys.argv = [source.module, *source_args]
            result = module.main()
            if inspect.isawaitable(result):
                result = await result
            if result is None:
                result = SourceResult(coverage={"contract": "legacy"})
            if not isinstance(result, SourceResult):
                raise TypeError(f"{source.module} debe devolver SourceResult; devolvió {type(result).__name__}")
        finally:
            sys.argv = original_argv
        promoted = result.ok and result.accepted >= source.min_pilot_records and result.written >= source.min_pilot_records
        status = "completed" if result.ok else "partial"
        error = "; ".join(result.errors) or None
        conn = await get_conn()
        try:
            await finish_sync_run(conn, run_id, status, result.seen, result.written, error)
            await save_run_metrics(conn, run_id, coverage={**result.coverage, "accepted": result.accepted, "skipped": result.skipped}, checkpoint_after=result.checkpoint)
            if result.ok:
                await mark_source_synced(conn, source_id)
                await save_checkpoint(conn, source_id, cursor_value=result.checkpoint, retry_count=0)
            if pilot_limit is not None and promote and promoted:
                await set_source_enabled(conn, source_id, True)
        finally:
            await conn.close()
        decision = "promoted" if pilot_limit is not None and promote and promoted else "ok"
        print(f"OK   {source.name}: {result.as_dict()} ({decision})")
        return decision
    except Exception as exc:
        print(f"FAIL {source.name}: {type(exc).__name__}: {exc}")
        conn = await get_conn()
        try:
            await finish_sync_run(conn, run_id, "failed", error_message=f"{type(exc).__name__}: {exc}")
            await save_run_metrics(conn, run_id, error_code=type(exc).__name__)
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
    parser.add_argument("--pilot", action="store_true", help="Escribe una muestra limitada de adaptadores con contrato.")
    parser.add_argument("--limit", type=int, help="Límite para --pilot; por defecto usa el catálogo.")
    parser.add_argument("--promote", action="store_true", help="Habilita una fuente que supera el piloto.")
    parser.add_argument("--validate", action="store_true", help="Valida adaptadores con contrato sin escribir.")
    parser.add_argument("--include-approval", action="store_true", help="Incluye fuentes approval tras una revisión explícita de términos.")
    parser.add_argument("--status", action="store_true", help="Muestra políticas y última ejecución sin ejecutar.")
    parser.add_argument("--scope", choices=("caba", "palermo"), default="caba", help="Ámbito para conectores ya migrados al contrato.")
    parser.add_argument("--neighborhood", help="Barrio oficial para conectores con contrato.")
    parser.add_argument("--commune", type=int, choices=range(1, 16), help="Comuna para conectores con contrato.")
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
    if args.status:
        conn = await get_conn()
        try:
            rows = await conn.fetch("""SELECT s.source_name, p.enabled, p.refresh_schedule, s.scraped_at
                FROM sources s LEFT JOIN source_policies p ON p.source_id=s.id ORDER BY s.source_name""")
            print([dict(row) for row in rows])
        finally:
            await conn.close()
        return
    if args.register_only:
        print({"registered": len(selected), "executed": 0})
        return
    if args.due:
        selected = await due_sources()
        print({"due": [source.name for source in selected]})
    if not args.include_credentials:
        selected = [s for s in selected if s.mode != "credential"]
    results = [await run_source(source, allow_paid=args.allow_paid,
                                pilot_limit=(args.limit or source.pilot_limit) if args.pilot else None,
                                promote=args.promote, validate_only=args.validate,
                                include_approval=args.include_approval, scope=args.scope,
                                neighborhood=args.neighborhood, commune=args.commune) for source in selected]
    print({"ok": results.count("ok"), "promoted": results.count("promoted"), "skipped": results.count("skipped"), "failed": results.count("failed")})


if __name__ == "__main__":
    asyncio.run(main())
