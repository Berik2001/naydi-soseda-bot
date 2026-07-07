# -*- coding: utf-8 -*-
"""Тесты админ-панели: фильтр доступа IsAdmin и форматирование статистики."""

import asyncio

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

from handlers.admin import IsAdmin, _format_stats  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _User:
    def __init__(self, uid):
        self.id = uid


class _Msg:
    def __init__(self, uid):
        self.from_user = _User(uid) if uid is not None else None


def test_is_admin_allows_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "555")
    assert _run(IsAdmin()(_Msg(555))) is True


def test_is_admin_blocks_others(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "555")
    assert _run(IsAdmin()(_Msg(999))) is False


def test_is_admin_blocks_no_user(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "555")
    assert _run(IsAdmin()(_Msg(None))) is False


def test_format_stats_contains_key_numbers():
    overview = {
        "total": 10, "active": 8, "seekers": 6, "providers": 4, "premium": 2,
        "new_24h": 3, "new_7d": 7, "likes": 20, "views": 50, "matches": 5,
    }
    cities = [{"city": "Астана", "n": 6}, {"city": "Алматы", "n": 4}]
    text = _format_stats(overview, cities)
    assert "Всего анкет: <b>10</b>" in text
    assert "Мэтчей: <b>5</b>" in text
    assert "Астана — 6" in text


def test_format_stats_escapes_city_html():
    overview = {
        "total": 1, "active": 1, "seekers": 1, "providers": 0, "premium": 0,
        "new_24h": 0, "new_7d": 0, "likes": 0, "views": 0, "matches": 0,
    }
    cities = [{"city": "<b>hack</b>", "n": 1}]
    text = _format_stats(overview, cities)
    assert "&lt;b&gt;hack&lt;/b&gt;" in text  # экранировано, не сырой HTML


def test_match_kb_shows_delete_only_for_admin():
    from keyboards import inline
    admin_cbs = {b.callback_data
                 for row in inline.match_kb(5, is_admin=True).inline_keyboard for b in row}
    assert "admindel:5" in admin_cbs                    # админ видит кнопку удаления
    plain_cbs = {b.callback_data
                 for row in inline.match_kb(5).inline_keyboard for b in row}
    assert "admindel:5" not in plain_cbs                # обычный пользователь — нет


def test_admin_delete_confirm_kb_has_both_choices():
    from keyboards import inline
    cbs = {b.callback_data
           for row in inline.admin_delete_confirm_kb(7).inline_keyboard for b in row}
    assert cbs == {"admindelok:7", "admindelno:7"}
