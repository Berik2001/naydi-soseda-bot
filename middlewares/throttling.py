# -*- coding: utf-8 -*-
"""
Anti-flood middleware: ограничивает частоту апдейтов на одного пользователя.

Зачем. aiogram обрабатывает апдейты параллельно (каждый — отдельная задача),
а каждый лайк/свайп/команда лезет в маленький пул БД (config.DB_POOL_MAX_SIZE).
Без ограничения один скрипт способен слать сотни апдейтов в секунду, исчерпать
пул и положить бота для всех. Middleware отсекает флуд ДО хендлера — дешёвая
проверка в памяти, без обращения к БД.

Два независимых предела на пользователя:
  • soft (RATE)  — минимальный интервал между «дорогими» действиями (коллбэки,
    команды, текст). Отсекает скрипт, но не мешает живому человеку.
  • hard (BURST) — максимум действий за окно WINDOW. Страховка от всплеска,
    когда soft-интервал обходят чередованием разных апдейтов.

Важные исключения (иначе сломаем легитимные сценарии):
  • Платежи (pre_checkout_query и successful_payment) НИКОГДА не throttl-ятся —
    потерять их = потерять деньги пользователя.
  • Загрузка медиа (фото/видео) не подпадает под soft-лимит: альбом из 10 фото
    Telegram присылает пачкой почти одновременно — soft-интервал выкинул бы 9 из
    10. Пачка всё ещё учитывается в hard-лимите (там запас под 1–2 альбома).

Хранилище — в памяти процесса (как _locks в media_flow): подходит для одного
инстанса. При горизонтальном масштабе состояние надо вынести в Redis.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update

# Дефолты подобраны так, чтобы не мешать человеку и резать скрипт:
#   RATE=0.4  → не чаще ~2.5 «дорогих» действий в секунду
#   BURST=30 / WINDOW=10s → до 3 действий/сек в среднем; пропускает 1–2 альбома
DEFAULT_RATE = 0.4      # сек между дорогими действиями (soft)
DEFAULT_BURST = 30      # макс. действий за окно (hard)
DEFAULT_WINDOW = 10.0   # длина окна hard-лимита, сек

# Чистка словарей, чтобы память не росла на брошенных пользователях
# (тот же приём, что и с _locks/_done_tasks в media_flow).
_GC_CAP = 10_000


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничитель частоты апдейтов на пользователя. Регистрируется как inner
    middleware диспетчера: ``dp.update.middleware(ThrottlingMiddleware())`` —
    к этому моменту aiogram уже проставил ``event_from_user`` в data."""

    def __init__(
        self,
        rate: float = DEFAULT_RATE,
        burst: int = DEFAULT_BURST,
        window: float = DEFAULT_WINDOW,
    ) -> None:
        self.rate = rate
        self.burst = burst
        self.window = window
        # user_id -> время последнего дорогого действия (для soft-лимита)
        self._last: dict[int, float] = {}
        # user_id -> список меток времени в текущем окне (для hard-лимита)
        self._hits: dict[int, list[float]] = {}

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        # Платежи не трогаем никогда — их потеря необратима.
        if event.pre_checkout_query is not None:
            return await handler(event, data)
        msg = event.message
        if msg is not None and msg.successful_payment is not None:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:  # системные апдейты без пользователя — пропускаем
            return await handler(event, data)

        uid = user.id
        now = time.monotonic()

        # Hard-лимит: скользящее окно на все апдейты пользователя.
        hits = [t for t in self._hits.get(uid, ()) if now - t < self.window]
        hits.append(now)
        self._hits[uid] = hits
        if len(hits) > self.burst:
            # Молча дропаем: отвечать под флудом = усиливать нагрузку.
            return None

        # Soft-лимит: минимальный интервал между дорогими действиями.
        # Загрузку медиа исключаем — альбом приходит легитимной пачкой.
        is_media = msg is not None and (msg.photo is not None or msg.video is not None)
        if not is_media:
            if now - self._last.get(uid, 0.0) < self.rate:
                return None
            self._last[uid] = now

        self._maybe_gc()
        return await handler(event, data)

    def _maybe_gc(self) -> None:
        """Выбросить пользователей без активности в текущем окне, если словари
        разрослись. Дешевле, чем таймер, и вызывается только при переполнении."""
        if len(self._hits) < _GC_CAP:
            return
        now = time.monotonic()
        stale = [u for u, ts in self._hits.items()
                 if not ts or now - ts[-1] >= self.window]
        for u in stale:
            self._hits.pop(u, None)
            self._last.pop(u, None)
