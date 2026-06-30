# -*- coding: utf-8 -*-
"""
Команды: /start, /help, /profile, /edit, /pause, /resume.
"""

import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.render import send_media_card

# Максимум фото квартиры (как в регистрации)
MAX_APARTMENT_PHOTOS = 10

# Сериализует чтение-запись списка фото при конкурентной загрузке альбома
# (aiogram обрабатывает апдейты как параллельные задачи).
_photos_lock = asyncio.Lock()

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
    "goal": texts.GOAL,
    "move_in": texts.MOVE_IN,
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
    """Показать полную анкету/объявление и меню действий."""
    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return
    await state.clear()
    # Кнопки меню прикрепляем прямо к карточке — без отдельного сообщения
    await send_full_card(message, user, reply_markup=inline.profile_menu_kb(user["role"]))


async def send_full_card(message: Message, user, reply_markup=None) -> None:
    """Показать полную карточку (своя анкета/объявление) с прикреплённым меню."""
    card = texts.listing_card(user) if user["role"] == "provider" else texts.profile_card(user)
    await send_media_card(message, user, card, reply_markup=reply_markup)


async def show_updated_profile(message: Message, telegram_id: int) -> None:
    """
    После любого редактирования — заново показать обновлённую анкету
    с меню действий (как /profile), а не сухое «Изменено».
    """
    user = await get_user(telegram_id)
    if user is None:
        await message.answer(texts.NO_PROFILE)
        return
    await send_full_card(message, user, reply_markup=inline.profile_menu_kb(user["role"]))


# ---------- Пункты меню «Моя анкета» ----------

@router.callback_query(F.data == "profile:feed")
async def profile_feed(call: CallbackQuery) -> None:
    """👀 Лента: объявления (ищущим) / анкеты (сдающим)."""
    user = await get_user(call.from_user.id)
    if user is None:
        await call.message.answer(texts.NO_PROFILE)
        await call.answer()
        return
    if not user["is_active"]:
        await call.message.answer(texts.SEARCH_PAUSED)
        await call.answer()
        return
    from handlers.matching import start_search
    await start_search(call.message, user)
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


@router.callback_query(F.data == "profile:about")
async def profile_about(call: CallbackQuery, state: FSMContext) -> None:
    """✍️ Изменить «о себе» — общий поток текстового редактирования.
    Для сдающего это описание объявления (с примером по полу)."""
    user = await get_user(call.from_user.id)
    await state.set_state(Edit.waiting_value)
    await state.update_data(edit_field="about")
    if user and user["role"] == "provider":
        prompt = texts.ask_listing_desc(user["gender"])
    else:
        prompt = texts.ASK_ABOUT
    await call.message.answer(prompt)
    await call.answer()


# ---------- Изменение фото квартиры (provider) ----------

@router.callback_query(F.data == "profile:apt_photos")
async def profile_apt_photos(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Edit.waiting_apartment_photos)
    await state.update_data(apt_photos=[])
    await call.message.answer(
        texts.ASK_APARTMENT_PHOTOS, reply_markup=inline.photos_done_kb("aptphoto:done")
    )
    await call.answer()


@router.message(Edit.waiting_apartment_photos, F.photo)
async def edit_apt_photo(message: Message, state: FSMContext) -> None:
    async with _photos_lock:
        data = await state.get_data()
        photos = list(data.get("apt_photos") or [])
        if len(photos) >= MAX_APARTMENT_PHOTOS:
            return  # больше 10 не добавляем (молча)
        photos.append(message.photo[-1].file_id)
        await state.update_data(apt_photos=photos)
    # На каждое фото не отвечаем — кнопка «Готово ✅» уже под приглашением.


@router.callback_query(Edit.waiting_apartment_photos, F.data == "aptphoto:done")
async def edit_apt_photos_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("apt_photos") or []
    if not photos:
        await call.answer(texts.APARTMENT_PHOTOS_NEED_ONE, show_alert=True)
        return
    await update_field(call.from_user.id, "apartment_photos", photos)
    await state.clear()
    await call.message.answer(texts.PHOTO_UPDATED)
    await call.answer()
    await show_updated_profile(call.message, call.from_user.id)


@router.message(Edit.waiting_apartment_photos)
async def edit_apt_photos_wrong(message: Message) -> None:
    await message.answer(
        texts.ASK_APARTMENT_PHOTOS, reply_markup=inline.photos_done_kb("aptphoto:done")
    )


# ---------- Изменение медиа профиля (seeker: до 2 фото / 1 видео) ----------

@router.callback_query(F.data == "profile:photo")
async def profile_photo(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Edit.waiting_photo)
    await state.update_data(new_media=[], new_media_type=None)
    await call.message.answer(texts.ASK_PHOTO, reply_markup=inline.photos_done_kb("media:done"))
    await call.answer()


@router.message(Edit.waiting_photo, F.photo)
async def profile_photo_set(message: Message, state: FSMContext) -> None:
    async with _photos_lock:
        data = await state.get_data()
        media = list(data.get("new_media") or [])
        if data.get("new_media_type") == "video":
            await message.answer(texts.MEDIA_PHOTO_AFTER_VIDEO)
            return
        if len(media) >= 2:
            await message.answer(texts.PHOTO_MAX_TWO)
            return
        media.append(message.photo[-1].file_id)
        await state.update_data(new_media=media, new_media_type="photo")
    # На каждое фото не отвечаем — кнопка «Готово ✅» уже под приглашением.


@router.message(Edit.waiting_photo, F.video)
async def profile_video_set(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("new_media") and data.get("new_media_type") == "photo":
        await message.answer(texts.MEDIA_VIDEO_AFTER_PHOTO)
        return
    await state.update_data(new_media=[message.video.file_id], new_media_type="video")
    await message.answer(texts.MEDIA_VIDEO_ADDED)


@router.callback_query(Edit.waiting_photo, F.data == "media:done")
async def profile_media_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    media = data.get("new_media") or []
    if not media:
        await call.answer(texts.PHOTO_NEED_ONE, show_alert=True)
        return
    await update_field(call.from_user.id, "profile_media", media)
    await update_field(call.from_user.id, "profile_media_type", data.get("new_media_type"))
    await state.clear()
    await call.message.answer(texts.PHOTO_UPDATED)
    await call.answer()
    await show_updated_profile(call.message, call.from_user.id)


@router.message(Edit.waiting_photo)
async def profile_photo_wrong(message: Message) -> None:
    await message.answer(texts.PHOTO_NEED_ONE, reply_markup=inline.photos_done_kb("media:done"))


# ---------- Изменение города / района ----------

@router.callback_query(F.data == "profile:location")
async def profile_location(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer(texts.ASK_CITY, reply_markup=inline.profile_city_kb())
    await call.answer()


async def _ask_profile_district(call: CallbackQuery, state: FSMContext) -> None:
    """Район вводится текстом (пользователь пишет сам)."""
    user = await get_user(call.from_user.id)
    role = user["role"] if user else None
    await state.set_state(Edit.waiting_loc_district)
    await call.message.edit_text(texts.ask_district(role))


@router.callback_query(F.data.startswith("pcity:"))
async def profile_city_set(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    if value == "other":
        await state.set_state(Edit.waiting_loc_city)
        await call.message.edit_text(texts.ASK_CITY_CUSTOM)
        await call.answer()
        return
    await update_field(call.from_user.id, "city", value)
    await _ask_profile_district(call, state)
    await call.answer()


@router.message(Edit.waiting_loc_city, F.text)
async def profile_city_text(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    await update_field(message.from_user.id, "city", city)
    user = await get_user(message.from_user.id)
    role = user["role"] if user else None
    # Район вводится текстом
    await state.set_state(Edit.waiting_loc_district)
    await message.answer(texts.ask_district(role))


@router.message(Edit.waiting_loc_district, F.text)
async def profile_district_text(message: Message, state: FSMContext) -> None:
    await update_field(message.from_user.id, "district", message.text.strip())
    await state.clear()
    await message.answer(texts.PROFILE_UPDATED)
    await show_updated_profile(message, message.from_user.id)


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
        if field == "district":
            user = await get_user(call.from_user.id)
            prompt = texts.ask_district(user["role"] if user else None)
        else:
            prompt = {
                "city": texts.ASK_CITY_CUSTOM,
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
    # Цель определяет роль (seeker/provider) — синхронизируем
    if field == "goal":
        await update_field(call.from_user.id, "role", texts.GOAL_ROLE[key])
    # Пол сожителя всегда равен собственному полу — синхронизируем при смене пола
    if field == "gender":
        await update_field(call.from_user.id, "preferred_gender", key)

    await call.message.edit_text("✅ Изменено!")
    await call.answer("Готово")
    await show_updated_profile(call.message, call.from_user.id)


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
    await show_updated_profile(message, message.from_user.id)
