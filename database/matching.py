# -*- coding: utf-8 -*-
"""Репозиторий мэтчинга: подбор кандидата, отметки просмотров и лайков."""

from __future__ import annotations

import asyncpg

from database.pool import get_pool


async def get_next_candidate(viewer_id: int) -> asyncpg.Record | None:
    """
    Найти следующего подходящего кандидата для смотрящего (по его telegram_id).

    Данные смотрящего (город, preferred_gender, роль) берутся тем же запросом
    через CTE `me` — не нужен отдельный get_user перед каждым свайпом.

    Фильтры (без бюджета):
      1. Тот же город
      2. Пол кандидата совпадает с preferred_gender смотрящего
         (парни видят парней, девушки — девушек)
      3. Противоположная роль (ищущий видит объявления, сдающий — анкеты;
         если роль смотрящего неизвестна — показываем всех)
      4. Не сам пользователь и не показанные ранее
      5. Кандидат активен

    Возвращает None, если смотрящего нет или подходящих кандидатов не осталось.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            WITH me AS (
                SELECT telegram_id, city, preferred_gender,
                       CASE role
                            WHEN 'seeker'   THEN 'provider'
                            WHEN 'provider' THEN 'seeker'
                            ELSE NULL
                       END AS opposite
                FROM users WHERE telegram_id = $1
            )
            SELECT u.* FROM users u CROSS JOIN me
            WHERE u.telegram_id <> me.telegram_id
              AND u.is_active = TRUE
              AND u.city = me.city
              AND (me.preferred_gender = 'any' OR u.gender = me.preferred_gender)
              -- противоположная роль (если у смотрящего роль задана)
              AND (me.opposite IS NULL OR u.role = me.opposite)
              AND NOT EXISTS (
                    SELECT 1 FROM views v
                    WHERE v.viewer_id = me.telegram_id AND v.viewed_id = u.telegram_id
              )
            -- Премиум-анкеты показываем первыми
            ORDER BY (u.premium_until IS NOT NULL AND u.premium_until > now()) DESC,
                     u.created_at DESC
            LIMIT 1
            """,
            viewer_id,
        )


async def add_view(viewer_id: int, viewed_id: int) -> None:
    """Отметить кандидата как просмотренного."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO views (viewer_id, viewed_id)
            VALUES ($1, $2)
            ON CONFLICT (viewer_id, viewed_id) DO NOTHING
            """,
            viewer_id, viewed_id,
        )


async def add_like(from_id: int, to_id: int, is_super: bool = False) -> None:
    """Сохранить лайк (или супер-лайк)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO likes (from_id, to_id, is_super)
            VALUES ($1, $2, $3)
            ON CONFLICT (from_id, to_id) DO UPDATE SET is_super = EXCLUDED.is_super
            """,
            from_id, to_id, is_super,
        )


async def has_like(from_id: int, to_id: int) -> bool:
    """Проверить, лайкнул ли from_id пользователя to_id (для взаимного мэтча)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM likes WHERE from_id = $1 AND to_id = $2",
            from_id, to_id,
        )
        return row is not None
