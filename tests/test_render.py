# -*- coding: utf-8 -*-
"""Тесты устойчивости рендера карточки к «битым» file_id (render._render)."""

import asyncio

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

from handlers.render import _render  # noqa: E402  (после importorskip)


def _run(coro):
    return asyncio.run(coro)


class _Recorder:
    """Собирает вызовы отправки; можно заставить фото/видео/альбом падать."""

    def __init__(self, fail=()):
        self.fail = set(fail)          # какие способы отправки «ломаются»
        self.texts = []                # доставленные текстовые сообщения
        self.photos = []               # успешно отправленные фото
        self.videos = []
        self.albums = []

    async def send_text(self, t, m):
        self.texts.append(t)

    async def send_photo(self, f, c, m):
        if "photo" in self.fail:
            raise RuntimeError("bad file_id")
        self.photos.append(f)

    async def send_video(self, f, c, m):
        if "video" in self.fail:
            raise RuntimeError("bad file_id")
        self.videos.append(f)

    async def send_album(self, a):
        if "album" in self.fail:
            raise RuntimeError("bad file_id")
        self.albums.append(a)

    async def render(self, user, card="CARD", markup="KB"):
        await _render(
            user, card, markup,
            send_text=self.send_text, send_photo=self.send_photo,
            send_video=self.send_video, send_album=self.send_album,
        )


def _seeker_photos(files):
    return {"role": "seeker", "profile_media": files, "profile_media_type": "photo"}


def test_broken_album_still_delivers_card_text():
    # Альбом падает целиком → фото шлём по одному, но текст+кнопки доходят
    rec = _Recorder(fail=("album",))
    _run(rec.render(_seeker_photos(["a", "b"])))
    assert rec.texts == ["CARD"]
    assert rec.photos == ["a", "b"]      # уцелевшие фото отправлены поштучно


def test_broken_album_and_broken_photos_still_delivers_text():
    # И альбом, и поштучная отправка падают → пользователь всё равно видит карточку
    rec = _Recorder(fail=("album", "photo"))
    _run(rec.render(_seeker_photos(["a", "b"])))
    assert rec.texts == ["CARD"]
    assert rec.photos == []


def test_broken_single_photo_falls_back_to_text():
    rec = _Recorder(fail=("photo",))
    _run(rec.render(_seeker_photos(["a"])))
    assert rec.texts == ["CARD"]


def test_broken_video_falls_back_to_text():
    rec = _Recorder(fail=("video",))
    _run(rec.render({"role": "seeker", "profile_media": ["v"],
                     "profile_media_type": "video"}))
    assert rec.texts == ["CARD"]


def test_healthy_album_sends_photos_and_text_once():
    rec = _Recorder()
    _run(rec.render(_seeker_photos(["a", "b"])))
    assert len(rec.albums) == 1
    assert rec.texts == ["CARD"]
