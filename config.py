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


# ====================== ПУЛ СОЕДИНЕНИЙ БД ======================
# По умолчанию asyncpg держит до 10 соединений. Supabase-пулер в session-mode
# пускает максимум ~15 клиентов, а при деплое Railway старый и новый контейнеры
# работают одновременно — 10+10 > 15 → новый контейнер падает (EMAXCONNSESSION).
# Боту long-polling столько не нужно: держим маленький пул, чтобы два контейнера
# при выкатке укладывались в лимит (5+5 < 15).
#
# Размеры вынесены в env, чтобы масштабировать без правки кода: при переходе на
# transaction-mode пулер Supabase (порт 6543, тысячи клиентов) можно поднять
# DB_POOL_MAX_SIZE.


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


DB_POOL_MIN_SIZE = _int_env("DB_POOL_MIN_SIZE", 1)
DB_POOL_MAX_SIZE = _int_env("DB_POOL_MAX_SIZE", 5)


# ====================== ЧИСТКА ПРОСМОТРОВ ======================
# Таблица views растёт на каждый свайп. Фоновая задача периодически удаляет
# старые записи, чтобы таблица не пухла бесконечно (и давно просмотренные анкеты
# со временем снова появлялись в ленте).

# Сколько дней хранить просмотры. 0 или меньше — чистку не запускать.
VIEWS_RETENTION_DAYS = _int_env("VIEWS_RETENTION_DAYS", 60)
# Как часто прогонять чистку, часов.
VIEWS_CLEANUP_INTERVAL_HOURS = _int_env("VIEWS_CLEANUP_INTERVAL_HOURS", 24)


def get_statement_cache_size() -> int | None:
    """
    Размер кэша prepared statements asyncpg.

    По умолчанию None — поведение asyncpg не меняем. При работе через
    transaction-mode пулер (pgbouncer/Supavisor) prepared statements ломаются,
    поэтому там нужно выставить DB_STATEMENT_CACHE_SIZE=0.
    """
    raw = os.getenv("DB_STATEMENT_CACHE_SIZE")
    return int(raw) if raw not in (None, "") else None


def get_command_timeout() -> float | None:
    """
    Таймаут выполнения одного запроса asyncpg, в секундах (по умолчанию None —
    без лимита, поведение не меняем).

    Зачем под нагрузкой: пул маленький (DB_POOL_MAX_SIZE), и один зависший
    запрос держит соединение, приближая исчерпание пула → отказ для всех.
    Таймаут обрывает такой запрос и возвращает слот в пул.

    Осторожно: слишком малое значение обрубит тяжёлые стартовые бэкфилл-миграции
    на большой таблице. Ставь с запасом (напр. 30–60).
    """
    raw = os.getenv("DB_COMMAND_TIMEOUT")
    return float(raw) if raw not in (None, "") else None


# ====================== ПРЕМИУМ (Telegram Stars) ======================

PREMIUM_STARS = 50              # цена в Telegram Stars (за PREMIUM_DAYS)
PREMIUM_DAYS = 30               # срок действия в днях
PREMIUM_PAYLOAD = "premium_30d"  # идентификатор товара в payload инвойса


# ====================== ЛИМИТ ЛАЙКОВ ======================
# Дневной лимит лайков для бесплатных пользователей (скользящие 24 часа).
# Премиум лимитом НЕ ограничивается. 0 или меньше — лимит выключен.
# Цель — не столько анти-спам (это уже закрыто throttling + дедупом лайков),
# сколько чтобы один человек не пролайкивал всех подряд, и как повод к премиуму.
FREE_DAILY_LIKES = _int_env("FREE_DAILY_LIKES", 100)


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


def get_redis_url() -> str | None:
    """
    Строка подключения к Redis для FSM-хранилища (опциональна).

    Если задана — состояние регистрации переживает рестарты бота и появляется
    возможность горизонтального масштаба. Если нет — используется MemoryStorage.
    """
    return os.getenv("REDIS_URL") or None


# ====================== НАБЛЮДАЕМОСТЬ ======================

def get_sentry_dsn() -> str | None:
    """DSN Sentry для трекинга ошибок (опционально). Нет — Sentry выключен."""
    return os.getenv("SENTRY_DSN") or None


def get_log_level() -> str:
    """Уровень логирования (INFO по умолчанию). Напр. DEBUG/WARNING/ERROR."""
    return (os.getenv("LOG_LEVEL") or "INFO").upper()


def get_environment() -> str:
    """Окружение для тегирования событий Sentry (production по умолчанию)."""
    return os.getenv("ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT") or "production"


# ====================== АДМИНИСТРАТОРЫ ======================

# ID владельца — дефолт, если не задан ADMIN_IDS (чтобы админка работала «из коробки»).
_DEFAULT_ADMIN_ID = 8459204194


def get_admin_ids() -> set[int]:
    """
    Telegram ID администраторов (доступ к /admin, /stats).

    Берём из env ADMIN_IDS (через запятую, напр. "111,222"). Если не задан —
    один владелец по умолчанию. Кривые значения игнорируем, чтобы опечатка в env
    не роняла старт.
    """
    raw = os.getenv("ADMIN_IDS")
    if not raw:
        return {_DEFAULT_ADMIN_ID}
    ids: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                continue
    return ids or {_DEFAULT_ADMIN_ID}
