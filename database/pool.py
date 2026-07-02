# -*- coding: utf-8 -*-
"""
Жизненный цикл пула соединений asyncpg + инициализация схемы и миграций.

Один пул на всё приложение: создаётся в bot.py при старте, закрывается при
остановке. Репозитории (users/matching/premium) берут соединения через get_pool.
"""

from __future__ import annotations  # поддержка синтаксиса "X | None" на Python 3.9

import asyncpg

from config import DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE, get_statement_cache_size
from database.models import ALL_TABLES, MIGRATIONS

# Глобальный пул соединений
_pool: asyncpg.Pool | None = None

# Ключ advisory-лока миграций: гарантирует, что при одновременном старте
# нескольких инстансов схему мигрирует только один (остальные ждут).
_MIGRATION_LOCK_ID = 776_211


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Создать пул соединений и подготовить таблицы.

    Размер пула ограничен (см. config.DB_POOL_*), чтобы при выкатке два
    контейнера укладывались в лимит клиентов пулера Supabase.
    """
    global _pool
    kwargs = {"min_size": DB_POOL_MIN_SIZE, "max_size": DB_POOL_MAX_SIZE}
    # Для transaction-mode пулера prepared statements отключают (statement_cache_size=0).
    scs = get_statement_cache_size()
    if scs is not None:
        kwargs["statement_cache_size"] = scs
    _pool = await asyncpg.create_pool(dsn=dsn, **kwargs)
    await init_db()
    return _pool


async def close_pool() -> None:
    """Закрыть пул соединений."""
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    """Получить активный пул (бросает ошибку, если не инициализирован)."""
    if _pool is None:
        raise RuntimeError("Пул соединений не инициализирован. Вызови create_pool().")
    return _pool


async def init_db() -> None:
    """
    Создать все таблицы (IF NOT EXISTS — дёшево) и применить НЕприменённые
    миграции ровно по одному разу, отмечая версию в schema_migrations.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        for query in ALL_TABLES:
            await conn.execute(query)

        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT NOW())"
        )

        # Только один инстанс мигрирует одновременно (остальные ждут лок).
        await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATION_LOCK_ID)
        try:
            rows = await conn.fetch("SELECT version FROM schema_migrations")
            applied = {r["version"] for r in rows}
            for version, query in MIGRATIONS:
                if version in applied:
                    continue
                await conn.execute(query)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1) "
                    "ON CONFLICT DO NOTHING",
                    version,
                )
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _MIGRATION_LOCK_ID)
