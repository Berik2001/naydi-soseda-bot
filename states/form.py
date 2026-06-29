# -*- coding: utf-8 -*-
"""
Состояния FSM для регистрации и редактирования анкеты.
"""

from aiogram.fsm.state import State, StatesGroup


class Form(StatesGroup):
    """Шаги последовательной анкеты (регистрация)."""
    gender = State()            # Шаг 1 — пол
    goal = State()              # Шаг 2 — цель
    preferred_gender = State()  # Шаг 3 — предпочтение по полу сожителя
    city = State()              # Шаг 4 — город (кнопки)
    city_custom = State()       # Шаг 4 — ввод другого города текстом
    district = State()          # Шаг 5 — район (кнопки)
    district_custom = State()   # Шаг 5 — ввод другого района текстом
    budget = State()            # Шаг 6 — бюджет (текст)
    move_in = State()           # Шаг 7 — когда нужно
    smoking = State()           # Шаг 8 — курение
    pets = State()              # Шаг 9 — животные
    occupation = State()        # Шаг 10 — занятость
    photo = State()             # Шаг 12 — фото
    about = State()             # Шаг 13 — о себе
    confirm = State()           # Шаг 14 — подтверждение анкеты


class Edit(StatesGroup):
    """Состояния редактирования отдельных полей анкеты."""
    waiting_value = State()         # ждём новое текстовое значение (город/район/бюджет/о себе)
    waiting_photo = State()         # ждём новое фото профиля
    waiting_loc_city = State()      # ждём текстовый ввод города (через меню анкеты)
    waiting_loc_district = State()  # ждём текстовый ввод района (через меню анкеты)
