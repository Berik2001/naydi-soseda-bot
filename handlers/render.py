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

# Короткая подпись для отдельного сообщения с кнопками (под альбомом, у
# которого собственных inline-кнопок быть не может).
ACTIONS_LABEL = "👇 Действия:"


def _get(obj, key):
    """Достать поле и из dict (FSM data), и из asyncpg.Record; None если нет."""
    try:
        return obj[key]
    except (KeyError, IndexError):
        return None


async def send_media_card(message: Message, user, card_text: str, reply_markup=None) -> None:
    """
    Отправить карточку с медиа и (опционально) кнопками.

    Правила отображения:
    - 2–10 фото → media group (альбом): Telegram показывает их компактной
      сеткой, как в каналах объявлений. Кнопки/текст идут отдельным сообщением,
      т.к. у альбома не может быть inline-клавиатуры.
    - ровно 1 фото → обычное фото с подписью (одиночное фото Telegram всегда
      показывает крупно — это его поведение, через Bot API не уменьшить).
    - видео → видео с подписью.
    """
    role = _get(user, "role")

    # Источник медиа зависит от роли
    if role == "provider":
        media = list(_get(user, "apartment_photos") or [])
        mtype = "photo"
    else:
        media = list(_get(user, "profile_media") or [])
        mtype = _get(user, "profile_media_type")

    # Запасной вариант для старых анкет с одиночным photo_file_id
    if not media and _get(user, "photo_file_id"):
        media = [_get(user, "photo_file_id")]
        mtype = "photo"

    if mtype == "video" and media:
        await message.answer_video(media[0], caption=card_text, reply_markup=reply_markup)
    elif mtype == "photo" and len(media) >= 2:
        # Альбом: текст карточки — подписью к первому фото (текст и фото вместе,
        # фото компактной сеткой). Кнопки у media group невозможны, поэтому
        # меню/действия отправляем отдельным коротким сообщением.
        album = []
        for i, f in enumerate(media[:10]):
            if i == 0:
                album.append(InputMediaPhoto(media=f, caption=card_text))
            else:
                album.append(InputMediaPhoto(media=f))
        await message.answer_media_group(album)
        if reply_markup is not None:
            await message.answer(ACTIONS_LABEL, reply_markup=reply_markup)
    elif mtype == "photo" and len(media) == 1:
        await message.answer_photo(media[0], caption=card_text, reply_markup=reply_markup)
    else:
        await message.answer(card_text, reply_markup=reply_markup)
