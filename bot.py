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
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

import config
from database.db import close_pool, create_pool
from handlers import matching, premium, registration, start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    """
    Глобальный перехват необработанных исключений в хендлерах.

    Без него падение любого хендлера тонет в общем логе aiogram, а пользователь
    видит «зависание». Логируем с трейсбеком (для наблюдаемости) и гасим ошибку,
    чтобы один битый апдейт не ронял обработку остальных.
    """
    logger.exception("Ошибка при обработке апдейта: %s", event.exception)
    return True


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
    # Секреты валидируются здесь (config бросит понятную ошибку, если их нет)
    bot_token = config.get_bot_token()
    database_url = config.get_database_url()

    # Создаём пул соединений с БД и таблицы
    await create_pool(database_url)
    logger.info("Подключение к базе данных установлено, таблицы готовы.")

    # FSM-хранилище в памяти (по требованию ТЗ)
    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

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
