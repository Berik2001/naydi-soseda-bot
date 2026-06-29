# -*- coding: utf-8 -*-
"""
Все inline-клавиатуры бота.

Соглашение по callback_data: "<префикс>:<значение>".
Например: "gender:female", "city:Алматы", "like:123456".
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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


def preferred_gender_kb() -> InlineKeyboardMarkup:
    """Шаг 3 — предпочтение по полу сожителя."""
    return _kb_from_dict("pref", texts.PREFERRED_GENDER, width=1)


def city_kb() -> InlineKeyboardMarkup:
    """Шаг 4 — город."""
    builder = InlineKeyboardBuilder()
    for city in texts.CITIES:
        builder.button(text=city, callback_data=f"city:{city}")
    builder.button(text="Другой город ✍️", callback_data="city:other")
    builder.adjust(2)
    return builder.as_markup()


def district_kb(city: str) -> InlineKeyboardMarkup:
    """Шаг 5 — район (зависит от города)."""
    builder = InlineKeyboardBuilder()
    for district in texts.DISTRICTS.get(city, []):
        builder.button(text=district, callback_data=f"dist:{district}")
    builder.button(text="Другой ✍️", callback_data="dist:other")
    builder.adjust(2)
    return builder.as_markup()


def move_in_kb() -> InlineKeyboardMarkup:
    """Шаг 7 — когда нужно."""
    return _kb_from_dict("move", texts.MOVE_IN, width=1)


def smoking_kb() -> InlineKeyboardMarkup:
    """Шаг 8 — курение."""
    return _kb_from_dict("smoke", texts.SMOKING, width=3)


def pets_kb() -> InlineKeyboardMarkup:
    """Шаг 9 — животные."""
    return _kb_from_dict("pets", texts.PETS, width=1)


def occupation_kb() -> InlineKeyboardMarkup:
    """Шаг 11 — занятость."""
    return _kb_from_dict("occ", texts.OCCUPATION, width=1)


def skip_photo_kb() -> InlineKeyboardMarkup:
    """Шаг 12 — кнопка «Пропустить» для фото."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip:photo")
    return builder.as_markup()


def skip_about_kb() -> InlineKeyboardMarkup:
    """Шаг 13 — кнопка «Пропустить» для «о себе»."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip:about")
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    """Шаг 14 — сохранить / заполнить заново."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сохранить анкету", callback_data="confirm:save")
    builder.button(text="✏️ Заполнить заново", callback_data="confirm:restart")
    builder.adjust(1)
    return builder.as_markup()


# ====================== МЭТЧИНГ ======================

def match_kb(candidate_id: int) -> InlineKeyboardMarkup:
    """Кнопки под карточкой кандидата."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Интересно", callback_data=f"like:{candidate_id}")
    builder.button(text="👎 Пропустить", callback_data=f"pass:{candidate_id}")
    builder.button(text="⭐ Супер-лайк", callback_data=f"super:{candidate_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


# ====================== МЕНЮ «МОЯ АНКЕТА» (/profile) ======================

def profile_menu_kb() -> InlineKeyboardMarkup:
    """Меню действий с анкетой."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👀 Смотреть анкету", callback_data="profile:view")
    builder.button(text="🔄 Заполнить заново", callback_data="profile:restart")
    builder.button(text="📸 Изменить фото", callback_data="profile:photo")
    builder.button(text="💰 Изменить цену", callback_data="profile:budget")
    builder.button(text="📍 Изменить город/район", callback_data="profile:location")
    builder.button(text="⭐ Активировать премиум", callback_data="profile:premium")
    builder.adjust(1)
    return builder.as_markup()


def profile_city_kb() -> InlineKeyboardMarkup:
    """Выбор города при редактировании через меню анкеты."""
    builder = InlineKeyboardBuilder()
    for city in texts.CITIES:
        builder.button(text=city, callback_data=f"pcity:{city}")
    builder.button(text="Другой город ✍️", callback_data="pcity:other")
    builder.adjust(2)
    return builder.as_markup()


def profile_district_kb(city: str) -> InlineKeyboardMarkup:
    """Выбор района при редактировании через меню анкеты (зависит от города)."""
    builder = InlineKeyboardBuilder()
    for district in texts.DISTRICTS.get(city, []):
        builder.button(text=district, callback_data=f"pdist:{district}")
    builder.button(text="Другой ✍️", callback_data="pdist:other")
    builder.adjust(2)
    return builder.as_markup()


# ====================== РЕДАКТИРОВАНИЕ ======================

# Какие поля можно редактировать и как (text — ввод текста, остальное — клавиатура)
EDIT_FIELDS = {
    "gender": "Пол",
    "goal": "Цель",
    "preferred_gender": "С кем жить",
    "city": "Город",
    "district": "Район",
    "budget": "Бюджет",
    "move_in": "Когда нужно",
    "smoking": "Курение",
    "pets": "Животные",
    "occupation": "Занятость",
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
