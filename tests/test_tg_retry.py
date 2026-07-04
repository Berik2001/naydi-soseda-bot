# -*- coding: utf-8 -*-
"""Тесты устойчивой доставки: повтор при флуд-лимите Telegram (429)."""

import asyncio

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

from aiogram.exceptions import TelegramRetryAfter  # noqa: E402

import tg_retry  # noqa: E402
from tg_retry import with_flood_retry  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _Flood(TelegramRetryAfter):
    """Флуд-ошибка без конструирования TelegramMethod — для юнит-тестов.
    isinstance-совместима с TelegramRetryAfter, так что helper её ловит."""

    def __init__(self, retry_after: int = 1):
        Exception.__init__(self, "flood")
        self.retry_after = retry_after


@pytest.fixture
def no_sleep(monkeypatch):
    """Не спим по-настоящему; фиксируем, сколько раз и на сколько «ждали»."""
    slept = []

    async def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr(tg_retry.asyncio, "sleep", fake_sleep)
    return slept


def test_returns_result_without_retry(no_sleep):
    async def body():
        calls = []

        async def factory():
            calls.append(1)
            return "ok"

        result = await with_flood_retry(factory)
        return result, calls

    result, calls = _run(body())
    assert result == "ok"
    assert len(calls) == 1
    assert no_sleep == []  # не ждали — успех с первой попытки


def test_retries_after_flood_then_succeeds(no_sleep):
    async def body():
        calls = []

        async def factory():
            calls.append(1)
            if len(calls) == 1:
                raise _Flood(retry_after=3)
            return "ok"

        result = await with_flood_retry(factory, retries=2)
        return result, calls

    result, calls = _run(body())
    assert result == "ok"
    assert len(calls) == 2      # первая упала, вторая прошла
    assert no_sleep == [3]      # подождали ровно retry_after


def test_gives_up_and_reraises_after_exhausting(no_sleep):
    async def body():
        calls = []

        async def factory():
            calls.append(1)
            raise _Flood(retry_after=1)

        with pytest.raises(TelegramRetryAfter):
            await with_flood_retry(factory, retries=2)
        return calls

    calls = _run(body())
    assert len(calls) == 3      # 1 исходная + 2 повтора
    assert no_sleep == [1, 1]   # спали перед каждым повтором, но не после последней


def test_non_flood_error_propagates_without_retry(no_sleep):
    async def body():
        calls = []

        async def factory():
            calls.append(1)
            raise ValueError("bad file_id")

        with pytest.raises(ValueError):
            await with_flood_retry(factory)
        return calls

    calls = _run(body())
    assert len(calls) == 1      # не-429 не ретраим — сразу пробрасываем
    assert no_sleep == []
