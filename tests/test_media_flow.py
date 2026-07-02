# -*- coding: utf-8 -*-
"""Тесты единого сбора медиа (media_flow) — фиксируют поведение после дедупликации."""

import asyncio

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

import media_flow  # noqa: E402  (после importorskip)


def _run(coro):
    return asyncio.run(coro)


class _State:
    """Мини-замена FSMContext поверх словаря."""

    def __init__(self, data=None):
        self._d = dict(data or {})

    async def get_data(self):
        return dict(self._d)

    async def update_data(self, **kw):
        self._d.update(kw)


class _Photo:
    def __init__(self, file_id):
        self.file_id = file_id


class _Chat:
    id = 123


class _Message:
    def __init__(self):
        self.chat = _Chat()
        # Telegram шлёт несколько размеров; берётся последний (самый большой)
        self.photo = [_Photo("small"), _Photo("big")]
        self.video = _Photo("vid")
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append(args)


@pytest.fixture(autouse=True)
def _no_done_button(monkeypatch):
    # Кнопку «Готово» (asyncio-таск) в юнит-тестах не дёргаем
    monkeypatch.setattr(media_flow, "schedule_done_button", lambda *a, **k: None)


def test_collect_album_photo_appends_biggest():
    st = _State()
    _run(media_flow.collect_album_photo(
        _Message(), st, list_key="apartment_photos", done_action="x", max_count=10))
    assert st._d["apartment_photos"] == ["big"]


def test_collect_album_photo_respects_max():
    st = _State({"apartment_photos": ["a", "b"]})
    _run(media_flow.collect_album_photo(
        _Message(), st, list_key="apartment_photos", done_action="x", max_count=2))
    assert st._d["apartment_photos"] == ["a", "b"]  # сверх лимита не добавили


def test_collect_profile_photo_appends_and_sets_type():
    st = _State()
    _run(media_flow.collect_profile_photo(
        _Message(), st, list_key="profile_media", type_key="profile_media_type",
        done_action="x", max_count=2))
    assert st._d["profile_media"] == ["big"]
    assert st._d["profile_media_type"] == "photo"


def test_collect_profile_photo_rejected_after_video():
    st = _State({"profile_media_type": "video", "profile_media": ["v"]})
    msg = _Message()
    _run(media_flow.collect_profile_photo(
        msg, st, list_key="profile_media", type_key="profile_media_type",
        done_action="x", max_count=2))
    assert st._d["profile_media"] == ["v"]   # фото не примешалось к видео
    assert msg.answers                        # показано предупреждение


def test_collect_profile_video_sets():
    st = _State()
    _run(media_flow.collect_profile_video(
        _Message(), st, list_key="profile_media", type_key="profile_media_type",
        done_action="x"))
    assert st._d["profile_media"] == ["vid"]
    assert st._d["profile_media_type"] == "video"


def test_collect_profile_video_rejected_after_photo():
    st = _State({"profile_media_type": "photo", "profile_media": ["p"]})
    msg = _Message()
    _run(media_flow.collect_profile_video(
        msg, st, list_key="profile_media", type_key="profile_media_type",
        done_action="x"))
    assert st._d["profile_media"] == ["p"]   # видео не примешалось к фото
    assert msg.answers
