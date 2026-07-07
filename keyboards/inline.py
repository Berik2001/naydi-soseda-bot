# -*- coding: utf-8 -*-
"""
Все inline-клавиатуры бота.

Соглашение по callback_data: "<префикс>:<значение>".
Например: "gender:female", "city:Алматы", "like:123456".
"""

from __future__ import annotations  # поддержка "X | None" на Python 3.9

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import texts


def _kb_from_dict(prefix: str, options: dict, width: int = 1) -> InlineKeyboardMarkup:
    """Построить клавиатуру из словаря {ключ: подпись}."""
    builder = InlineKeyboardBuilder()
    for key, label in options.items():
        builder.button(text=label, callback_data=f"{prefix}:{key}")
    builder.adjust(width)
    return builder.as_markup()


# ====================== РЕГИСТРАЦИЯ ======================

def gender_kb() -> InlineKeyboardMarkup:
    """Шаг 1 — пол."""
    return _kb_from_dict("gender", texts.GENDER, width=2)


def goal_kb() -> InlineKeyboardMarkup:
    """Шаг 2 — цель."""
    return _kb_from_dict("goal", texts.GOAL, width=1)


def city_kb() -> InlineKeyboardMarkup:
    """Шаг 3 — город."""
    builder = InlineKeyboardBuilder()
    for city in texts.CITIES:
        builder.button(text=city, callback_data=f"city:{city}")
    builder.button(text="Другой город ✍️", callback_data="city:other")
    builder.adjust(2)
    return builder.as_markup()


def photo_skip_kb(action: str) -> InlineKeyboardMarkup:
    """Кнопка «Пропустить» на шаге фото (фото необязательны). action — callback."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить ➡️", callback_data=action)
    return builder.as_markup()


# ====================== МЭТЧИНГ ======================

def match_kb(candidate_id: int) -> InlineKeyboardMarkup:
    """Кнопки под карточкой кандидата.

    Супер-лайк временно скрыт: кнопку убрали, но обработчик super: в
    handlers/matching.py оставлен — вернуть фичу можно одной строкой (добавить
    кнопку обратно и поправить adjust).
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Интересно", callback_data=f"like:{candidate_id}")
    builder.button(text="👎 Пропустить", callback_data=f"pass:{candidate_id}")
    builder.adjust(2)
    return builder.as_markup()


def incoming_like_kb(liker_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки под уведомлением «тебя лайкнули»:
    «перейти к переписке» = лайк в ответ (мэтч), «отказаться» = пропустить.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Перейти к переписке", callback_data=f"accept:{liker_id}")
    builder.button(text="👎 Отказаться", callback_data=f"decline:{liker_id}")
    builder.adjust(1)
    return builder.as_markup()


# ====================== МЕНЮ «МОЯ АНКЕТА» (/profile) ======================

def profile_menu_kb(role: str | None) -> InlineKeyboardMarkup:
    """Меню действий с анкетой. Первая кнопка и «фото» зависят от роли."""
    builder = InlineKeyboardBuilder()
    if role == "provider":
        builder.button(text="👀 Смотреть анкеты", callback_data="profile:feed")
        builder.button(text="🔄 Заполнить заново", callback_data="profile:restart")
        builder.button(text="📸 Изменить фото квартиры", callback_data="profile:apt_photos")
    else:
        builder.button(text="👀 Смотреть объявления", callback_data="profile:feed")
        builder.button(text="🔄 Заполнить заново", callback_data="profile:restart")
        builder.button(text="📸 Изменить фото", callback_data="profile:photo")
    builder.button(text="💰 Изменить цену", callback_data="profile:budget")
    builder.button(text="📍 Изменить город/район", callback_data="profile:location")
    # У сдающего это текст объявления, у ищущего — «о себе»
    about_label = "✍️ Изменить текст объявления" if role == "provider" else "✍️ Изменить о себе"
    builder.button(text=about_label, callback_data="profile:about")
    # Кнопка премиума временно скрыта (пока премиум бесплатный)
    builder.adjust(1)
    return builder.as_markup()


def photos_done_kb(action: str) -> InlineKeyboardMarkup:
    """
    Inline-кнопка «Готово ✅» под сообщением-приглашением загрузить фото.
    Показывается ОДИН раз (на приглашении), на каждое фото не дублируется.
    Inline-кнопка надёжнее reply-клавиатуры: она всегда видна в сообщении,
    тогда как нижняя клавиатура на части клиентов прячется за переключателем.
    `action` — callback_data завершения (например, "aptphoto:done").
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.PHOTOS_DONE_BTN, callback_data=action)
    return builder.as_markup()


def profile_city_kb() -> InlineKeyboardMarkup:
    """Выбор города при редактировании через меню анкеты."""
    builder = InlineKeyboardBuilder()
    for city in texts.CITIES:
        builder.button(text=city, callback_data=f"pcity:{city}")
    builder.button(text="Другой город ✍️", callback_data="pcity:other")
    builder.adjust(2)
    return builder.as_markup()


# ====================== ПРЕМИУМ ======================

def premium_buy_kb(stars: int) -> InlineKeyboardMarkup:
    """Кнопка покупки премиума за Stars."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⭐ Купить за {stars} Stars", callback_data="premium:buy")
    return builder.as_markup()


def premium_active_kb() -> InlineKeyboardMarkup:
    """Кнопки для активного премиума."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👀 Кто меня лайкнул", callback_data="premium:wholiked")
    return builder.as_markup()


# ====================== РЕДАКТИРОВАНИЕ ======================

# Какие поля можно редактировать и как (text — ввод текста, остальное — клавиатура)
EDIT_FIELDS = {
    "gender": "Пол",
    # «Цель» не редактируем точечно: она задаёт роль (ищу/сдаю) и набор полей.
    # Смена роли — только через «Заполнить заново».
    # «С кем жить» не редактируем: пол сожителя всегда равен собственному полу.
    "city": "Город",
    "district": "Район",
    "budget": "Бюджет",
    "about": "О себе",
}


def edit_fields_kb() -> InlineKeyboardMarkup:
    """Список полей для редактирования."""
    builder = InlineKeyboardBuilder()
    for field, label in EDIT_FIELDS.items():
        builder.button(text=label, callback_data=f"edit:{field}")
    builder.adjust(2)
    return builder.as_markup()


def edit_choice_kb(field: str, options: dict) -> InlineKeyboardMarkup:
    """Клавиатура выбора нового значения для поля-выбора."""
    builder = InlineKeyboardBuilder()
    for key, label in options.items():
        builder.button(text=label, callback_data=f"setedit:{field}:{key}")
    builder.adjust(2)
    return builder.as_markup()


# ====================== ОБРАТНАЯ СВЯЗЬ ======================

def feedback_cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены на шаге обратной связи (/feedback)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена ✖️", callback_data="feedback:cancel")
    return builder.as_markup()
