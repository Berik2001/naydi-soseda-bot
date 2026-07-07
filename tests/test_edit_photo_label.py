# -*- coding: utf-8 -*-
"""Тесты динамической надписи кнопки выхода на шаге редактирования фото."""

import pytest

pytest.importorskip("aiogram")  # локально aiogram может не стоять; в CI есть

import texts  # noqa: E402
from handlers.start import _media_skip_label  # noqa: E402
from keyboards import inline  # noqa: E402


def test_label_keep_current_when_has_media():
    assert _media_skip_label(True) == texts.BTN_KEEP_CURRENT      # есть фото → «оставить текущее»


def test_label_skip_when_no_media():
    assert _media_skip_label(False) == texts.BTN_SKIP             # нет фото → «пропустить»


def test_photo_skip_kb_uses_custom_label():
    kb = inline.photo_skip_kb("photo:editcancel", texts.BTN_KEEP_CURRENT)
    btn = kb.inline_keyboard[0][0]
    assert btn.text == texts.BTN_KEEP_CURRENT
    assert btn.callback_data == "photo:editcancel"


def test_photo_skip_kb_default_label_for_registration():
    kb = inline.photo_skip_kb("photo:skip")                       # регистрация — без label
    assert kb.inline_keyboard[0][0].text == texts.BTN_SKIP
