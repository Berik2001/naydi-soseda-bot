# -*- coding: utf-8 -*-
"""
Интеграционные тесты слоя БД против реального PostgreSQL.

Покрывают бизнес-ядро, которое юнит-тесты не достают: правила подбора
кандидата (город/пол/роль/премиум/просмотренные) и взаимные лайки.

Запускаются только если задан TEST_DATABASE_URL (в CI — сервис postgres).
Локально: подними Postgres и укажи строку, напр.
    TEST_DATABASE_URL=postgresql://postgres@localhost:5439/postgres pytest -q
"""

import asyncio
import os

import pytest

pytest.importorskip("asyncpg")

DSN = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL не задан")

from database import matching, pool as db_pool, premium, stats, users  # noqa: E402


def run(scenario):
    """Выполнить сценарий с чистой БД в рамках одного event loop."""
    async def wrapper():
        await db_pool.create_pool(DSN)
        try:
            async with db_pool.get_pool().acquire() as conn:
                await conn.execute("TRUNCATE users, views, likes RESTART IDENTITY CASCADE")
            await scenario()
        finally:
            await db_pool.close_pool()
    asyncio.run(wrapper())


def _user(tid, gender="male", city="Алматы", role="seeker"):
    """Минимальная анкета для upsert (preferred_gender = собственному полу)."""
    return {
        "telegram_id": tid, "username": f"u{tid}", "full_name": f"User{tid}",
        "gender": gender, "preferred_gender": gender, "goal": "цель",
        "city": city, "district": "Центр", "budget": 100000,
        "about": "о себе", "role": role,
    }


# ---------------------- upsert / get / update ----------------------

def test_upsert_and_get_roundtrip():
    async def scenario():
        await users.upsert_user(_user(1))
        u = await users.get_user(1)
        assert u is not None
        assert u["full_name"] == "User1"
        assert u["city"] == "Алматы"
        assert u["is_active"] is True
    run(scenario)


def test_update_field_and_set_active():
    async def scenario():
        await users.upsert_user(_user(1))
        await users.update_field(1, "city", "Астана")
        await users.set_active(1, False)
        u = await users.get_user(1)
        assert u["city"] == "Астана"
        assert u["is_active"] is False
    run(scenario)


def test_upsert_is_idempotent_by_telegram_id():
    async def scenario():
        await users.upsert_user(_user(1, city="Алматы"))
        await users.upsert_user(_user(1, city="Шымкент"))  # тот же id → перезапись
        u = await users.get_user(1)
        assert u["city"] == "Шымкент"
        # одна запись, не две
        async with db_pool.get_pool().acquire() as conn:
            cnt = await conn.fetchval("SELECT count(*) FROM users")
        assert cnt == 1
    run(scenario)


# ---------------------- get_next_candidate: правила подбора ----------------------

def test_candidate_matches_city_gender_opposite_role():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))            # смотрящий
        await users.upsert_user(_user(2, role="provider"))          # ✅ подходит
        await users.upsert_user(_user(3, city="Астана", role="provider"))   # другой город
        await users.upsert_user(_user(4, gender="female", role="provider")) # другой пол
        await users.upsert_user(_user(5, role="seeker"))            # та же роль
        cand = await matching.get_next_candidate(1)
        assert cand is not None and cand["telegram_id"] == 2
    run(scenario)


def test_premium_candidate_ranked_first():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await users.upsert_user(_user(6, role="provider"))
        await premium.activate_premium(6, 30)                       # 6 — премиум
        cand = await matching.get_next_candidate(1)
        assert cand["telegram_id"] == 6                             # премиум первым
    run(scenario)


def test_viewed_and_inactive_excluded():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await users.upsert_user(_user(3, role="provider"))
        await matching.add_view(1, 2)                               # 2 просмотрен
        await users.set_active(3, False)                           # 3 на паузе
        cand = await matching.get_next_candidate(1)
        assert cand is None                                        # некого показать
    run(scenario)


# ---------------------- лайки / взаимность ----------------------

def test_add_like_and_reciprocity():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await matching.add_like(1, 2)
        assert await matching.has_like(1, 2) is True
        assert await matching.has_like(2, 1) is False              # встречного ещё нет
        await matching.add_like(2, 1)
        assert await matching.has_like(2, 1) is True               # теперь взаимно
    run(scenario)


def test_register_like_flags_new_and_reciprocal():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))

        # Первый лайк — новый, встречного ещё нет
        is_new, reciprocal = await matching.register_like(1, 2)
        assert is_new is True and reciprocal is False

        # Повторный тот же лайк (напр. подделанный коллбэк) — НЕ новый → не спамим уведомлением
        is_new, reciprocal = await matching.register_like(1, 2)
        assert is_new is False

        # Встречный лайк от 2 к 1 — теперь взаимно
        is_new, reciprocal = await matching.register_like(2, 1)
        assert is_new is True and reciprocal is True

        # Просмотр проставился как побочный эффект
        assert await matching.get_next_candidate(1) is None
    run(scenario)


def test_delete_old_views_removes_only_stale():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        async with db_pool.get_pool().acquire() as conn:
            # Старый просмотр (100 дней назад) и свежий (сейчас)
            await conn.execute(
                "INSERT INTO views (viewer_id, viewed_id, created_at) "
                "VALUES ($1, $2, now() - interval '100 days')", 1, 2)
            await conn.execute(
                "INSERT INTO views (viewer_id, viewed_id, created_at) "
                "VALUES ($1, $2, now())", 1, 3)

        deleted = await matching.delete_old_views(60)
        assert deleted == 1                                        # удалён только старый

        async with db_pool.get_pool().acquire() as conn:
            remaining = await conn.fetchval("SELECT count(*) FROM views")
        assert remaining == 1
    run(scenario)


def test_delete_old_views_none_stale_returns_zero():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await matching.add_view(1, 2)                              # свежий просмотр
        deleted = await matching.delete_old_views(60)
        assert deleted == 0                                        # чистить нечего
    run(scenario)


def test_like_usage_counts_and_premium_flag():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await users.upsert_user(_user(3, role="provider"))

        await matching.register_like(1, 2)
        await matching.register_like(1, 3)
        is_prem, used = await matching.like_usage(1)
        assert is_prem is False
        assert used == 2                                           # два свежих лайка

        await premium.activate_premium(1, 30)
        is_prem, _ = await matching.like_usage(1)
        assert is_prem is True                                     # премиум распознан
    run(scenario)


def test_like_usage_ignores_old_likes():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        async with db_pool.get_pool().acquire() as conn:
            await conn.execute(
                "INSERT INTO likes (from_id, to_id, created_at) "
                "VALUES ($1, $2, now() - interval '2 days')", 1, 2)
        _, used = await matching.like_usage(1)
        assert used == 0                                           # старые (>24ч) не в счёт
    run(scenario)


def test_stats_overview_and_matches():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await users.upsert_user(_user(3, role="provider", city="Астана"))
        await premium.activate_premium(3, 30)
        # взаимный лайк 1<->2 → один мэтч
        await matching.register_like(1, 2)
        await matching.register_like(2, 1)

        o = await stats.get_overview()
        assert o["total"] == 3
        assert o["seekers"] == 1
        assert o["providers"] == 2
        assert o["premium"] == 1
        assert o["likes"] == 2
        assert o["matches"] == 1                                   # пара учтена один раз

        cities = await stats.top_cities()
        by_city = {r["city"]: r["n"] for r in cities}
        assert by_city.get("Алматы") == 2                          # 1 и 2 в Алматы
        assert by_city.get("Астана") == 1
    run(scenario)


def test_delete_user_removes_profile_and_relations():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await matching.register_like(1, 2)                          # лайк + просмотр от 1
        await matching.register_like(2, 1)                          # встречный от 2

        assert await users.delete_user(1) is True
        assert await users.get_user(1) is None                     # анкета удалена

        async with db_pool.get_pool().acquire() as conn:
            likes = await conn.fetchval(
                "SELECT count(*) FROM likes WHERE from_id = 1 OR to_id = 1")
            views = await conn.fetchval(
                "SELECT count(*) FROM views WHERE viewer_id = 1 OR viewed_id = 1")
        assert likes == 0 and views == 0                           # связи вычищены

        assert await users.delete_user(1) is False                 # повторно — нечего
        assert await users.get_user(2) is not None                 # второй не задет
    run(scenario)


def test_who_liked_me_lists_active_likers():
    async def scenario():
        await users.upsert_user(_user(1, role="seeker"))
        await users.upsert_user(_user(2, role="provider"))
        await users.upsert_user(_user(3, role="provider"))
        await matching.add_like(2, 1)
        await matching.add_like(3, 1, is_super=True)
        await users.set_active(3, False)                           # неактивных не показываем
        rows = await premium.who_liked_me(1)
        ids = {r["telegram_id"] for r in rows}
        assert ids == {2}
    run(scenario)
