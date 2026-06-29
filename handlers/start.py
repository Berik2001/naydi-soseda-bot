# -*- coding: utf-8 -*-
"""
Команды: /start, /help, /profile, /edit, /pause, /resume.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from database.db import get_user, set_active, update_field
from handlers.registration import start_registration
from keyboards import inline
from states.form import Edit
from validators import is_valid_about, parse_budget

router = Router()

# Поля, которые редактируются текстом (остальные — выбором кнопок)
_TEXT_FIELDS = {"city", "district", "budget", "about"}

# Поля, значение которых хранится КЛЮЧОМ (gender, preferred_gender)
_KEY_FIELDS = {"gender", "preferred_gender"}

# Какой словарь использовать для клавиатуры выбора при редактировании
_CHOICE_OPTIONS = {
    "gender": texts.GENDER,
    "preferred_gender": texts.PREFERRED_GENDER,
    "goal": texts.GOAL,
    "move_in": texts.MOVE_IN,
    "smoking": texts.SMOKING,
    "pets": texts.PETS,
    "occupation": texts.OCCUPATION,
}


# ====================== /start ======================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Начало работы — запускаем анкету."""
    await start_registration(message, state, message.from_user)


# ====================== /help ======================

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


# ====================== /profile ======================

@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Показать свою анкету."""
    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return

    card = texts.profile_card(user)
    if user["photo_file_id"]:
        await message.answer_photo(photo=user["photo_file_id"], caption=card)
    else:
        await message.answer(card)


# ====================== /pause и /resume ======================

@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return
    await set_active(message.from_user.id, False)
    await message.answer(texts.PAUSED)


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return
    await set_active(message.from_user.id, True)
    await message.answer(texts.RESUMED)


# ====================== /edit ======================

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext) -> None:
    """Показать список полей для редактирования."""
    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return
    await state.clear()
    await message.answer("✏️ Что хочешь изменить?", reply_markup=inline.edit_fields_kb())


@router.callback_query(F.data.startswith("edit:"))
async def edit_field_chosen(call: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал поле для редактирования."""
    field = call.data.split(":", 1)[1]

    if field in _TEXT_FIELDS:
        # Поле редактируется текстом — ждём ввод
        await state.set_state(Edit.waiting_value)
        await state.update_data(edit_field=field)
        prompt = {
            "city": texts.ASK_CITY_CUSTOM,
            "district": texts.ASK_DISTRICT_CUSTOM,
            "budget": texts.ASK_BUDGET,
            "about": texts.ASK_ABOUT,
        }[field]
        await call.message.edit_text(prompt)
    else:
        # Поле-выбор — показываем клавиатуру вариантов
        options = _CHOICE_OPTIONS[field]
        await call.message.edit_text(
            "Выбери новое значение:",
            reply_markup=inline.edit_choice_kb(field, options),
        )
    await call.answer()


@router.callback_query(F.data.startswith("setedit:"))
async def edit_choice_set(call: CallbackQuery) -> None:
    """Сохранить новое значение поля-выбора."""
    _, field, key = call.data.split(":", 2)

    if field in _KEY_FIELDS:
        value = key  # gender / preferred_gender хранятся ключом
    else:
        value = _CHOICE_OPTIONS[field][key]  # остальные — текстом

    await update_field(call.from_user.id, field, value)
    await call.message.edit_text("✅ Изменено!")
    await call.answer("Готово")


@router.message(Edit.waiting_value, F.text)
async def edit_text_set(message: Message, state: FSMContext) -> None:
    """Сохранить новое текстовое значение."""
    data = await state.get_data()
    field = data.get("edit_field")
    text = message.text.strip()

    # Валидация по полю (та же логика, что и в регистрации)
    if field == "budget":
        value = parse_budget(text)
        if value is None:
            await message.answer(texts.ASK_BUDGET_RETRY)
            return
    elif field == "about":
        if not is_valid_about(text):
            await message.answer(texts.ABOUT_TOO_LONG)
            return
        value = text
    else:  # city, district
        value = text

    await update_field(message.from_user.id, field, value)
    await state.clear()
    await message.answer("✅ Изменено!")
