# -*- coding: utf-8 -*-
"""
Поиск сожителей (/search) и логика лайков / взаимных мэтчей.
"""

from __future__ import annotations  # поддержка "X | None" на Python 3.9

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.render import send_media_card, send_media_card_to_chat

import cards
import config
import texts
from database.matching import add_view, get_next_candidate, like_usage, register_like
from database.users import delete_user, get_user
from keyboards import inline
from tg_retry import with_flood_retry

logger = logging.getLogger(__name__)

router = Router()


def _parse_target_id(data: str | None) -> int | None:
    """
    Безопасно достать telegram_id из callback_data «<префикс>:<id>».

    callback_data приходит от клиента и в самописном клиенте может быть любым:
    поэтому не доверяем и парсим через try. None → коллбэк битый/подделанный,
    хендлер просто тихо его гасит (int(...) раньше кидал ValueError → шум в логах).
    """
    if not data:
        return None
    try:
        return int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


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
    await _send_candidate(message, candidate, viewer["telegram_id"])


async def _send_candidate(message: Message, candidate, viewer_id: int) -> None:
    """Показать карточку кандидата с кнопками действий (через общий рендер).

    Админам добавляется модераторская кнопка «🗑 Удалить» (см. match_kb).
    """
    is_admin = viewer_id in config.get_admin_ids()
    kb = inline.match_kb(candidate["telegram_id"], is_admin=is_admin)
    await send_media_card(message, candidate, cards.user_card(candidate), reply_markup=kb)


async def _show_next(message: Message, viewer_id: int) -> None:
    """Показать следующего кандидата (или сообщить, что анкеты закончились)."""
    candidate = await get_next_candidate(viewer_id)
    if candidate is None:
        await message.answer(texts.SEARCH_END)
        return
    await _send_candidate(message, candidate, viewer_id)


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
    candidate_id = _parse_target_id(call.data)
    if candidate_id is None:
        await call.answer()
        return
    await add_view(call.from_user.id, candidate_id)
    await _remove_buttons(call)
    await call.answer(texts.SKIPPED)
    await _show_next(call.message, call.from_user.id)


async def _process_like(call: CallbackQuery, bot: Bot, is_super: bool) -> None:
    """Общая логика лайка и супер-лайка + проверка взаимного мэтча."""
    viewer_id = call.from_user.id
    candidate_id = _parse_target_id(call.data)
    if candidate_id is None:
        await call.answer()
        return

    # Дневной лимит лайков (бесплатным). Премиум не ограничиваем. Пропуск (👎) и
    # приём входящего лайка (on_accept) лимит НЕ тратят — только проактивный лайк.
    if config.FREE_DAILY_LIKES > 0:
        is_prem, used = await like_usage(viewer_id)
        if not is_prem and used >= config.FREE_DAILY_LIKES:
            await call.answer(texts.LIKE_LIMIT_ALERT, show_alert=True)
            return  # карточку и кнопки оставляем — можно листать пропуском

    # Просмотр + лайк + проверка встречного лайка — одним соединением пула.
    # is_new=False, если лайк уже стоял (повторный или подделанный коллбэк):
    # тогда НЕ шлём получателю новое уведомление — защита от спама.
    is_new, reciprocal = await register_like(viewer_id, candidate_id, is_super=is_super)

    await _remove_buttons(call)
    await call.answer(texts.SUPERLIKE_SENT if is_super else texts.LIKE_SENT)

    if reciprocal:
        # Оба лайкнули друг друга → мэтч, шлём контакт обоим
        await _notify_match(bot, viewer_id, candidate_id)
    elif is_new:
        # Только на ПЕРВЫЙ лайк уведомляем кандидата: «тебя лайкнули» + его выбор
        await _notify_incoming_like(bot, viewer_id, candidate_id, is_super)

    await _show_next(call.message, viewer_id)


async def _notify_incoming_like(bot: Bot, liker_id: int, target_id: int,
                                is_super: bool) -> None:
    """Показать получателю анкету лайкнувшего и кнопки принять/отказаться."""
    liker = await get_user(liker_id)
    if liker is None:
        return
    header = texts.incoming_like_header(is_super)
    caption = f"{header}\n\n{cards.user_card(liker)}"
    try:
        # Примитивы отправки внутри уже переживают флуд-лимит (см. render.py).
        await send_media_card_to_chat(
            bot, target_id, liker, caption,
            reply_markup=inline.incoming_like_kb(liker_id),
        )
    except TelegramForbiddenError:
        # Получатель заблокировал бота / не начинал диалог — ожидаемо, молча.
        pass
    except TelegramRetryAfter:
        # Флуд-лимит не переждан за отведённые попытки — уведомление потеряно.
        logger.warning("Уведомление о лайке не доставлено %s: флуд-лимит Telegram.", target_id)
    except Exception:
        logger.exception("Сбой доставки уведомления о лайке %s.", target_id)


# ====================== ВХОДЯЩИЙ ЛАЙК: ПРИНЯТЬ / ОТКАЗАТЬСЯ ======================

@router.callback_query(F.data.startswith("accept:"))
async def on_accept(call: CallbackQuery, bot: Bot) -> None:
    """«Перейти к переписке» — лайк в ответ, что даёт мэтч и контакт обоим."""
    liker_id = _parse_target_id(call.data)
    if liker_id is None:
        await call.answer()
        return
    me = call.from_user.id
    # Просмотр + ответный лайк одним соединением; лайкнувший нас уже лайкнул → мэтч.
    await register_like(me, liker_id, is_super=False)
    await _remove_buttons(call)
    await call.answer(texts.MATCH_ACCEPTED)
    await _notify_match(bot, me, liker_id)


@router.callback_query(F.data.startswith("decline:"))
async def on_decline(call: CallbackQuery) -> None:
    """«Отказаться» — помечаем лайкнувшего просмотренным и сразу возвращаем
    пользователя к его собственной анкете с меню действий."""
    liker_id = _parse_target_id(call.data)
    if liker_id is None:
        await call.answer()
        return
    await add_view(call.from_user.id, liker_id)
    await _remove_buttons(call)
    await call.answer(texts.MATCH_DECLINED)
    # Ленивый импорт разрывает цикл импорта (start импортирует matching).
    from handlers.start import show_updated_profile
    await show_updated_profile(call.message, call.from_user.id)


# ====================== АДМИН: УДАЛЕНИЕ ОБЪЯВЛЕНИЯ ======================
# Кнопка «🗑 Удалить» показывается на карточке только админам (см. match_kb).
# Каждый колбэк перепроверяет права: даже подделанный admindel:* от не-админа
# ничего не удалит.

def _is_admin(user_id: int) -> bool:
    return user_id in config.get_admin_ids()


@router.callback_query(F.data.startswith("admindel:"))
async def on_admin_delete(call: CallbackQuery) -> None:
    """«🗑 Удалить» — показать подтверждение (защита от случайного тапа)."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    target = _parse_target_id(call.data)
    if target is None:
        await call.answer()
        return
    try:
        await call.message.edit_reply_markup(
            reply_markup=inline.admin_delete_confirm_kb(target)
        )
    except Exception:  # noqa: BLE001 — сообщение старое/без кнопок
        pass
    await call.answer()


@router.callback_query(F.data.startswith("admindelok:"))
async def on_admin_delete_ok(call: CallbackQuery) -> None:
    """Подтверждение: удалить анкету/объявление и показать следующего."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    target = _parse_target_id(call.data)
    if target is None:
        await call.answer()
        return
    deleted = await delete_user(target)
    logger.info("Админ %s удалил анкету %s (найдена=%s).",
                call.from_user.id, target, deleted)
    await _remove_buttons(call)
    await call.answer("🗑 Удалено" if deleted else "Анкета уже удалена", show_alert=not deleted)
    await _show_next(call.message, call.from_user.id)


@router.callback_query(F.data.startswith("admindelno:"))
async def on_admin_delete_cancel(call: CallbackQuery) -> None:
    """Отмена: вернуть обычные кнопки карточки (с админ-кнопкой)."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    target = _parse_target_id(call.data)
    if target is None:
        await call.answer()
        return
    try:
        await call.message.edit_reply_markup(
            reply_markup=inline.match_kb(target, is_admin=True)
        )
    except Exception:  # noqa: BLE001
        pass
    await call.answer()


async def _notify_match(bot: Bot, user_a: int, user_b: int) -> None:
    """Отправить обоим участникам сообщение о мэтче."""
    # Профили обоих читаем разом (независимые запросы)
    a, b = await asyncio.gather(get_user(user_a), get_user(user_b))
    if a is None or b is None:
        return

    # Пишем каждому контакт другого (имя — кликабельная ссылка на профиль).
    # Доставка обоим независима и best-effort: блокировка/сбой у одного не мешает
    # другому, а флуд-лимит Telegram (429) переживаем повтором (см. _deliver_match).
    await asyncio.gather(
        _deliver_match(bot, user_a, b),
        _deliver_match(bot, user_b, a),
    )


async def _deliver_match(bot: Bot, chat_id: int, other) -> None:
    """Доставить одному участнику контакт другого, переживая флуд-лимит."""
    text = cards.match_message(other["full_name"], other["username"], other["telegram_id"])
    try:
        await with_flood_retry(lambda: bot.send_message(chat_id, text))
    except TelegramForbiddenError:
        # Заблокировал бота / не начинал диалог — ожидаемо, молча.
        pass
    except TelegramRetryAfter:
        # Не переждали флуд-лимит за отведённые попытки — уведомление о мэтче потеряно.
        logger.warning("Уведомление о мэтче не доставлено %s: флуд-лимит Telegram.", chat_id)
    except Exception:
        logger.exception("Сбой доставки уведомления о мэтче %s.", chat_id)


async def _remove_buttons(call: CallbackQuery) -> None:
    """Убрать кнопки из показанной карточки, чтобы их нельзя было нажать снова."""
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        # Например, если сообщение слишком старое — игнорируем
        pass
