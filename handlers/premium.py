# -*- coding: utf-8 -*-
"""
Премиум через Telegram Stars (валюта XTR, без внешнего платёжного провайдера).

Флоу оплаты:
  1. Пользователь жмёт «Купить» -> бот шлёт инвойс (answer_invoice, currency=XTR).
  2. Telegram присылает pre_checkout_query -> отвечаем ok=True.
  3. После оплаты приходит message.successful_payment -> начисляем премиум.
"""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import texts
from database.db import (
    activate_premium,
    get_premium_until,
    is_premium,
    who_liked_me,
)
from keyboards import inline

router = Router()

# --- Настройки премиума (легко менять) ---
PREMIUM_STARS = 150     # цена в Telegram Stars
PREMIUM_DAYS = 30       # срок действия в днях
PREMIUM_PAYLOAD = "premium_30d"  # идентификатор товара в payload инвойса


# ====================== ЭКРАН ПРЕМИУМА ======================

async def _show_premium_screen(message: Message, user_id: int) -> None:
    """Показать статус премиума: активен -> инфо+кнопка, иначе -> оффер с покупкой."""
    if await is_premium(user_id):
        until = await get_premium_until(user_id)
        until_str = until.strftime("%d.%m.%Y") if until else "—"
        await message.answer(
            texts.premium_active(until_str),
            reply_markup=inline.premium_active_kb(),
        )
    else:
        await message.answer(
            texts.premium_offer(PREMIUM_STARS, PREMIUM_DAYS),
            reply_markup=inline.premium_buy_kb(PREMIUM_STARS),
        )


@router.callback_query(F.data == "profile:premium")
async def open_premium(call: CallbackQuery) -> None:
    """Открыть экран премиума из меню анкеты."""
    await _show_premium_screen(call.message, call.from_user.id)
    await call.answer()


@router.message(Command("premium"))
async def cmd_premium(message: Message, state: FSMContext) -> None:
    """Команда /premium."""
    await state.clear()  # команда прерывает незавершённую регистрацию
    await _show_premium_screen(message, message.from_user.id)


# ====================== ПОКУПКА (Telegram Stars) ======================

@router.callback_query(F.data == "premium:buy")
async def buy_premium(call: CallbackQuery) -> None:
    """Отправить инвойс на оплату звёздами."""
    await call.message.answer_invoice(
        title="Премиум на 30 дней",
        description="Топ выдачи + просмотр тех, кто тебя лайкнул.",
        payload=PREMIUM_PAYLOAD,
        currency="XTR",  # Telegram Stars
        # Для Stars provider_token не нужен (пустая строка)
        provider_token="",
        prices=[LabeledPrice(label="Премиум 30 дней", amount=PREMIUM_STARS)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot) -> None:
    """Подтвердить готовность принять платёж (обязательный шаг Telegram)."""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    """Платёж прошёл — начисляем премиум."""
    await activate_premium(message.from_user.id, PREMIUM_DAYS)
    await message.answer(texts.PREMIUM_ACTIVATED)


# ====================== «КТО МЕНЯ ЛАЙКНУЛ» (премиум-фича) ======================

@router.callback_query(F.data == "premium:wholiked")
async def who_liked(call: CallbackQuery) -> None:
    """Показать список лайкнувших — только для премиум-пользователей."""
    if not await is_premium(call.from_user.id):
        await call.message.answer(
            texts.PREMIUM_REQUIRED,
            reply_markup=inline.premium_buy_kb(PREMIUM_STARS),
        )
        await call.answer()
        return

    rows = await who_liked_me(call.from_user.id)
    if not rows:
        await call.message.answer(texts.WHO_LIKED_EMPTY)
        await call.answer()
        return

    lines = [texts.WHO_LIKED_HEADER]
    for r in rows:
        lines.append(texts.liked_by_line(r, r["is_super"]))
    await call.message.answer("\n".join(lines))
    await call.answer()
