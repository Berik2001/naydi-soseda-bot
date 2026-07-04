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


async def register_like(
    from_id: int, to_id: int, is_super: bool = False
) -> tuple[bool, bool]:
    """
    Отметить просмотр, поставить лайк и проверить встречный лайк — всё за ОДИН
    заход в пул (одно соединение вместо трёх acquire). Возвращает кортеж
    (is_new_like, reciprocal):

      is_new_like — лайк поставлен ВПЕРВЫЕ (а не повтор уже существующего).
        По нему хендлер решает, слать ли получателю уведомление «тебя лайкнули».
        Это защита от спама: подделанный/повторный коллбэк «like:<id>» больше не
        шлёт жертве новое уведомление на каждый клик — только один раз.

      reciprocal — получатель ранее уже лайкнул нас (значит, взаимный мэтч).

    Признак «впервые» берём из RETURNING (xmax = 0): при INSERT xmax=0, при
    срабатывании ON CONFLICT ... DO UPDATE строка обновляется и xmax<>0.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO views (viewer_id, viewed_id) VALUES ($1, $2) "
            "ON CONFLICT (viewer_id, viewed_id) DO NOTHING",
            from_id, to_id,
        )
        inserted = await conn.fetchval(
            "INSERT INTO likes (from_id, to_id, is_super) VALUES ($1, $2, $3) "
            "ON CONFLICT (from_id, to_id) DO UPDATE SET is_super = EXCLUDED.is_super "
            "RETURNING (xmax = 0)",
            from_id, to_id, is_super,
        )
        reciprocal = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM likes WHERE from_id = $1 AND to_id = $2)",
            to_id, from_id,
        )
        return bool(inserted), bool(reciprocal)


async def like_usage(from_id: int, hours: int = 24) -> tuple[bool, int]:
    """
    Вернуть (премиум?, сколько лайков поставлено за последние `hours` часов) —
    одним заходом в пул. Для дневного лимита лайков.

    Считаем строки likes (одна на каждого лайкнутого; повторный лайк не создаёт
    новую строку — лента исключает уже просмотренных). Фильтр по from_id покрыт
    UNIQUE(from_id, to_id).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              COALESCE(
                (SELECT premium_until IS NOT NULL AND premium_until > now()
                   FROM users WHERE telegram_id = $1),
                FALSE
              ) AS is_prem,
              (SELECT count(*) FROM likes
                 WHERE from_id = $1
                   AND created_at > now() - make_interval(hours => $2)) AS used
            """,
            from_id, hours,
        )
        return bool(row["is_prem"]), int(row["used"])


async def delete_old_views(days: int) -> int:
    """
    Удалить просмотры старше `days` дней. Возвращает число удалённых строк.

    Ограничивает рост таблицы views (растёт на каждый свайп). Повторный показ
    давно просмотренных анкет — ожидаемое поведение: ситуация людей со временем
    меняется. Лайки при этом НЕ трогаем, поэтому повторный лайк того же человека
    не пере-уведомляет (register_like вернёт is_new=False).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        status = await conn.execute(
            "DELETE FROM views WHERE created_at < now() - make_interval(days => $1)",
            days,
        )
    # asyncpg отдаёт тег команды вида "DELETE <n>"
    parts = status.split()
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0
