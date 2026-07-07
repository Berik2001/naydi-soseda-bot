# -*- coding: utf-8 -*-
"""Тесты обратной связи: ретрансляция админам, экранирование, антиспам-кулдаун."""

import asyncio

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

import config  # noqa: E402
import texts  # noqa: E402
from handlers import feedback  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _Clock:
    def __init__(self, start=1000.0):
        self.t = start

    def monotonic(self):
        return self.t


class _User:
    def __init__(self, uid, username="user", full_name="Имя"):
        self.id = uid
        self.username = username
        self.full_name = full_name


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


class _Msg:
    def __init__(self, uid, text, bot):
        self.from_user = _User(uid)
        self.text = text
        self.bot = bot
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)


class _State:
    def __init__(self):
        self.cleared = False

    async def clear(self):
        self.cleared = True


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    feedback._last_feedback.clear()
    monkeypatch.setattr(config, "FEEDBACK_COOLDOWN_SEC", 30)
    monkeypatch.setenv("ADMIN_IDS", "111,222")
    yield
    feedback._last_feedback.clear()


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(feedback, "time", c)
    return c


# ---------------------- ретрансляция ----------------------

def test_relays_to_all_admins_and_confirms(clock):
    bot = _Bot()
    msg = _Msg(5, "Есть идея!", bot)
    state = _State()
    _run(feedback.feedback_receive(msg, state))

    assert {c[0] for c in bot.sent} == {111, 222}          # оба админа получили
    assert "ID: <code>5</code>" in bot.sent[0][1]          # идентификация отправителя
    assert texts.FEEDBACK_SENT in msg.answers              # подтверждение пользователю
    assert state.cleared is True


def test_message_text_is_html_escaped(clock):
    bot = _Bot()
    msg = _Msg(7, "<b>взлом</b> & спам", bot)
    _run(feedback.feedback_receive(msg, _State()))
    body = bot.sent[0][1]
    assert "&lt;b&gt;взлом&lt;/b&gt; &amp; спам" in body   # не сырой HTML


def test_empty_rejected(clock):
    bot = _Bot()
    msg = _Msg(5, "   ", bot)
    state = _State()
    _run(feedback.feedback_receive(msg, state))
    assert bot.sent == []                                  # ничего не отправлено
    assert texts.FEEDBACK_EMPTY in msg.answers
    assert state.cleared is False                          # остаёмся в состоянии


def test_too_long_rejected(clock):
    bot = _Bot()
    msg = _Msg(5, "я" * (config.FEEDBACK_MAX_LEN + 1), bot)
    _run(feedback.feedback_receive(msg, _State()))
    assert bot.sent == []
    assert texts.FEEDBACK_TOO_LONG in msg.answers


# ---------------------- кулдаун ----------------------

def test_cooldown_blocks_second_then_allows(clock):
    state = _State()

    bot1 = _Bot()
    _run(feedback.feedback_receive(_Msg(5, "первое", bot1), state))
    assert len(bot1.sent) == 2                             # ушло обоим админам

    clock.t += 5                                           # спустя 5 сек — рано
    bot2 = _Bot()
    msg2 = _Msg(5, "второе", bot2)
    _run(feedback.feedback_receive(msg2, _State()))
    assert bot2.sent == []                                 # заблокировано кулдауном
    assert any("Подожди" in a for a in msg2.answers)

    clock.t += 30                                          # кулдаун прошёл
    bot3 = _Bot()
    _run(feedback.feedback_receive(_Msg(5, "третье", bot3), _State()))
    assert len(bot3.sent) == 2                             # снова доставлено


def test_profile_menu_has_support_button():
    from keyboards import inline
    for role in ("seeker", "provider", None):
        kb = inline.profile_menu_kb(role)
        cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
        assert "feedback:start" in cbs, role   # кнопка «Написать в поддержку» есть


def test_cooldown_is_per_user(clock):
    _run(feedback.feedback_receive(_Msg(5, "a", _Bot()), _State()))
    bot = _Bot()
    _run(feedback.feedback_receive(_Msg(9, "b", bot), _State()))  # другой юзер
    assert len(bot.sent) == 2                              # его не блокирует чужой кулдаун
