# -*- coding: utf-8 -*-
"""
Устойчивая доставка в Telegram: переживание флуд-лимита (HTTP 429).

Telegram ограничивает бота ~30 сообщениями в секунду глобально. При всплеске
(массовая рассылка уведомлений о мэтчах/лайках) часть вызовов возвращает 429, и
aiogram бросает TelegramRetryAfter с полем retry_after. Раньше такие ошибки
глотались вместе с остальными — уведомление терялось без следа. Здесь — короткий
повтор с ожиданием ровно того времени, что просит Telegram.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from aiogram.exceptions import TelegramRetryAfter

T = TypeVar("T")

# Сколько раз повторяем после 429, прежде чем сдаться. Флуд-паузы Telegram обычно
# 1–5 сек; 2 повтора переживают типичный всплеск, не подвешивая обработку надолго.
DEFAULT_RETRIES = 2


async def with_flood_retry(
    factory: Callable[[], Awaitable[T]], *, retries: int = DEFAULT_RETRIES
) -> T:
    """
    Выполнить отправку в Telegram, переживая флуд-лимит (TelegramRetryAfter):
    ждём запрошенный Telegram retry_after и повторяем (до `retries` раз).

    factory — ФАБРИКА корутины (вызывается заново на каждую попытку): одну и ту же
    корутину нельзя await-ить дважды, поэтому передаём именно фабрику, а не готовую
    корутину.

    Обрабатываем здесь ТОЛЬКО 429 — остальные исключения пробрасываем без изменений,
    их разбирает вызывающий код (fallback на текст при битом file_id, best-effort
    при блокировке бота пользователем). После исчерпания повторов TelegramRetryAfter
    тоже пробрасывается — решение, что делать с не доставленным сообщением, за
    вызывающим (обычно: залогировать и продолжить).
    """
    for attempt in range(retries + 1):
        try:
            return await factory()
        except TelegramRetryAfter as exc:
            if attempt == retries:
                raise
            await asyncio.sleep(exc.retry_after)
    # Недостижимо: цикл либо вернёт результат, либо пробросит исключение.
    raise AssertionError("with_flood_retry: цикл завершился без результата")
