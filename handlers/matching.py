# -*- coding: utf-8 -*-
"""
Поиск сожителей (/search) и логика лайков / взаимных мэтчей.
"""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

import texts
from database.db import (
    add_like,
    add_view,
    get_next_candidate,
    get_user,
    has_like,
)
from keyboards import inline

router = Router()


# ====================== /search ======================

@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    """Начать поиск кандидатов."""
    viewer = await get_user(message.from_user.id)
    if viewer is None:
        await message.answer(texts.SEARCH_NO_PROFILE)
        return
    if not viewer["is_active"]:
        await message.answer(texts.SEARCH_PAUSED)
        return
    await start_search(message, viewer)


async def start_search(message: Message, viewer) -> None:
    """Показать первого кандидата (или сообщить, что подходящих нет).

    Используется командой /search и быстрым путём регистрации «есть жильё».
    """
    candidate = await get_next_candidate(viewer)
    if candidate is None:
        await message.answer(texts.SEARCH_EMPTY)
        return
    await _send_candidate(message, candidate)


async def _send_candidate(message: Message, candidate) -> None:
    """Показать карточку кандидата с кнопками действий.

    Объявление (provider) — альбом фото квартиры + текст с кнопками.
    Анкета (seeker) — фото (если есть) + текст с кнопками.
    """
    cid = candidate["telegram_id"]
    kb = inline.match_kb(cid)

    if candidate["role"] == "provider":
        photos = candidate["apartment_photos"] or []
        if photos:
            media = [InputMediaPhoto(media=fid) for fid in photos]
            await message.answer_media_group(media)
        await message.answer(texts.listing_card(candidate), reply_markup=kb)
    elif candidate["photo_file_id"]:
        await message.answer_photo(
            photo=candidate["photo_file_id"],
            caption=texts.profile_card(candidate, header=None),
            reply_markup=kb,
        )
    else:
        await message.answer(
            texts.profile_card(candidate, header=None), reply_markup=kb
        )


async def _show_next(message: Message, viewer_id: int) -> None:
    """Показать следующего кандидата (или сообщить, что анкеты закончились)."""
    viewer = await get_user(viewer_id)
    candidate = await get_next_candidate(viewer)
    if candidate is None:
        await message.answer(texts.SEARCH_END)
        return
    await _send_candidate(message, candidate)


# ====================== ЛАЙК / СУПЕР-ЛАЙК / ПРОПУСК ======================

@router.callback_query(F.data.startswith("like:"))
async def on_like(call: CallbackQuery, bot: Bot) -> None:
    await _process_like(call, bot, is_super=False)


@router.callback_query(F.data.startswith("super:"))
async def on_superlike(call: CallbackQuery, bot: Bot) -> None:
    await _process_like(call, bot, is_super=True)


@router.callback_query(F.data.startswith("pass:"))
async def on_pass(call: CallbackQuery) -> None:
    """Пропустить кандидата — просто отмечаем как просмотренного."""
    candidate_id = int(call.data.split(":", 1)[1])
    await add_view(call.from_user.id, candidate_id)
    await _remove_buttons(call)
    await call.answer(texts.SKIPPED)
    await _show_next(call.message, call.from_user.id)


async def _process_like(call: CallbackQuery, bot: Bot, is_super: bool) -> None:
    """Общая логика лайка и супер-лайка + проверка взаимного мэтча."""
    viewer_id = call.from_user.id
    candidate_id = int(call.data.split(":", 1)[1])

    await add_view(viewer_id, candidate_id)
    await add_like(viewer_id, candidate_id, is_super=is_super)

    await _remove_buttons(call)
    await call.answer(texts.SUPERLIKE_SENT if is_super else texts.LIKE_SENT)

    # Проверяем взаимность: лайкнул ли кандидат смотрящего ранее
    if await has_like(candidate_id, viewer_id):
        await _notify_match(bot, viewer_id, candidate_id)

    await _show_next(call.message, viewer_id)


async def _notify_match(bot: Bot, user_a: int, user_b: int) -> None:
    """Отправить обоим участникам сообщение о мэтче."""
    a = await get_user(user_a)
    b = await get_user(user_b)
    if a is None or b is None:
        return

    # Пишем каждому контакт другого
    await bot.send_message(user_a, texts.match_message(b["full_name"], b["username"]))
    await bot.send_message(user_b, texts.match_message(a["full_name"], a["username"]))


async def _remove_buttons(call: CallbackQuery) -> None:
    """Убрать кнопки из показанной карточки, чтобы их нельзя было нажать снова."""
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        # Например, если сообщение слишком старое — игнорируем
        pass
