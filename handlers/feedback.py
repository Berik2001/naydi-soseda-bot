# -*- coding: utf-8 -*-
"""
Обратная связь: пользователь пишет создателю бота через /feedback, не имея
его прямого контакта. Сообщение ретранслируется всем админам (config.get_admin_ids)
с идентификацией отправителя (кликабельное имя + @username + id), чтобы можно
было при желании ответить.

Защита от спама админам: помимо глобального throttling — персональный кулдаун
между сообщениями (config.FEEDBACK_COOLDOWN_SEC), в памяти процесса.
"""

from __future__ import annotations

import html
import logging
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import texts
from keyboards import inline
from states.form import Feedback
from tg_retry import with_flood_retry

logger = logging.getLogger(__name__)

router = Router()

# Время последней успешной обратной связи по пользователю (антиспам-кулдаун).
# В памяти процесса: как _locks в media_flow — на один инстанс, чистится по cap.
_last_feedback: dict[int, float] = {}
_COOLDOWN_CAP = 10_000


def _cooldown_left(user_id: int, now: float) -> int:
    """Сколько секунд осталось до разрешённой следующей отправки (0 — можно)."""
    last = _last_feedback.get(user_id)
    if last is None:
        return 0
    left = config.FEEDBACK_COOLDOWN_SEC - (now - last)
    return int(left) + 1 if left > 0 else 0


def _remember(user_id: int, now: float) -> None:
    if len(_last_feedback) >= _COOLDOWN_CAP:
        # Выбрасываем записи, у которых кулдаун давно истёк.
        stale = [u for u, t in _last_feedback.items()
                 if now - t >= config.FEEDBACK_COOLDOWN_SEC]
        for u in stale:
            _last_feedback.pop(u, None)
    _last_feedback[user_id] = now


# ====================== /feedback ======================

@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext) -> None:
    """Начать обратную связь: перевести в состояние ожидания текста."""
    await state.set_state(Feedback.waiting)
    await message.answer(texts.FEEDBACK_ASK, reply_markup=inline.feedback_cancel_kb())


@router.callback_query(Feedback.waiting, F.data == "feedback:cancel")
async def feedback_cancel(call: CallbackQuery, state: FSMContext) -> None:
    """Отмена обратной связи."""
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.message.answer(texts.FEEDBACK_CANCELLED)
    await call.answer()


@router.message(Feedback.waiting, F.text)
async def feedback_receive(message: Message, state: FSMContext) -> None:
    """Принять текст, проверить и ретранслировать админам."""
    text = message.text.strip()
    if not text:
        await message.answer(texts.FEEDBACK_EMPTY)
        return
    if len(text) > config.FEEDBACK_MAX_LEN:
        await message.answer(texts.FEEDBACK_TOO_LONG)
        return

    now = time.monotonic()
    left = _cooldown_left(message.from_user.id, now)
    if left > 0:
        await message.answer(texts.feedback_cooldown(left))
        return

    await _relay_to_admins(message, text)
    _remember(message.from_user.id, now)
    await state.clear()
    await message.answer(texts.FEEDBACK_SENT)


@router.message(Feedback.waiting)
async def feedback_wrong(message: Message) -> None:
    """На шаге обратной связи ждём именно текст."""
    await message.answer(texts.FEEDBACK_TEXT_ONLY)


# ====================== РЕТРАНСЛЯЦИЯ АДМИНАМ ======================

def _format(user, text: str) -> str:
    """Сообщение для админа: кто написал (кликабельно) + сам текст (экранирован)."""
    name = html.escape(user.full_name or "без имени")
    uname = f"@{user.username}" if user.username else "—"
    return (
        "📩 <b>Обратная связь</b>\n"
        f"От: <a href=\"tg://user?id={user.id}\">{name}</a> ({html.escape(uname)})\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{html.escape(text)}"
    )


async def _relay_to_admins(message: Message, text: str) -> None:
    """Отправить обратную связь всем админам, переживая флуд-лимит. Best-effort."""
    payload = _format(message.from_user, text)
    for admin_id in config.get_admin_ids():
        try:
            await with_flood_retry(
                lambda aid=admin_id: message.bot.send_message(aid, payload)
            )
        except Exception:  # noqa: BLE001 — один недоступный админ не мешает остальным
            logger.warning("Обратная связь не доставлена админу %s.", admin_id)
