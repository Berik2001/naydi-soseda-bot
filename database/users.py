# -*- coding: utf-8 -*-
"""Репозиторий анкет пользователей: чтение, upsert, точечное обновление, пауза."""

from __future__ import annotations

import asyncpg

from database.pool import get_pool


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
                smoking, pets, occupation, photo_file_id,
                about, role, apartment_photos,
                profile_media, profile_media_type, is_active
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15,
                $16, $17, $18, $19, TRUE
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
                occupation = EXCLUDED.occupation,
                photo_file_id = EXCLUDED.photo_file_id,
                about = EXCLUDED.about,
                role = EXCLUDED.role,
                apartment_photos = EXCLUDED.apartment_photos,
                profile_media = EXCLUDED.profile_media,
                profile_media_type = EXCLUDED.profile_media_type,
                is_active = TRUE
            """,
            data["telegram_id"], data.get("username"), data.get("full_name"),
            data.get("gender"), data.get("goal"), data.get("preferred_gender"),
            data.get("city"), data.get("district"), data.get("budget"),
            data.get("move_in"), data.get("smoking"), data.get("pets"),
            data.get("occupation"),
            data.get("photo_file_id"), data.get("about"),
            data.get("role"), data.get("apartment_photos"),
            data.get("profile_media"), data.get("profile_media_type"),
        )


async def update_field(telegram_id: int, field: str, value) -> None:
    """
    Обновить одно поле анкеты.
    field берётся только из белого списка — защита от SQL-инъекций.
    """
    allowed = {
        "gender", "goal", "preferred_gender", "city", "district",
        "budget", "move_in", "smoking", "pets",
        "occupation", "photo_file_id", "about",
        "role", "apartment_photos", "profile_media", "profile_media_type",
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
