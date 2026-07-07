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
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import Message

import config
from database.stats import get_overview, top_cities
from database.users import delete_user, get_user

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
    "/delete &lt;id&gt; — удалить анкету по Telegram ID\n"
    "/admin — это меню\n\n"
    "💡 Ещё удалять объявления можно кнопкой «🗑 Удалить» прямо в ленте (/search)."
)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Меню админ-команд."""
    await message.answer(ADMIN_HELP)


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject) -> None:
    """Удалить анкету по Telegram ID: /delete 12345 (модерация)."""
    raw = (command.args or "").strip()
    if not raw:
        await message.answer("Формат: <code>/delete &lt;telegram_id&gt;</code>")
        return
    try:
        target = int(raw.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом. Пример: <code>/delete 12345</code>")
        return

    user = await get_user(target)
    if user is None:
        await message.answer(f"Анкета с ID <code>{target}</code> не найдена.")
        return

    await delete_user(target)
    name = html.escape(user["full_name"] or "без имени")
    city = html.escape(user["city"] or "—")
    await message.answer(f"🗑 Удалена анкета: <b>{name}</b> ({city}), ID <code>{target}</code>.")


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
