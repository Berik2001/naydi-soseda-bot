# -*- coding: utf-8 -*-
"""
View-модели карточек: превращают данные пользователя (dict или asyncpg.Record)
в готовый текст карточки/сообщения. Отделены от texts.py, где живёт «копирайт»
бота (статические строки и словари).
"""

from __future__ import annotations  # поддержка "X | None" на Python 3.9

import html

from texts import GENDER


def esc(value) -> str:
    """
    Экранировать пользовательский текст для parse_mode=HTML.

    Бот работает в HTML-режиме (bot.py). Любое сырое пользовательское поле
    (имя, город, район, «о себе») с символами <, >, & ломает разбор entities —
    Telegram отклоняет отправку, и карточка не показывается. Прогоняем такие
    поля через html.escape, поведение остаётся прежним для обычного текста.
    """
    return html.escape(str(value)) if value is not None else ""

def format_budget(amount: int) -> str:
    """100000 -> '100 000 тг'"""
    return f"{amount:,}".replace(",", " ") + " тг"


def user_link(name: str | None, telegram_id: int) -> str:
    """
    Кликабельное имя-ссылка на профиль пользователя.
    Работает даже без username через tg://user?id=<id>.
    Имя экранируется — в HTML-режиме спецсимволы не сломают разметку.
    """
    safe = html.escape(name or "Пользователь")
    return f'<a href="tg://user?id={telegram_id}">{safe}</a>'

def match_message(name: str | None, username: str | None, telegram_id: int) -> str:
    """Сообщение о взаимном мэтче. Имя — кликабельная ссылка на профиль."""
    link = user_link(name, telegram_id)
    if username:
        contact = f"👉 @{username}"
    else:
        contact = "👉 Нажми на имя выше, чтобы открыть профиль"
    return (
        "🎉 У вас мэтч!\n"
        f"{link} хочет с тобой пообщаться\n"
        f"{contact}"
    )

def liked_by_line(user: dict, is_super: bool) -> str:
    """Одна строка в списке «кто меня лайкнул»."""
    mark = "⭐" if is_super else "❤️"
    name = esc(user["full_name"] or "Без имени")
    contact = f"@{user['username']}" if user["username"] else "(без username)"
    return f"{mark} {name}, {esc(user['city'])} — {contact}"

def profile_card(user: dict) -> str:
    """
    Карточка анкеты. Сверху — цель пользователя. Показываются только заполненные поля.

    Доступ к полям через .get(): объект приходит и как dict (данные FSM при
    регистрации, где части ключей может не быть), и как asyncpg.Record (из БД).
    Значения в словарях (цель, режим заезда, занятость) уже содержат свой эмодзи,
    поэтому в карточке для них НЕ добавляем второй префикс — иначе дублируются смайлики.
    """
    name = esc(user.get("full_name") or "Без имени")
    gender = GENDER.get(user.get("gender"), "—")

    lines = []
    # Цель — заголовок карточки (значение уже с эмодзи 🔍/🏠)
    if user.get("goal"):
        lines += [esc(user.get("goal")), ""]

    lines.append(f"👤 {name}, {gender}")

    # Локация: город всегда, район — если указан
    if user.get("district"):
        lines.append(f"📍 {esc(user.get('city'))}, {esc(user.get('district'))}")
    elif user.get("city"):
        lines.append(f"📍 {esc(user.get('city'))}")

    if user.get("budget"):
        # Бюджет ищущего — это «до» (верхний предел)
        lines.append(f"💰 до {format_budget(user.get('budget'))}")
    if user.get("move_in"):
        lines.append(esc(user.get("move_in")))  # уже с эмодзи

    # Привычки в одну строку (значения уже с эмодзи, кроме курения).
    # Для старых анкет, где эти поля заполнены; новые анкеты их не содержат.
    habits = []
    if user.get("smoking"):
        habits.append(f"🚭 {esc(user.get('smoking'))}")
    if user.get("pets"):
        habits.append(esc(user.get("pets")))
    if habits:
        lines.append(" | ".join(habits))

    if user.get("occupation"):
        lines.append(esc(user.get("occupation")))  # уже с эмодзи

    # «О себе» показываем всегда (с прочерком, если пусто)
    lines.append(f"💬 «{esc(user.get('about')) or '—'}»")

    return "\n".join(lines)

def listing_card(user: dict, header: str | None = "🏠 Есть жильё — ищу соседа") -> str:
    """Карточка объявления (для роли provider — есть жильё, ищет соседа)."""
    name = esc(user.get("full_name") or "Без имени")
    gender = GENDER.get(user.get("gender"), "—")

    lines = []
    if header:
        lines += [header, ""]
    lines.append(f"👤 {name}, {gender}")
    if user.get("district"):
        lines.append(f"📍 {esc(user.get('city'))}, {esc(user.get('district'))}")
    elif user.get("city"):
        lines.append(f"📍 {esc(user.get('city'))}")
    if user.get("budget"):
        lines.append(f"💰 {format_budget(user.get('budget'))}/мес")
    lines.append(f"💬 «{esc(user.get('about')) or '—'}»")
    return "\n".join(lines)

def user_card(user: dict) -> str:
    """Единая точка: для provider — объявление, иначе — анкета."""
    if user.get("role") == "provider":
        return listing_card(user)
    return profile_card(user)
