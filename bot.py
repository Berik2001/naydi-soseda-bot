# -*- coding: utf-8 -*-
"""
Точка входа бота для поиска сожителей в Казахстане.

Запуск:  python bot.py
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

import config
from database.pool import close_pool, create_pool
from handlers import matching, premium, registration, start

logging.basicConfig(
    level=getattr(logging, config.get_log_level(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """
    Включить трекинг ошибок Sentry, если задан SENTRY_DSN.

    LoggingIntegration сам ловит logger.error/exception (в т.ч. глобальный
    on_error) и шлёт в Sentry со стектрейсом. Импорт ленивый — зависимость не
    нужна, пока DSN не задан; сбой инициализации не роняет бота.
    """
    dsn = config.get_sentry_dsn()
    if not dsn:
        logger.info("Sentry: выключен (SENTRY_DSN не задан).")
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=config.get_environment(),
            traces_sample_rate=0.0,  # трейсинг производительности не нужен боту
        )
        logger.info("Sentry: включён.")
    except Exception as exc:  # noqa: BLE001 — наблюдаемость не должна ронять прод
        logger.error("Sentry не инициализировался (%s) — продолжаю без него.", exc)


async def on_error(event: ErrorEvent) -> bool:
    """
    Глобальный перехват необработанных исключений в хендлерах.

    Без него падение любого хендлера тонет в общем логе aiogram, а пользователь
    видит «зависание». Логируем с трейсбеком (для наблюдаемости) и гасим ошибку,
    чтобы один битый апдейт не ронял обработку остальных.
    """
    logger.exception("Ошибка при обработке апдейта: %s", event.exception)
    return True


def build_storage() -> BaseStorage:
    """
    Выбрать FSM-хранилище: Redis (если задан REDIS_URL) — состояние переживает
    рестарты и допускает горизонтальный масштаб; иначе MemoryStorage (состояние
    теряется при рестарте, только один инстанс). Импорт Redis — ленивый, чтобы
    зависимость не требовалась, пока REDIS_URL не задан.
    """
    redis_url = config.get_redis_url()
    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(redis_url)
            logger.info("FSM-хранилище: Redis.")
            return storage
        except Exception as exc:  # noqa: BLE001 — не роняем бота из-за кривого URL
            logger.error(
                "Не удалось инициализировать Redis (%s). Откат на MemoryStorage. "
                "Проверь REDIS_URL — нужна строка вида "
                "rediss://default:ПАРОЛЬ@host:6379 (не REST-URL https://...).",
                exc,
            )
    logger.info(
        "FSM-хранилище: в памяти. Для устойчивости к рестартам и масштаба "
        "задай REDIS_URL."
    )
    return MemoryStorage()


async def set_commands(bot: Bot) -> None:
    """
    Меню команд бота (кнопка «/» в Telegram).
    Показываем только «Моя анкета». Остальные команды
    (/start, /search, /pause, /resume, /help, /edit, /premium) работают,
    если ввести вручную, но в меню не отображаются.
    """
    commands = [
        BotCommand(command="profile", description="Моя анкета"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    # Наблюдаемость поднимаем первой — чтобы ловить и ошибки старта (БД и т.п.)
    init_sentry()

    # Секреты валидируются здесь (config бросит понятную ошибку, если их нет)
    bot_token = config.get_bot_token()
    database_url = config.get_database_url()

    # Создаём пул соединений с БД и таблицы
    await create_pool(database_url)
    logger.info("Подключение к базе данных установлено, таблицы готовы.")

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=build_storage())

    # Порядок важен: сначала роутеры с командами (start/matching/premium),
    # чтобы /profile, /start, /search и т.д. работали ДАЖЕ во время
    # регистрации. Иначе FSM-хендлеры регистрации перехватывают команды как
    # «неверный ввод». Регистрация — последней: её обработчики привязаны к
    # состояниям Form.* и ловят только «свои» сообщения.
    dp.include_router(start.router)
    dp.include_router(matching.router)
    dp.include_router(premium.router)
    dp.include_router(registration.router)

    # Глобальный перехват ошибок хендлеров (логирование + не роняем polling)
    dp.errors.register(on_error)

    await set_commands(bot)

    logger.info("Бот запущен. Ожидаю сообщения...")
    try:
        await dp.start_polling(bot)
    finally:
        await close_pool()
        await bot.session.close()
        logger.info("Бот остановлен, соединения закрыты.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход по сигналу остановки.")
