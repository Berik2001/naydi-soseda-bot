# -*- coding: utf-8 -*-
"""
Админ-панель: /admin (меню) и /stats (статистика бота).

Доступ ограничен фильтром IsAdmin на уровне роутера — все хендлеры внутри видны
только пользователям из config.get_admin_ids(). Для остальных команды «не
существуют» (апдейт проваливается дальше и просто игнорируется).

Роутер подключается в bot.py ПЕРВЫМ, чтобы админ-команды срабатывали даже во
время незавершённой регистрации (как и прочие команды). Хендлеры только читают —
FSM-состояние не трогаем, поэтому регистрация админа не сбивается.
"""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

import config
from database.stats import get_overview, top_cities

router = Router()


class IsAdmin(BaseFilter):
    """Пропускает только пользователей из списка админов (config.get_admin_ids)."""

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        return user is not None and user.id in config.get_admin_ids()


# Доступ ко всем message-хендлерам роутера — только админам.
router.message.filter(IsAdmin())


ADMIN_HELP = (
    "🛠 <b>Админ-панель</b>\n\n"
    "/stats — статистика бота\n"
    "/admin — это меню"
)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Меню админ-команд."""
    await message.answer(ADMIN_HELP)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Ключевые метрики бота."""
    overview = await get_overview()
    cities = await top_cities()
    await message.answer(_format_stats(overview, cities))


def _format_stats(o: dict, cities: list) -> str:
    """Собрать читаемое сообщение статистики (значения — из get_overview/top_cities)."""
    lines = [
        "📊 <b>Статистика бота</b>",
        "",
        f"👥 Всего анкет: <b>{o['total']}</b>",
        f"✅ Активных: <b>{o['active']}</b>",
        f"🔍 Ищут жильё: <b>{o['seekers']}</b>",
        f"🏠 Сдают жильё: <b>{o['providers']}</b>",
        f"⭐ Премиум: <b>{o['premium']}</b>",
        "",
        f"🆕 Новых за 24ч: <b>{o['new_24h']}</b>",
        f"🆕 Новых за 7 дней: <b>{o['new_7d']}</b>",
        "",
        f"❤️ Лайков: <b>{o['likes']}</b>",
        f"🎉 Мэтчей: <b>{o['matches']}</b>",
        f"👀 Просмотров: <b>{o['views']}</b>",
    ]
    if cities:
        lines.append("")
        lines.append("🏙 <b>Топ городов:</b>")
        for r in cities:
            lines.append(f"  • {html.escape(r['city'])} — {r['n']}")
    return "\n".join(lines)
