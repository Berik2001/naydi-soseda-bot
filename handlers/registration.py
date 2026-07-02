# -*- coding: utf-8 -*-
"""
Регистрация анкеты через FSM (14 шагов).

Логика хранения: gender и preferred_gender сохраняются ключами,
остальные поля — готовым русским текстом (из словарей texts).
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import cards
import texts
from config import MAX_APARTMENT_PHOTOS, MAX_PROFILE_PHOTOS
from database.users import upsert_user
from handlers.render import send_media_card
from keyboards import inline
from media_flow import (
    cancel_done_button,
    collect_album_photo,
    collect_profile_photo,
    collect_profile_video,
)
from states.form import Form
from validators import is_valid_about, parse_budget


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
    data = await state.get_data()
    # Сохраняем цель текстом и роль (seeker / provider).
    # «С кем жить» больше не спрашиваем: пол сожителя = собственному полу
    # (парень живёт с парнями, девушка — с девушками).
    await state.update_data(
        goal=texts.GOAL[key],
        role=texts.GOAL_ROLE[key],
        preferred_gender=data.get("gender"),
    )
    await state.set_state(Form.city)
    # Фиксируем выбор цели (убираем кнопки) и спрашиваем город ОТДЕЛЬНЫМ
    # сообщением, чтобы шаг с городом был виден и не перезаписывался районом.
    await call.message.edit_text(texts.GOAL[key])
    await call.message.answer(texts.ASK_CITY, reply_markup=inline.city_kb())
    await call.answer()


# ====================== ШАГ 3 — ГОРОД ======================

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
    # Фиксируем выбранный город (убираем кнопки) и спрашиваем район
    # ОТДЕЛЬНЫМ сообщением — чтобы город остался виден в переписке.
    await call.message.edit_text(f"📍 {value}")
    await _ask_district(call.message, state)
    await call.answer()


@router.message(Form.city_custom, F.text)
async def step_city_custom(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    await state.update_data(city=city)
    await _ask_district(message, state)


async def _ask_district(message: Message, state: FSMContext):
    """Шаг 5 — район всегда вводится текстом (пользователь пишет сам).
    Всегда отправляем новым сообщением, чтобы предыдущий шаг не перезаписывался."""
    data = await state.get_data()
    await state.set_state(Form.district_custom)
    await message.answer(texts.ask_district(data.get("role")))


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
        # Сдаю/есть жильё -> загрузка фото квартиры (необязательно, можно пропустить)
        await state.update_data(apartment_photos=[], done_msg_id=None)
        await state.set_state(Form.apartment_photos)
        await message.answer(
            texts.ASK_APARTMENT_PHOTOS, reply_markup=inline.photo_skip_kb("aptphoto:skip")
        )
    else:
        # Ищущий -> сразу к фото профиля (шаги «когда заехать» и «занятость»
        # убраны: это пользователь пишет свободно в «о себе»). Фото необязательно.
        await state.update_data(profile_media=[], profile_media_type=None, done_msg_id=None)
        await state.set_state(Form.photo)
        await message.answer(texts.ASK_PHOTO, reply_markup=inline.photo_skip_kb("photo:skip"))


# ====================== ОБЪЯВЛЕНИЕ: ФОТО КВАРТИРЫ (сдаю) ======================

@router.message(Form.apartment_photos, F.photo)
async def step_apartment_photo(message: Message, state: FSMContext) -> None:
    await collect_album_photo(
        message, state,
        list_key="apartment_photos", done_action="aptphoto:done",
        max_count=MAX_APARTMENT_PHOTOS,
    )


async def _go_to_listing_about(message: Message, state: FSMContext) -> None:
    """Перейти к описанию объявления (после фото квартиры — Готово или Пропустить)."""
    data = await state.get_data()
    await state.set_state(Form.listing_about)
    await message.answer(texts.ask_listing_desc(data.get("gender")))


@router.callback_query(Form.apartment_photos, F.data == "aptphoto:done")
async def step_apartment_photos_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not (data.get("apartment_photos") or []):
        await call.answer(texts.APARTMENT_PHOTOS_NEED_ONE, show_alert=True)
        return
    cancel_done_button(call.message.chat.id)
    # Убираем кнопку у плавающего сообщения (оставляем счётчик)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.answer()
    await _go_to_listing_about(call.message, state)


@router.callback_query(Form.apartment_photos, F.data == "aptphoto:skip")
async def step_apartment_photos_skip(call: CallbackQuery, state: FSMContext) -> None:
    """Пропустить фото квартиры — фото необязательны."""
    cancel_done_button(call.message.chat.id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.answer()
    data = await state.get_data()
    if not (data.get("apartment_photos") or []):
        await call.message.answer(texts.PHOTO_SKIP_HINT)
    await _go_to_listing_about(call.message, state)


@router.message(Form.apartment_photos)
async def step_apartment_photos_wrong(message: Message) -> None:
    await message.answer(texts.ASK_APARTMENT_PHOTOS)


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


# ====================== ШАГ 7 — ФОТО / ВИДЕО (обязательно) ======================

@router.message(Form.photo, F.photo)
async def step_photo(message: Message, state: FSMContext) -> None:
    await collect_profile_photo(
        message, state,
        list_key="profile_media", type_key="profile_media_type",
        done_action="media:done", max_count=MAX_PROFILE_PHOTOS,
    )


@router.message(Form.photo, F.video)
async def step_video(message: Message, state: FSMContext) -> None:
    await collect_profile_video(
        message, state,
        list_key="profile_media", type_key="profile_media_type",
        done_action="media:done",
    )


async def _go_to_about(message: Message, state: FSMContext) -> None:
    """Перейти к «о себе» (после фото профиля — Готово или Пропустить)."""
    await state.set_state(Form.about)
    await message.answer(texts.ASK_ABOUT)


@router.callback_query(Form.photo, F.data == "media:done")
async def step_photo_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not (data.get("profile_media") or []):
        await call.answer(texts.PHOTO_NEED_ONE, show_alert=True)
        return
    cancel_done_button(call.message.chat.id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.answer()
    await _go_to_about(call.message, state)


@router.callback_query(Form.photo, F.data == "photo:skip")
async def step_photo_skip(call: CallbackQuery, state: FSMContext) -> None:
    """Пропустить фото профиля — фото необязательны."""
    cancel_done_button(call.message.chat.id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.answer()
    data = await state.get_data()
    if not (data.get("profile_media") or []):
        await call.message.answer(texts.PHOTO_SKIP_HINT)
    await _go_to_about(call.message, state)


@router.message(Form.photo)
async def step_photo_wrong(message: Message) -> None:
    await message.answer(texts.SEND_PHOTO_OR_SKIP)


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


# ====================== СОХРАНЕНИЕ И ПОКАЗ АНКЕТЫ ======================

async def _show_card_preview(message: Message, state: FSMContext) -> None:
    """
    Финал регистрации: сразу сохраняем анкету и показываем её
    с обычным меню действий (как /profile). Без шага подтверждения.
    """
    data = await state.get_data()
    # Дополняем данными из Telegram-профиля.
    # full_name НЕ трогаем — там имя, которое пользователь ввёл сам.
    data["telegram_id"] = message.from_user.id
    data["username"] = message.from_user.username
    data.setdefault("full_name", message.from_user.full_name)

    await upsert_user(data)
    await state.clear()

    await send_media_card(
        message, data, cards.user_card(data),
        reply_markup=inline.profile_menu_kb(data.get("role")),
    )


# ====================== ОБРАБОТКА НЕВЕРНОГО ВВОДА ======================
# Если пользователь пишет текст там, где ждут кнопку — вежливо напоминаем.

@router.message(Form.gender)
@router.message(Form.goal)
@router.message(Form.city)
async def wrong_input_button(message: Message) -> None:
    await message.answer(texts.PRESS_BUTTON)
