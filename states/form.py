# -*- coding: utf-8 -*-
"""
Состояния FSM для регистрации и редактирования анкеты.
"""

from aiogram.fsm.state import State, StatesGroup


class Form(StatesGroup):
    """Шаги последовательной анкеты (регистрация)."""
    gender = State()            # Шаг 1 — пол
    name = State()              # Шаг 2 — имя
    goal = State()              # Шаг 3 — цель
    city = State()              # Шаг 4 — город (кнопки)
    city_custom = State()       # Шаг 4 — ввод другого города текстом
    district_custom = State()   # Шаг 5 — район (ввод текстом)
    budget = State()            # Шаг 6 — бюджет (ищу) / цена аренды (сдаю)
    apartment_photos = State()  # сдаю: фото квартиры (до 10)
    listing_about = State()     # сдаю: описание объявления
    move_in = State()           # Шаг 7 — когда нужно
    occupation = State()        # Шаг 8 — занятость
    photo = State()             # Шаг 9 — фото
    about = State()             # Шаг 10 — о себе


class Edit(StatesGroup):
    """Состояния редактирования отдельных полей анкеты."""
    waiting_value = State()         # ждём новое текстовое значение (город/район/бюджет/о себе)
    waiting_photo = State()         # ждём новое фото профиля
    waiting_apartment_photos = State()  # пересбор фото квартиры (сдаю)
    waiting_loc_city = State()      # ждём текстовый ввод города (через меню анкеты)
    waiting_loc_district = State()  # ждём текстовый ввод района (через меню анкеты)
