# -*- coding: utf-8 -*-
"""
Регистрация анкеты через FSM (14 шагов).

Логика хранения: gender и preferred_gender сохраняются ключами,
остальные поля — готовым русским текстом (из словарей texts).
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from database.db import upsert_user
from keyboards import inline
from states.form import Form

router = Router()


# ====================== ЗАПУСК РЕГИСТРАЦИИ ======================

async def start_registration(message: Message, state: FSMContext, user) -> None:
    """
    Начать анкету с первого шага. Вызывается из /start.
    user — объект Telegram-пользователя (message.from_user или call.from_user),
    его имя/username сохраняем сразу, чтобы показать в карточке-превью.
    """
    await state.clear()
    await state.update_data(
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )
    await state.set_state(Form.gender)
    await message.answer(texts.WELCOME, reply_markup=inline.gender_kb())


# ====================== ШАГ 1 — ПОЛ ======================

@router.callback_query(Form.gender, F.data.startswith("gender:"))
async def step_gender(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]  # female / male
    await state.update_data(gender=value)
    await state.set_state(Form.goal)
    await call.message.edit_text(texts.ASK_GOAL, reply_markup=inline.goal_kb())
    await call.answer()


# ====================== ШАГ 2 — ЦЕЛЬ ======================

@router.callback_query(Form.goal, F.data.startswith("goal:"))
async def step_goal(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(goal=texts.GOAL[key])  # сохраняем текстом
    await state.set_state(Form.preferred_gender)
    await call.message.edit_text(
        texts.ASK_PREFERRED_GENDER, reply_markup=inline.preferred_gender_kb()
    )
    await call.answer()


# ====================== ШАГ 3 — ПРЕДПОЧТЕНИЕ ПО ПОЛУ ======================

@router.callback_query(Form.preferred_gender, F.data.startswith("pref:"))
async def step_preferred_gender(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]  # female / male / any
    await state.update_data(preferred_gender=value)
    await state.set_state(Form.city)
    await call.message.edit_text(texts.ASK_CITY, reply_markup=inline.city_kb())
    await call.answer()


# ====================== ШАГ 4 — ГОРОД ======================

@router.callback_query(Form.city, F.data.startswith("city:"))
async def step_city(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    if value == "other":
        # Ждём текстовый ввод названия города
        await state.set_state(Form.city_custom)
        await call.message.edit_text(texts.ASK_CITY_CUSTOM)
        await call.answer()
        return

    await state.update_data(city=value)
    await _ask_district(call.message, state, value, edit=True)
    await call.answer()


@router.message(Form.city_custom, F.text)
async def step_city_custom(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    await state.update_data(city=city)
    await _ask_district(message, state, city, edit=False)


async def _ask_district(message: Message, state: FSMContext, city: str, edit: bool):
    """Шаг 5 — спросить район. Для Алматы/Астаны — кнопки, иначе текст."""
    if city in texts.DISTRICTS:
        await state.set_state(Form.district)
        kb = inline.district_kb(city)
        if edit:
            await message.edit_text(texts.ASK_DISTRICT, reply_markup=kb)
        else:
            await message.answer(texts.ASK_DISTRICT, reply_markup=kb)
    else:
        # Другой город — сразу текстовый ввод района
        await state.set_state(Form.district_custom)
        if edit:
            await message.edit_text(texts.ASK_DISTRICT_CUSTOM)
        else:
            await message.answer(texts.ASK_DISTRICT_CUSTOM)


# ====================== ШАГ 5 — РАЙОН ======================

@router.callback_query(Form.district, F.data.startswith("dist:"))
async def step_district(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    if value == "other":
        await state.set_state(Form.district_custom)
        await call.message.edit_text(texts.ASK_DISTRICT_CUSTOM)
        await call.answer()
        return

    await state.update_data(district=value)
    await state.set_state(Form.budget)
    await call.message.edit_text(texts.ASK_BUDGET)
    await call.answer()


@router.message(Form.district_custom, F.text)
async def step_district_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(district=message.text.strip())
    await state.set_state(Form.budget)
    await message.answer(texts.ASK_BUDGET)


# ====================== ШАГ 6 — БЮДЖЕТ ======================

@router.message(Form.budget, F.text)
async def step_budget(message: Message, state: FSMContext) -> None:
    # Убираем пробелы между цифрами
    raw = message.text.replace(" ", "")
    if not raw.isdigit():
        await message.answer(texts.ASK_BUDGET_RETRY)
        return

    amount = int(raw)
    if amount < 10000 or amount > 5000000:
        await message.answer(texts.ASK_BUDGET_RETRY)
        return

    await state.update_data(budget=amount)
    await state.set_state(Form.move_in)
    await message.answer(texts.ASK_MOVE_IN, reply_markup=inline.move_in_kb())


# ====================== ШАГ 7 — КОГДА НУЖНО ======================

@router.callback_query(Form.move_in, F.data.startswith("move:"))
async def step_move_in(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(move_in=texts.MOVE_IN[key])
    await state.set_state(Form.smoking)
    await call.message.edit_text(texts.ASK_SMOKING, reply_markup=inline.smoking_kb())
    await call.answer()


# ====================== ШАГ 8 — КУРЕНИЕ ======================

@router.callback_query(Form.smoking, F.data.startswith("smoke:"))
async def step_smoking(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(smoking=texts.SMOKING[key])
    await state.set_state(Form.pets)
    await call.message.edit_text(texts.ASK_PETS, reply_markup=inline.pets_kb())
    await call.answer()


# ====================== ШАГ 9 — ЖИВОТНЫЕ ======================

@router.callback_query(Form.pets, F.data.startswith("pets:"))
async def step_pets(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(pets=texts.PETS[key])
    await state.set_state(Form.schedule)
    await call.message.edit_text(texts.ASK_SCHEDULE, reply_markup=inline.schedule_kb())
    await call.answer()


# ====================== ШАГ 10 — РЕЖИМ ЖИЗНИ ======================

@router.callback_query(Form.schedule, F.data.startswith("sched:"))
async def step_schedule(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(schedule=texts.SCHEDULE[key])
    await state.set_state(Form.occupation)
    await call.message.edit_text(texts.ASK_OCCUPATION, reply_markup=inline.occupation_kb())
    await call.answer()


# ====================== ШАГ 11 — ЗАНЯТОСТЬ ======================

@router.callback_query(Form.occupation, F.data.startswith("occ:"))
async def step_occupation(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(occupation=texts.OCCUPATION[key])
    await state.set_state(Form.photo)
    await call.message.edit_text(texts.ASK_PHOTO, reply_markup=inline.skip_photo_kb())
    await call.answer()


# ====================== ШАГ 12 — ФОТО ======================

@router.message(Form.photo, F.photo)
async def step_photo(message: Message, state: FSMContext) -> None:
    # Берём самое большое по размеру фото
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await state.set_state(Form.about)
    await message.answer(texts.ASK_ABOUT, reply_markup=inline.skip_about_kb())


@router.callback_query(Form.photo, F.data == "skip:photo")
async def step_photo_skip(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(photo_file_id=None)
    await state.set_state(Form.about)
    await call.message.edit_text(texts.ASK_ABOUT, reply_markup=inline.skip_about_kb())
    await call.answer()


# ====================== ШАГ 13 — О СЕБЕ ======================

@router.message(Form.about, F.text)
async def step_about(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) > 200:
        await message.answer(texts.ABOUT_TOO_LONG)
        return
    await state.update_data(about=text)
    await _show_profile_card(message, state)


@router.callback_query(Form.about, F.data == "skip:about")
async def step_about_skip(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(about=None)
    await _show_profile_card(call.message, state)
    await call.answer()


# ====================== ШАГ 14 — ПОКАЗ АНКЕТЫ ======================

async def _show_profile_card(message: Message, state: FSMContext) -> None:
    """Собрать данные и показать карточку с кнопками сохранить/заново."""
    data = await state.get_data()
    # Карточка строится тем же помощником, что и /profile
    card = texts.profile_card(data)
    await state.set_state(Form.confirm)

    if data.get("photo_file_id"):
        await message.answer_photo(
            photo=data["photo_file_id"],
            caption=card,
            reply_markup=inline.confirm_kb(),
        )
    else:
        await message.answer(card, reply_markup=inline.confirm_kb())


@router.callback_query(Form.confirm, F.data == "confirm:save")
async def confirm_save(call: CallbackQuery, state: FSMContext) -> None:
    """Сохранить анкету в БД."""
    data = await state.get_data()
    # Дополняем данными из Telegram-профиля
    data["telegram_id"] = call.from_user.id
    data["username"] = call.from_user.username
    data["full_name"] = call.from_user.full_name

    await upsert_user(data)
    await state.clear()
    await call.message.answer(texts.PROFILE_SAVED)
    await call.answer("Сохранено ✅")


@router.callback_query(Form.confirm, F.data == "confirm:restart")
async def confirm_restart(call: CallbackQuery, state: FSMContext) -> None:
    """Заполнить анкету заново."""
    await call.message.answer(texts.PROFILE_RESTART)
    await start_registration(call.message, state, call.from_user)
    await call.answer()


# ====================== ОБРАБОТКА НЕВЕРНОГО ВВОДА ======================
# Если пользователь пишет текст там, где ждут кнопку — вежливо напоминаем.

@router.message(Form.gender)
@router.message(Form.goal)
@router.message(Form.preferred_gender)
@router.message(Form.city)
@router.message(Form.district)
@router.message(Form.move_in)
@router.message(Form.smoking)
@router.message(Form.pets)
@router.message(Form.schedule)
@router.message(Form.occupation)
async def wrong_input_button(message: Message) -> None:
    await message.answer(texts.PRESS_BUTTON)


@router.message(Form.photo)
async def wrong_input_photo(message: Message) -> None:
    await message.answer(texts.SEND_PHOTO_OR_SKIP)
