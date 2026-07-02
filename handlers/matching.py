# -*- coding: utf-8 -*-
"""
Поиск сожителей (/search) и логика лайков / взаимных мэтчей.
"""

import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.render import send_media_card, send_media_card_to_chat

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
async def cmd_search(message: Message, state: FSMContext) -> None:
    """Начать поиск кандидатов."""
    await state.clear()  # команда прерывает незавершённую регистрацию
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
    candidate = await get_next_candidate(viewer["telegram_id"])
    if candidate is None:
        await message.answer(texts.SEARCH_EMPTY)
        return
    await _send_candidate(message, candidate)


async def _send_candidate(message: Message, candidate) -> None:
    """Показать карточку кандидата с кнопками действий (через общий рендер)."""
    kb = inline.match_kb(candidate["telegram_id"])
    await send_media_card(message, candidate, texts.user_card(candidate), reply_markup=kb)


async def _show_next(message: Message, viewer_id: int) -> None:
    """Показать следующего кандидата (или сообщить, что анкеты закончились)."""
    candidate = await get_next_candidate(viewer_id)
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

    # Три независимые операции БД выполняем разом (одним round-trip вместо трёх):
    # отметить просмотр, поставить лайк и проверить встречный лайк кандидата.
    _, _, reciprocal = await asyncio.gather(
        add_view(viewer_id, candidate_id),
        add_like(viewer_id, candidate_id, is_super=is_super),
        has_like(candidate_id, viewer_id),
    )

    await _remove_buttons(call)
    await call.answer(texts.SUPERLIKE_SENT if is_super else texts.LIKE_SENT)

    if reciprocal:
        # Оба лайкнули друг друга → мэтч, шлём контакт обоим
        await _notify_match(bot, viewer_id, candidate_id)
    else:
        # Иначе сразу уведомляем кандидата: «тебя лайкнули» + его выбор
        await _notify_incoming_like(bot, viewer_id, candidate_id, is_super)

    await _show_next(call.message, viewer_id)


async def _notify_incoming_like(bot: Bot, liker_id: int, target_id: int,
                                is_super: bool) -> None:
    """Показать получателю анкету лайкнувшего и кнопки принять/отказаться."""
    liker = await get_user(liker_id)
    if liker is None:
        return
    header = texts.incoming_like_header(is_super)
    caption = f"{header}\n\n{texts.user_card(liker)}"
    try:
        await send_media_card_to_chat(
            bot, target_id, liker, caption,
            reply_markup=inline.incoming_like_kb(liker_id),
        )
    except Exception:
        # Получатель мог заблокировать бота / не начинал диалог — игнорируем
        pass


# ====================== ВХОДЯЩИЙ ЛАЙК: ПРИНЯТЬ / ОТКАЗАТЬСЯ ======================

@router.callback_query(F.data.startswith("accept:"))
async def on_accept(call: CallbackQuery, bot: Bot) -> None:
    """«Перейти к переписке» — лайк в ответ, что даёт мэтч и контакт обоим."""
    liker_id = int(call.data.split(":", 1)[1])
    me = call.from_user.id
    await add_view(me, liker_id)
    await add_like(me, liker_id, is_super=False)
    await _remove_buttons(call)
    await call.answer(texts.MATCH_ACCEPTED)
    await _notify_match(bot, me, liker_id)


@router.callback_query(F.data.startswith("decline:"))
async def on_decline(call: CallbackQuery) -> None:
    """«Отказаться» — помечаем лайкнувшего просмотренным, больше не показываем."""
    liker_id = int(call.data.split(":", 1)[1])
    await add_view(call.from_user.id, liker_id)
    await _remove_buttons(call)
    await call.answer(texts.MATCH_DECLINED)


async def _notify_match(bot: Bot, user_a: int, user_b: int) -> None:
    """Отправить обоим участникам сообщение о мэтче."""
    a = await get_user(user_a)
    b = await get_user(user_b)
    if a is None or b is None:
        return

    # Пишем каждому контакт другого (имя — кликабельная ссылка на профиль)
    await bot.send_message(
        user_a, texts.match_message(b["full_name"], b["username"], b["telegram_id"])
    )
    await bot.send_message(
        user_b, texts.match_message(a["full_name"], a["username"], a["telegram_id"])
    )


async def _remove_buttons(call: CallbackQuery) -> None:
    """Убрать кнопки из показанной карточки, чтобы их нельзя было нажать снова."""
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        # Например, если сообщение слишком старое — игнорируем
        pass
