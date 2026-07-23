import os
import queue
import re
import ssl
from contextlib import asynccontextmanager
from urllib.parse import unquote, urlparse

import pymysql
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv

load_dotenv()

_pool = None


def _params(sql: str) -> str:
    """Convierte placeholders asyncpg ($1) al formato DB-API de MySQL."""
    return re.sub(r"\$\d+(?:::[A-Za-z_\[\]]+)?", "%s", sql)


def _tls_context() -> ssl.SSLContext:
    """TLS configurable; producción debe usar TIDB_TLS_VERIFY=true."""
    if os.getenv("TIDB_TLS_VERIFY", "false").lower() in {"1", "true", "yes"}:
        return ssl.create_default_context(cafile=os.getenv("TIDB_CA_CERT") or None)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class Connection:
    def __init__(self, raw_connection):
        self.raw_connection = raw_connection

    def _run(self, sql: str, args: tuple, one: bool = False, value: bool = False):
        with self.raw_connection.cursor() as cursor:
            cursor.execute(_params(sql), args)
            if value:
                row = cursor.fetchone()
                return next(iter(row.values())) if row else None
            if one:
                return cursor.fetchone()
            if cursor.description:
                return cursor.fetchall()
            self.raw_connection.commit()
            return cursor.rowcount

    async def fetch(self, sql: str, *args):
        return await run_in_threadpool(self._run, sql, args)

    async def fetchrow(self, sql: str, *args):
        return await run_in_threadpool(self._run, sql, args, True)

    async def fetchval(self, sql: str, *args):
        return await run_in_threadpool(self._run, sql, args, False, True)

    async def execute(self, sql: str, *args):
        return await run_in_threadpool(self._run, sql, args)

    async def close(self):
        """La vida útil la administra Pool.acquire()."""
        return None


class Pool:
    def __init__(self, config: dict, min_size: int = 1, max_size: int = 10):
        self.config = config
        self.max_size = max_size
        self._connections = queue.Queue(maxsize=max_size)
        self._created = 0
        for _ in range(min_size):
            self._connections.put(self._new_connection())

    def _new_connection(self):
        self._created += 1
        return pymysql.connect(**self.config)

    def _checkout(self):
        try:
            return self._connections.get_nowait()
        except queue.Empty:
            if self._created < self.max_size:
                return self._new_connection()
            return self._connections.get(timeout=15)

    def _checkin(self, connection):
        try:
            connection.rollback()
            self._connections.put_nowait(connection)
        except Exception:
            try:
                connection.close()
            finally:
                self._created -= 1

    @asynccontextmanager
    async def acquire(self):
        raw = await run_in_threadpool(self._checkout)
        try:
            yield Connection(raw)
        finally:
            await run_in_threadpool(self._checkin, raw)

    async def close(self):
        def close_all():
            while True:
                try:
                    self._connections.get_nowait().close()
                except queue.Empty:
                    return
        await run_in_threadpool(close_all)

async def get_pool() -> Pool:
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL no configurada")
        url = urlparse(database_url)
        if url.scheme not in {"mysql", "mysql+pymysql"}:
            raise RuntimeError("DATABASE_URL debe usar el esquema mysql:// para TiDB")
        _pool = Pool({
            "host": url.hostname,
            "port": url.port or 4000,
            "user": unquote(url.username or ""),
            "password": unquote(url.password or ""),
            "database": os.getenv("DATABASE_NAME") or url.path.lstrip("/"),
            "ssl": _tls_context(),
            "cursorclass": pymysql.cursors.DictCursor,
            "connect_timeout": 15,
            "autocommit": False,
        })
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
    _pool = None
