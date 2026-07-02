# -*- coding: utf-8 -*-
"""Репозиторий премиума (Telegram Stars): статус, активация, «кто лайкнул»."""

from database.pool import get_pool


async def is_premium(telegram_id: int) -> bool:
    """Активен ли премиум у пользователя (с учётом срока действия)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT (premium_until IS NOT NULL AND premium_until > now()) "
            "FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        return bool(row)


async def activate_premium(telegram_id: int, days: int) -> None:
    """
    Активировать/продлить премиум на `days` дней.
    Если премиум ещё активен — срок наращивается поверх текущего.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET is_premium = TRUE,
                premium_until = GREATEST(COALESCE(premium_until, now()), now())
                                + make_interval(days => $2)
            WHERE telegram_id = $1
            """,
            telegram_id, days,
        )


async def get_premium_until(telegram_id: int):
    """Вернуть дату окончания премиума (или None)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT premium_until FROM users WHERE telegram_id = $1", telegram_id
        )


async def who_liked_me(telegram_id: int, limit: int = 20) -> list:
    """Список активных пользователей, которые лайкнули меня (премиум-фича)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT u.*, l.is_super, l.created_at AS liked_at
            FROM likes l
            JOIN users u ON u.telegram_id = l.from_id
            WHERE l.to_id = $1 AND u.is_active = TRUE
            ORDER BY l.created_at DESC
            LIMIT $2
            """,
            telegram_id, limit,
        )
