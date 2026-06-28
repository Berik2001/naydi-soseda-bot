# -*- coding: utf-8 -*-
"""
Слой работы с PostgreSQL через asyncpg.

Используется один пул соединений на всё приложение.
Пул создаётся в bot.py при старте и закрывается при остановке.
"""

from __future__ import annotations  # поддержка синтаксиса "X | None" на Python 3.9

import asyncpg

from database.models import ALL_TABLES

# Глобальный пул соединений
_pool: asyncpg.Pool | None = None


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Создать пул соединений и подготовить таблицы."""
    global _pool
    _pool = await asyncpg.create_pool(dsn=dsn)
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
    """Создать все таблицы, если их ещё нет."""
    pool = get_pool()
    async with pool.acquire() as conn:
        for query in ALL_TABLES:
            await conn.execute(query)


# ====================== РАБОТА С АНКЕТАМИ ======================

async def get_user(telegram_id: int) -> asyncpg.Record | None:
    """Получить анкету по telegram_id."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1", telegram_id
        )


async def upsert_user(data: dict) -> None:
    """
    Создать или обновить анкету пользователя.
    data — словарь со всеми полями анкеты.
    При повторной регистрации старая анкета перезаписывается.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (
                telegram_id, username, full_name, gender, goal,
                preferred_gender, city, district, budget, move_in,
                smoking, pets, schedule, occupation, photo_file_id,
                about, is_active
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15,
                $16, TRUE
            )
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                gender = EXCLUDED.gender,
                goal = EXCLUDED.goal,
                preferred_gender = EXCLUDED.preferred_gender,
                city = EXCLUDED.city,
                district = EXCLUDED.district,
                budget = EXCLUDED.budget,
                move_in = EXCLUDED.move_in,
                smoking = EXCLUDED.smoking,
                pets = EXCLUDED.pets,
                schedule = EXCLUDED.schedule,
                occupation = EXCLUDED.occupation,
                photo_file_id = EXCLUDED.photo_file_id,
                about = EXCLUDED.about,
                is_active = TRUE
            """,
            data["telegram_id"], data.get("username"), data.get("full_name"),
            data.get("gender"), data.get("goal"), data.get("preferred_gender"),
            data.get("city"), data.get("district"), data.get("budget"),
            data.get("move_in"), data.get("smoking"), data.get("pets"),
            data.get("schedule"), data.get("occupation"),
            data.get("photo_file_id"), data.get("about"),
        )


async def update_field(telegram_id: int, field: str, value) -> None:
    """
    Обновить одно поле анкеты.
    field берётся только из белого списка — защита от SQL-инъекций.
    """
    allowed = {
        "gender", "goal", "preferred_gender", "city", "district",
        "budget", "move_in", "smoking", "pets", "schedule",
        "occupation", "photo_file_id", "about",
    }
    if field not in allowed:
        raise ValueError(f"Недопустимое поле: {field}")
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users SET {field} = $1 WHERE telegram_id = $2",
            value, telegram_id,
        )


async def set_active(telegram_id: int, active: bool) -> None:
    """Поставить анкету на паузу / снять с паузы."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_active = $1 WHERE telegram_id = $2",
            active, telegram_id,
        )


# ====================== МЭТЧИНГ ======================

async def get_next_candidate(viewer: asyncpg.Record) -> asyncpg.Record | None:
    """
    Найти следующего подходящего кандидата для viewer.

    Фильтры:
      1. Тот же город
      2. Пол кандидата совпадает с preferred_gender смотрящего
      3. Разница в бюджете не более 30%
      4. Не сам пользователь
      5. Не показывать уже просмотренных
      6. Кандидат активен
    """
    pool = get_pool()
    budget = viewer["budget"] or 0
    budget_min = int(budget * 0.7)
    budget_max = int(budget * 1.3)
    pref = viewer["preferred_gender"]

    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM users u
            WHERE u.telegram_id != $1
              AND u.is_active = TRUE
              AND u.city = $2
              AND ($3 = 'any' OR u.gender = $3)
              AND u.budget BETWEEN $4 AND $5
              AND NOT EXISTS (
                    SELECT 1 FROM views v
                    WHERE v.viewer_id = $1 AND v.viewed_id = u.telegram_id
              )
            ORDER BY u.created_at DESC
            LIMIT 1
            """,
            viewer["telegram_id"], viewer["city"], pref, budget_min, budget_max,
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
