# -*- coding: utf-8 -*-
"""
Единый помощник отрисовки карточки с медиа.

Поддерживает:
- ищущий (seeker): до 2 фото или 1 видео (profile_media + profile_media_type);
- сдающий (provider): альбом фото квартиры (apartment_photos);
- запасной вариант: одиночное photo_file_id (старые анкеты).

Альбом (media group) не несёт inline-кнопок, поэтому при 2 фото кнопки
отправляются отдельным сообщением после альбома.
"""

from aiogram.types import InputMediaPhoto, Message


def _get(obj, key):
    """Достать поле и из dict (FSM data), и из asyncpg.Record; None если нет."""
    try:
        return obj[key]
    except (KeyError, IndexError):
        return None


async def send_media_card(message: Message, user, card_text: str, reply_markup=None) -> None:
    """Отправить карточку с медиа и (опционально) кнопками."""
    role = _get(user, "role")

    # Сдающий — альбом фото квартиры
    if role == "provider":
        photos = _get(user, "apartment_photos") or []
        if photos:
            await message.answer_media_group([InputMediaPhoto(media=f) for f in photos])
        await message.answer(card_text, reply_markup=reply_markup)
        return

    # Ищущий — до 2 фото или 1 видео
    media = _get(user, "profile_media") or []
    mtype = _get(user, "profile_media_type")

    if mtype == "video" and media:
        await message.answer_video(media[0], caption=card_text, reply_markup=reply_markup)
    elif mtype == "photo" and len(media) >= 2:
        await message.answer_media_group([InputMediaPhoto(media=f) for f in media])
        await message.answer(card_text, reply_markup=reply_markup)
    elif mtype == "photo" and len(media) == 1:
        await message.answer_photo(media[0], caption=card_text, reply_markup=reply_markup)
    elif _get(user, "photo_file_id"):
        # старые анкеты с одиночным фото
        await message.answer_photo(
            _get(user, "photo_file_id"), caption=card_text, reply_markup=reply_markup
        )
    else:
        await message.answer(card_text, reply_markup=reply_markup)
