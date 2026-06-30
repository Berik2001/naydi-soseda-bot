# -*- coding: utf-8 -*-
"""
Точка входа бота для поиска сожителей в Казахстане.

Запуск:  python bot.py
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from dotenv import load_dotenv

from database.db import close_pool, create_pool
from handlers import matching, premium, registration, start

# Загружаем переменные окружения из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def set_commands(bot: Bot) -> None:
    """Меню команд бота (кнопка «/» в Telegram)."""
    commands = [
        BotCommand(command="start", description="Начало / регистрация"),
        BotCommand(command="profile", description="Моя анкета"),
        BotCommand(command="search", description="Найти сожителей"),
        BotCommand(command="pause", description="Скрыть анкету"),
        BotCommand(command="resume", description="Показать анкету"),
        BotCommand(command="help", description="Помощь"),
        # /edit и /premium временно скрыты из меню (редактирование — внутри /profile,
        # премиум пока бесплатный). Команды продолжают работать, если ввести вручную.
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в .env")
    if not DATABASE_URL:
        raise RuntimeError("Не задан DATABASE_URL в .env")

    # Создаём пул соединений с БД и таблицы
    await create_pool(DATABASE_URL)
    logger.info("Подключение к базе данных установлено, таблицы готовы.")

    # FSM-хранилище в памяти (по требованию ТЗ)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем роутеры. Порядок важен: сначала регистрация (FSM),
    # затем команды и мэтчинг.
    dp.include_router(registration.router)
    dp.include_router(start.router)
    dp.include_router(matching.router)
    dp.include_router(premium.router)

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
