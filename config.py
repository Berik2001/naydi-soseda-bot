# -*- coding: utf-8 -*-
"""
Единая точка конфигурации: секреты из окружения + настройки бота.

Раньше константы были размазаны по модулям (MAX_APARTMENT_PHOTOS дублировался
в registration.py и start.py, задержка кнопки и настройки премиума жили в своих
файлах, env читался прямо в bot.py). Теперь всё здесь — одно место правды.
"""

from __future__ import annotations  # поддержка "X | None" на Python 3.9

import os

from dotenv import load_dotenv

# Загружаем .env один раз при импорте конфига (идемпотентно).
load_dotenv()


# ====================== МЕДИА ======================

MAX_APARTMENT_PHOTOS = 10   # фото квартиры в объявлении (provider)
MAX_PROFILE_PHOTOS = 2      # фото профиля у ищущего (seeker)
DONE_BUTTON_DELAY = 0.8     # сек тишины после последнего фото → показать «Готово ✅»


# ====================== ПРЕМИУМ (Telegram Stars) ======================

PREMIUM_STARS = 150             # цена в Telegram Stars
PREMIUM_DAYS = 30               # срок действия в днях
PREMIUM_PAYLOAD = "premium_30d"  # идентификатор товара в payload инвойса


# ====================== СЕКРЕТЫ ИЗ ОКРУЖЕНИЯ ======================

def get_bot_token() -> str:
    """Токен бота из окружения (обязателен)."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в .env")
    return token


def get_database_url() -> str:
    """Строка подключения к БД из окружения (обязательна)."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Не задан DATABASE_URL в .env")
    return dsn
