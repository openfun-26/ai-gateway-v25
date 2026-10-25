"""SQLite (WAL) 异步访问层：单写连接串行化 + 读连接，避免 database is locked。"""
import asyncio
import json
from typing import Any, Iterable, Optional

import aiosqlite

from .config import DB_PATH


class Database:
    def __init__(self):
        self._w: aiosqlite.Connection | None = None
        self._r: aiosqlite.Connection | None = None
        self._wlock = asyncio.Lock()

    async def connect(self):
        self._w = await aiosqlite.connect(str(DB_PATH))
        self._w.row_factory = aiosqlite.Row
        await self._w.execute("PRAGMA journal_mode=WAL")
        await self._w.execute("PRAGMA synchronous=NORMAL")
        await self._w.execute("PRAGMA busy_timeout=5000")
        self._r = await aiosqlite.connect(str(DB_PATH))
        self._r.row_factory = aiosqlite.Row
        await self._r.execute("PRAGMA busy_timeout=5000")
        await self._r.execute("PRAGMA journal_mode=WAL")

    async def close(self):
        for c in (self._w, self._r):
            if c:
                await c.close()

    # ---------- 写（串行化） ----------
    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """执行写语句，返回 lastrowid。"""
        async with self._wlock:
            cur = await self._w.execute(sql, tuple(params))
            await self._w.commit()
            return cur.lastrowid or 0

    async def executemany(self, sql: str, seq: list) -> None:
        async with self._wlock:
            await self._w.executemany(sql, seq)
            await self._w.commit()

    async def executescript(self, sql: str) -> None:
        async with self._wlock:
            await self._w.executescript(sql)
            await self._w.commit()

    # ---------- 读（可并发） ----------
    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        cur = await self._r.execute(sql, tuple(params))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
        cur = await self._r.execute(sql, tuple(params))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def scalar(self, sql: str, params: Iterable[Any] = (), default=0):
        row = await self.fetchone(sql, params)
        if not row:
            return default
        v = next(iter(row.values()))
        return v if v is not None else default


db = Database()


def jloads(s, default):
    if not s:
        return default
    try:
        v = json.loads(s)
        return v if isinstance(v, type(default)) or v is None else default
    except Exception:
        return default
