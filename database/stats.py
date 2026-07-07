# -*- coding: utf-8 -*-
"""Репозиторий статистики для админ-панели (/stats): только чтение, агрегаты."""

from __future__ import annotations

from database.pool import get_pool


async def get_overview() -> dict:
    """
    Ключевые метрики бота одним запросом (подзапросы-агрегаты).

    Матчи считаем как неупорядоченные взаимные пары лайков (l1.from < l1.to,
    чтобы каждая пара учитывалась один раз).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              (SELECT count(*) FROM users)                                   AS total,
              (SELECT count(*) FROM users WHERE is_active)                   AS active,
              (SELECT count(*) FROM users WHERE role = 'seeker')             AS seekers,
              (SELECT count(*) FROM users WHERE role = 'provider')           AS providers,
              (SELECT count(*) FROM users
                 WHERE premium_until IS NOT NULL AND premium_until > now())  AS premium,
              (SELECT count(*) FROM users
                 WHERE created_at > now() - interval '1 day')                AS new_24h,
              (SELECT count(*) FROM users
                 WHERE created_at > now() - interval '7 days')               AS new_7d,
              (SELECT count(*) FROM likes)                                   AS likes,
              (SELECT count(*) FROM views)                                   AS views,
              (SELECT count(*) FROM likes l1 JOIN likes l2
                    ON l1.from_id = l2.to_id AND l1.to_id = l2.from_id
                 WHERE l1.from_id < l1.to_id)                               AS matches
            """
        )
        return dict(row)


async def top_cities(limit: int = 5) -> list:
    """Топ городов по числу анкет (для /stats)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT city, count(*) AS n
            FROM users
            WHERE city IS NOT NULL AND city <> ''
            GROUP BY city
            ORDER BY n DESC, city
            LIMIT $1
            """,
            limit,
        )
