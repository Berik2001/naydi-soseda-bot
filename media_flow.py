# -*- coding: utf-8 -*-
"""
Единый сбор медиа при загрузке (фото/видео/альбом) с «плавающей» кнопкой
«Готово ✅».

Раньше эта логика была написана дважды — в registration.py (шаги анкеты) и в
start.py (пересбор медиа при редактировании). Отличались только имена ключей
FSM-данных (apartment_photos/apt_photos, profile_media/new_media). Теперь оба
модуля зовут эти функции, а имена ключей передают параметрами.
"""

from __future__ import annotations  # поддержка "X | None" на Python 3.9

import asyncio

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import texts
from config import DONE_BUTTON_DELAY
from keyboards import inline


# ====================== PER-CHAT ЛОКИ ======================
# Сериализуют чтение-запись списка фото при конкурентной загрузке альбома
# (aiogram обрабатывает апдейты параллельно, handle_as_tasks=True). Лок свой на
# каждый чат — раньше был один глобальный на всех, и фото разных пользователей
# стояли в очереди друг за другом.
#
# Лок нужен только на короткое время загрузки альбома. Чтобы словарь не рос
# бесконечно (по entry на каждого, кто когда-либо грузил фото), записи чистятся:
# на завершении шага (см. cancel_done_button) и опортунистически при переполнении
# (свободные локи можно смело выбрасывать — при новой загрузке создастся заново).
_locks: dict = {}
_LOCK_CAP = 5000


def _lock_for(chat_id: int) -> asyncio.Lock:
    lock = _locks.get(chat_id)
    if lock is None:
        if len(_locks) >= _LOCK_CAP:
            for key in [k for k, v in _locks.items() if not v.locked()]:
                del _locks[key]
        lock = asyncio.Lock()
        _locks[chat_id] = lock
    return lock


# ====================== КНОПКА «ГОТОВО ✅» (DEBOUNCE) ======================
# При загрузке альбома фото приходят пачкой, поэтому кнопку показываем ОДИН раз —
# с паузой после последнего фото (иначе счётчик мигает: фото 1, фото 2, ...).
# Ключ — chat_id.
_done_tasks: dict = {}
_DONE_TASKS_CAP = 5000


def _prune_done_tasks() -> None:
    """Выбросить завершённые задачи, чтобы словарь не рос (брошенные загрузки)."""
    if len(_done_tasks) < _DONE_TASKS_CAP:
        return
    for key in [k for k, t in _done_tasks.items() if t.done()]:
        _done_tasks.pop(key, None)


async def _post_done_button(message: Message, state: FSMContext, action: str, key: str) -> None:
    """Удалить предыдущую кнопку и показать одну актуальную с финальным счётчиком."""
    data = await state.get_data()
    if key == "__video__":
        text = texts.VIDEO_PROGRESS
    else:
        n = len(data.get(key) or [])
        if n == 0:
            return
        text = texts.photos_progress(n)
    old_id = data.get("done_msg_id")
    if old_id:
        try:
            await message.bot.delete_message(message.chat.id, old_id)
        except Exception:  # noqa: BLE001 — сообщение могли удалить/его нет
            pass
    sent = await message.answer(text, reply_markup=inline.photos_done_kb(action))
    await state.update_data(done_msg_id=sent.message_id)


async def _delayed_done(message: Message, state: FSMContext, action: str, key: str) -> None:
    try:
        await asyncio.sleep(DONE_BUTTON_DELAY)
    except asyncio.CancelledError:
        return
    await _post_done_button(message, state, action, key)


def schedule_done_button(message: Message, state: FSMContext, action: str, key: str) -> None:
    """Показать кнопку «Готово ✅» один раз — через паузу после последнего фото."""
    chat_id = message.chat.id
    _prune_done_tasks()
    task = _done_tasks.get(chat_id)
    if task and not task.done():
        task.cancel()
    _done_tasks[chat_id] = asyncio.create_task(_delayed_done(message, state, action, key))


def cancel_done_button(chat_id: int) -> None:
    """
    Завершить шаг загрузки: отменить отложенную кнопку и освободить память —
    убрать запись задачи и per-chat лок (загрузка окончена, они больше не нужны).
    """
    task = _done_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()
    _locks.pop(chat_id, None)


# ====================== СБОР МЕДИА ======================

async def collect_album_photo(
    message: Message, state: FSMContext, *, list_key: str, done_action: str, max_count: int
) -> None:
    """
    Добавить фото в альбом (фото квартиры у provider). Лишние сверх max_count
    тихо игнорируем (без спама сообщениями). Затем — плавающая кнопка «Готово».
    """
    async with _lock_for(message.chat.id):
        data = await state.get_data()
        photos = list(data.get(list_key) or [])
        if len(photos) >= max_count:
            return  # больше не добавляем и кнопку не пересобираем
        photos.append(message.photo[-1].file_id)
        await state.update_data(**{list_key: photos})
    schedule_done_button(message, state, done_action, list_key)


async def collect_profile_photo(
    message: Message, state: FSMContext, *,
    list_key: str, type_key: str, done_action: str, max_count: int,
) -> None:
    """
    Добавить фото профиля (seeker: до max_count фото). Нельзя мешать с видео.
    """
    async with _lock_for(message.chat.id):
        data = await state.get_data()
        if data.get(type_key) == "video":
            await message.answer(texts.MEDIA_PHOTO_AFTER_VIDEO)
            return
        media = list(data.get(list_key) or [])
        if len(media) < max_count:
            media.append(message.photo[-1].file_id)
            await state.update_data(**{list_key: media, type_key: "photo"})
    schedule_done_button(message, state, done_action, list_key)


async def collect_profile_video(
    message: Message, state: FSMContext, *,
    list_key: str, type_key: str, done_action: str,
) -> None:
    """Задать видео профиля (seeker: ровно 1 видео). Нельзя мешать с фото."""
    data = await state.get_data()
    if data.get(list_key) and data.get(type_key) == "photo":
        await message.answer(texts.MEDIA_VIDEO_AFTER_PHOTO)
        return
    await state.update_data(**{list_key: [message.video.file_id], type_key: "video"})
    schedule_done_button(message, state, done_action, "__video__")
