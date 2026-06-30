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
from handlers.render import send_media_card
from keyboards import inline
from states.form import Form
from validators import is_valid_about, parse_budget

# Максимум фото квартиры в объявлении
MAX_APARTMENT_PHOTOS = 10


def _is_provider(data: dict) -> bool:
    """Роль «сдаёт/имеет жильё»?"""
    return data.get("role") == "provider"

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
    await state.set_state(Form.name)
    await call.message.edit_text(texts.ASK_NAME)
    await call.answer()


# ====================== ШАГ 1.5 — ИМЯ ======================

@router.message(Form.name, F.text)
async def step_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) > 50:
        await message.answer(texts.NAME_TOO_LONG)
        return
    # Имя из анкеты используем как full_name (приоритетнее имени из Telegram)
    await state.update_data(full_name=name)
    await state.set_state(Form.goal)
    await message.answer(texts.ASK_GOAL, reply_markup=inline.goal_kb())


@router.message(Form.name)
async def step_name_wrong(message: Message) -> None:
    await message.answer(texts.SEND_TEXT)


# ====================== ШАГ 2 — ЦЕЛЬ ======================

@router.callback_query(Form.goal, F.data.startswith("goal:"))
async def step_goal(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    # Сохраняем цель текстом и роль (seeker / provider)
    await state.update_data(goal=texts.GOAL[key], role=texts.GOAL_ROLE[key])
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
    """Шаг 5 — район всегда вводится текстом (пользователь пишет сам)."""
    await state.set_state(Form.district_custom)
    if edit:
        await message.edit_text(texts.ASK_DISTRICT_CUSTOM)
    else:
        await message.answer(texts.ASK_DISTRICT_CUSTOM)


# ====================== ШАГ 5 — РАЙОН (текст) ======================

@router.message(Form.district_custom, F.text)
async def step_district_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(district=message.text.strip())
    await _ask_budget_or_price(message, state, edit=False)


async def _ask_budget_or_price(message: Message, state: FSMContext, edit: bool) -> None:
    """Шаг 6 — спросить бюджет (ищу) или цену аренды (сдаю)."""
    data = await state.get_data()
    prompt = texts.ASK_PRICE if _is_provider(data) else texts.ASK_BUDGET
    await state.set_state(Form.budget)
    if edit:
        await message.edit_text(prompt)
    else:
        await message.answer(prompt)


# ====================== ШАГ 6 — БЮДЖЕТ / ЦЕНА ======================

@router.message(Form.budget, F.text)
async def step_budget(message: Message, state: FSMContext) -> None:
    # Разбор и валидация вынесены в validators.parse_budget (покрыто тестами)
    amount = parse_budget(message.text)
    if amount is None:
        await message.answer(texts.ASK_BUDGET_RETRY)
        return

    await state.update_data(budget=amount)
    data = await state.get_data()
    if _is_provider(data):
        # Сдаю/есть жильё -> загрузка фото квартиры
        await state.update_data(apartment_photos=[])
        await state.set_state(Form.apartment_photos)
        await message.answer(
            texts.ASK_APARTMENT_PHOTOS, reply_markup=inline.apartment_photos_done_kb()
        )
    else:
        await state.set_state(Form.move_in)
        await message.answer(texts.ASK_MOVE_IN, reply_markup=inline.move_in_kb())


# ====================== ОБЪЯВЛЕНИЕ: ФОТО КВАРТИРЫ (сдаю) ======================

@router.message(Form.apartment_photos, F.photo)
async def step_apartment_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = list(data.get("apartment_photos") or [])
    if len(photos) >= MAX_APARTMENT_PHOTOS:
        await message.answer(
            texts.APARTMENT_PHOTOS_MAX, reply_markup=inline.apartment_photos_done_kb()
        )
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(apartment_photos=photos)
    await message.answer(
        texts.apartment_photo_added(len(photos)),
        reply_markup=inline.apartment_photos_done_kb(),
    )


@router.callback_query(Form.apartment_photos, F.data == "aptphoto:done")
async def step_apartment_photos_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not (data.get("apartment_photos") or []):
        await call.answer(texts.APARTMENT_PHOTOS_NEED_ONE, show_alert=True)
        return
    await state.set_state(Form.listing_about)
    await call.message.answer(texts.ASK_LISTING_DESC)
    await call.answer()


@router.message(Form.apartment_photos)
async def step_apartment_photos_wrong(message: Message) -> None:
    await message.answer(texts.ASK_APARTMENT_PHOTOS,
                         reply_markup=inline.apartment_photos_done_kb())


# ====================== ОБЪЯВЛЕНИЕ: ОПИСАНИЕ (сдаю, обязательно) ======================

@router.message(Form.listing_about, F.text)
async def step_listing_about(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer(texts.ABOUT_EMPTY)
        return
    if not is_valid_about(text):
        await message.answer(texts.ABOUT_TOO_LONG)
        return
    await state.update_data(about=text)
    await _show_card_preview(message, state)


@router.message(Form.listing_about)
async def step_listing_about_wrong(message: Message) -> None:
    await message.answer(texts.SEND_TEXT)


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
    await state.set_state(Form.occupation)
    await call.message.edit_text(texts.ASK_OCCUPATION, reply_markup=inline.occupation_kb())
    await call.answer()


# ====================== ШАГ 10 — ЗАНЯТОСТЬ ======================

@router.callback_query(Form.occupation, F.data.startswith("occ:"))
async def step_occupation(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(occupation=texts.OCCUPATION[key])
    await state.update_data(profile_media=[], profile_media_type=None)
    await state.set_state(Form.photo)
    await call.message.edit_text(texts.ASK_PHOTO, reply_markup=inline.media_done_kb())
    await call.answer()


# ====================== ШАГ 11 — ФОТО / ВИДЕО (обязательно) ======================

@router.message(Form.photo, F.photo)
async def step_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    media = list(data.get("profile_media") or [])
    mtype = data.get("profile_media_type")
    if mtype == "video":
        await message.answer(texts.MEDIA_PHOTO_AFTER_VIDEO, reply_markup=inline.media_done_kb())
        return
    if len(media) >= 2:
        await message.answer(texts.PHOTO_MAX_TWO, reply_markup=inline.media_done_kb())
        return
    media.append(message.photo[-1].file_id)
    await state.update_data(profile_media=media, profile_media_type="photo")
    await message.answer(texts.photo_added(len(media)), reply_markup=inline.media_done_kb())


@router.message(Form.photo, F.video)
async def step_video(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("profile_media") and data.get("profile_media_type") == "photo":
        await message.answer(texts.MEDIA_VIDEO_AFTER_PHOTO, reply_markup=inline.media_done_kb())
        return
    await state.update_data(profile_media=[message.video.file_id], profile_media_type="video")
    await message.answer(texts.MEDIA_VIDEO_ADDED, reply_markup=inline.media_done_kb())


@router.callback_query(Form.photo, F.data == "media:done")
async def step_photo_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not (data.get("profile_media") or []):
        await call.answer(texts.PHOTO_NEED_ONE, show_alert=True)
        return
    await state.set_state(Form.about)
    await call.message.answer(texts.ASK_ABOUT)
    await call.answer()


@router.message(Form.photo)
async def step_photo_wrong(message: Message) -> None:
    await message.answer(texts.PHOTO_NEED_ONE, reply_markup=inline.media_done_kb())


# ====================== ШАГ 12 — О СЕБЕ (обязательно) ======================

@router.message(Form.about, F.text)
async def step_about(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer(texts.ABOUT_EMPTY)
        return
    if not is_valid_about(text):
        await message.answer(texts.ABOUT_TOO_LONG)
        return
    await state.update_data(about=text)
    await _show_card_preview(message, state)


@router.message(Form.about)
async def step_about_wrong(message: Message) -> None:
    await message.answer(texts.SEND_TEXT)


# ====================== ПОКАЗ КАРТОЧКИ/ОБЪЯВЛЕНИЯ ======================

async def _show_card_preview(message: Message, state: FSMContext) -> None:
    """Собрать данные и показать карточку (анкету или объявление) с кнопками."""
    data = await state.get_data()
    await state.set_state(Form.confirm)
    await message.answer(texts.PREVIEW_INTRO)

    card = texts.listing_card(data) if _is_provider(data) else texts.profile_card(data)
    await send_media_card(message, data, card, reply_markup=inline.confirm_kb())


@router.callback_query(Form.confirm, F.data == "confirm:save")
async def confirm_save(call: CallbackQuery, state: FSMContext) -> None:
    """Сохранить анкету в БД."""
    data = await state.get_data()
    # Дополняем данными из Telegram-профиля.
    # full_name НЕ трогаем — там имя, которое пользователь ввёл сам.
    data["telegram_id"] = call.from_user.id
    data["username"] = call.from_user.username
    data.setdefault("full_name", call.from_user.full_name)

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
@router.message(Form.move_in)
@router.message(Form.smoking)
@router.message(Form.pets)
@router.message(Form.occupation)
async def wrong_input_button(message: Message) -> None:
    await message.answer(texts.PRESS_BUTTON)
