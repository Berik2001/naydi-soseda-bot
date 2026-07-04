# -*- coding: utf-8 -*-
"""Тесты anti-flood middleware: soft/hard лимиты и обязательные исключения."""

import asyncio

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

from middlewares import throttling  # noqa: E402
from middlewares.throttling import ThrottlingMiddleware  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _Clock:
    """Управляемое время вместо time.monotonic() — тесты не зависят от реальных пауз."""

    def __init__(self, start: float = 1000.0):
        self.t = start

    def monotonic(self) -> float:
        return self.t


class _User:
    def __init__(self, uid: int):
        self.id = uid


class _Msg:
    def __init__(self, *, photo=None, video=None, successful_payment=None):
        self.photo = photo
        self.video = video
        self.successful_payment = successful_payment


class _Update:
    def __init__(self, *, message=None, pre_checkout_query=None):
        self.message = message
        self.pre_checkout_query = pre_checkout_query


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(throttling, "time", c)
    return c


def _handler_factory():
    calls = []

    async def handler(event, data):
        calls.append(event)
        return "ok"

    return handler, calls


def _data(uid: int) -> dict:
    return {"event_from_user": _User(uid)}


def _text_update():
    return _Update(message=_Msg())  # текст: без фото/видео/платежа


def test_soft_limit_drops_rapid_actions(clock):
    mw = ThrottlingMiddleware(rate=0.4, burst=100)
    handler, calls = _handler_factory()

    assert _run(mw(handler, _text_update(), _data(1))) == "ok"     # 1-й проходит
    assert _run(mw(handler, _text_update(), _data(1))) is None     # слишком быстро → дроп
    clock.t += 0.5                                                 # переждали интервал
    assert _run(mw(handler, _text_update(), _data(1))) == "ok"     # снова проходит
    assert len(calls) == 2


def test_soft_limit_is_per_user(clock):
    mw = ThrottlingMiddleware(rate=0.4, burst=100)
    handler, calls = _handler_factory()
    assert _run(mw(handler, _text_update(), _data(1))) == "ok"
    assert _run(mw(handler, _text_update(), _data(2))) == "ok"     # другой юзер — не задет
    assert len(calls) == 2


def test_media_bypasses_soft_limit(clock):
    """Альбом из фото приходит пачкой в один момент — их нельзя резать soft-лимитом."""
    mw = ThrottlingMiddleware(rate=0.4, burst=100)
    handler, calls = _handler_factory()
    for _ in range(10):                                            # 10 фото, одно и то же время
        upd = _Update(message=_Msg(photo=["big"]))
        assert _run(mw(handler, upd, _data(1))) == "ok"
    assert len(calls) == 10


def test_hard_limit_blocks_burst(clock):
    mw = ThrottlingMiddleware(rate=0.0, burst=5, window=10.0)      # rate=0 → проверяем только burst
    handler, calls = _handler_factory()
    for _ in range(5):
        assert _run(mw(handler, _text_update(), _data(1))) == "ok"
    assert _run(mw(handler, _text_update(), _data(1))) is None     # 6-й за окно → дроп
    clock.t += 11.0                                               # окно прошло
    assert _run(mw(handler, _text_update(), _data(1))) == "ok"    # снова можно
    assert len(calls) == 6


def test_payments_never_throttled(clock):
    """pre_checkout и successful_payment должны проходить даже под флудом — их потеря необратима."""
    mw = ThrottlingMiddleware(rate=100.0, burst=1)                # предельно жёсткий throttle
    handler, calls = _handler_factory()

    # Забиваем лимиты обычным апдейтом
    _run(mw(handler, _text_update(), _data(1)))

    pre_checkout = _Update(pre_checkout_query=object())
    assert _run(mw(handler, pre_checkout, _data(1))) == "ok"

    paid = _Update(message=_Msg(successful_payment=object()))
    assert _run(mw(handler, paid, _data(1))) == "ok"


def test_no_user_passes_through(clock):
    mw = ThrottlingMiddleware()
    handler, calls = _handler_factory()
    assert _run(mw(handler, _text_update(), {})) == "ok"          # системный апдейт без юзера
