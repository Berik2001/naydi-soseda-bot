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
async def cmd_profile(message: Message, state: FSMContext) -> None:
    """Показать меню действий с анкетой."""
    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return
    await state.clear()
    await message.answer(texts.PROFILE_MENU_TITLE, reply_markup=inline.profile_menu_kb())


async def _send_profile_card(message: Message, user) -> None:
    """Отправить карточку анкеты (с фото, если есть)."""
    card = texts.profile_card(user)
    if user["photo_file_id"]:
        await message.answer_photo(photo=user["photo_file_id"], caption=card)
    else:
        await message.answer(card)


# ---------- Пункты меню «Моя анкета» ----------

@router.callback_query(F.data == "profile:view")
async def profile_view(call: CallbackQuery) -> None:
    """👀 Смотреть анкету."""
    user = await get_user(call.from_user.id)
    if user is None:
        await call.message.answer(texts.NO_PROFILE)
    else:
        await _send_profile_card(call.message, user)
    await call.answer()


@router.callback_query(F.data == "profile:restart")
async def profile_restart(call: CallbackQuery, state: FSMContext) -> None:
    """🔄 Заполнить анкету заново."""
    await start_registration(call.message, state, call.from_user)
    await call.answer()


@router.callback_query(F.data == "profile:budget")
async def profile_budget(call: CallbackQuery, state: FSMContext) -> None:
    """💰 Изменить цену — переиспользуем общий поток текстового редактирования."""
    await state.set_state(Edit.waiting_value)
    await state.update_data(edit_field="budget")
    await call.message.answer(texts.ASK_BUDGET)
    await call.answer()


@router.callback_query(F.data == "profile:premium")
async def profile_premium(call: CallbackQuery) -> None:
    """⭐ Премиум (заглушка — платежи ещё не подключены)."""
    await call.message.answer(texts.PREMIUM_INFO)
    await call.answer()


# ---------- Изменение фото ----------

@router.callback_query(F.data == "profile:photo")
async def profile_photo(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Edit.waiting_photo)
    await call.message.answer(texts.ASK_NEW_PHOTO)
    await call.answer()


@router.message(Edit.waiting_photo, F.photo)
async def profile_photo_set(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await update_field(message.from_user.id, "photo_file_id", file_id)
    await state.clear()
    await message.answer(texts.PHOTO_UPDATED)


@router.message(Edit.waiting_photo)
async def profile_photo_wrong(message: Message) -> None:
    await message.answer(texts.SEND_PHOTO_PLEASE)


# ---------- Изменение города / района ----------

@router.callback_query(F.data == "profile:location")
async def profile_location(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer(texts.ASK_CITY, reply_markup=inline.profile_city_kb())
    await call.answer()


async def _ask_profile_district(call: CallbackQuery, state: FSMContext, city: str) -> None:
    """Спросить район: кнопками для Алматы/Астаны, текстом — для остальных."""
    if city in texts.DISTRICTS:
        await state.set_state(None)  # район выберется кнопкой (pdist), отдельное состояние не нужно
        await call.message.edit_text(
            texts.ASK_DISTRICT, reply_markup=inline.profile_district_kb(city)
        )
    else:
        await state.set_state(Edit.waiting_loc_district)
        await call.message.edit_text(texts.ASK_DISTRICT_CUSTOM)


@router.callback_query(F.data.startswith("pcity:"))
async def profile_city_set(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    if value == "other":
        await state.set_state(Edit.waiting_loc_city)
        await call.message.edit_text(texts.ASK_CITY_CUSTOM)
        await call.answer()
        return
    await update_field(call.from_user.id, "city", value)
    await _ask_profile_district(call, state, value)
    await call.answer()


@router.message(Edit.waiting_loc_city, F.text)
async def profile_city_text(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    await update_field(message.from_user.id, "city", city)
    # Для произвольного города район вводится текстом
    await state.set_state(Edit.waiting_loc_district)
    await message.answer(texts.ASK_DISTRICT_CUSTOM)


@router.callback_query(F.data.startswith("pdist:"))
async def profile_district_set(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    if value == "other":
        await state.set_state(Edit.waiting_loc_district)
        await call.message.edit_text(texts.ASK_DISTRICT_CUSTOM)
        await call.answer()
        return
    await update_field(call.from_user.id, "district", value)
    await state.clear()
    await call.message.edit_text(texts.PROFILE_UPDATED)
    await call.answer()


@router.message(Edit.waiting_loc_district, F.text)
async def profile_district_text(message: Message, state: FSMContext) -> None:
    await update_field(message.from_user.id, "district", message.text.strip())
    await state.clear()
    await message.answer(texts.PROFILE_UPDATED)


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
