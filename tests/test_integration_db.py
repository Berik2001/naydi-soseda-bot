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

from database import matching, pool as db_pool, premium, users  # noqa: E402


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
