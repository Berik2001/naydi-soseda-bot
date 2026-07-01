# -*- coding: utf-8 -*-
"""Тесты форматирования и сборки карточки анкеты (texts.py)."""

import texts


# ---------------------- format_budget ----------------------

def test_format_budget_groups_thousands():
    assert texts.format_budget(100000) == "100 000 тг"


def test_format_budget_million():
    assert texts.format_budget(1500000) == "1 500 000 тг"


def test_format_budget_small():
    assert texts.format_budget(10000) == "10 000 тг"


# ---------------------- profile_card ----------------------

def _sample_user(**overrides):
    """Базовая анкета для тестов карточки."""
    user = {
        "full_name": "Айгерим",
        "gender": "female",
        "city": "Алматы",
        "district": "Бостандык",
        "goal": "🔍 Ищу комнату/квартиру",
        "budget": 120000,
        "move_in": "🔥 Срочно, сейчас",
        "smoking": "Нет",
        "pets": "❌ Нет",
        "occupation": "🎓 Студент/ка",
        "about": "Тихая, дома редко",
    }
    user.update(overrides)
    return user


def test_profile_card_contains_key_fields():
    card = texts.profile_card(_sample_user())
    assert "Айгерим" in card
    assert "👩 Девушка" in card          # gender развёрнут из ключа
    assert "Алматы, Бостандык" in card
    assert "120 000 тг" in card          # бюджет отформатирован
    assert "Тихая, дома редко" in card


def test_profile_card_handles_missing_about():
    card = texts.profile_card(_sample_user(about=None))
    assert "«—»" in card  # пустое «о себе» заменяется прочерком


def test_profile_card_handles_missing_name():
    card = texts.profile_card(_sample_user(full_name=None))
    assert "Без имени" in card


def test_profile_card_male_gender():
    card = texts.profile_card(_sample_user(gender="male"))
    assert "👨 Парень" in card


def test_profile_card_budget_shows_up_to():
    """Бюджет ищущего показывается как «до X»."""
    card = texts.profile_card(_sample_user(budget=10000))
    assert "💰 до 10 000 тг" in card


def test_profile_card_goal_on_top_no_duplicate_emojis():
    """Цель сверху, без дублирующихся префиксов-эмодзи."""
    user = _sample_user(
        goal="🔍 Нет жилья — ищу куда подселиться",
        move_in="📅 В течение 2 недель",
        occupation="💼 Работаю",
    )
    card = texts.profile_card(user)
    # цель — первая строка карточки
    assert card.startswith("🔍 Нет жилья — ищу куда подселиться")
    # нет двойных эмодзи
    assert "📅 📅" not in card
    assert "💼 💼" not in card
    assert "🎯" not in card        # старый префикс цели убран
    assert "👤 Моя анкета" not in card


def test_profile_card_minimal_have_place():
    """Минимальная анкета «есть жильё»: пол + город, остальное пусто."""
    user = {
        "full_name": "Хост",
        "gender": "male",
        "city": "Алматы",
        "district": None,
        "goal": "🤝 Есть жильё, ищу с кем жить",
        "budget": None,
        "move_in": None,
        "smoking": None,
        "pets": None,
        "occupation": None,
        "about": None,
    }
    card = texts.profile_card(user)
    assert "Хост" in card
    assert "📍 Алматы" in card
    assert "None" not in card      # пустые поля не протекают как "None"
    assert "тг" not in card        # строки бюджета нет


def test_profile_card_registration_data_without_habit_keys():
    """
    Регресс: после регистрации данные FSM не содержат ключей smoking/pets
    (эти шаги убраны). Карточка должна собираться без KeyError.
    """
    data = {
        "full_name": "Серик",
        "gender": "male",
        "goal": "🔍 Нет жилья — ищу куда подселиться",
        "role": "seeker",
        "city": "Астана",
        "district": "Есиль",
        "budget": 30000,
        "move_in": "📅 В течение 2 недель",
        "occupation": "🏠 Фриланс",
        "about": "Я не курю и не пью",
    }
    card = texts.profile_card(data)  # не должно бросать KeyError
    assert "Серик" in card
    assert "Астана, Есиль" in card
    assert "💰 до 30 000 тг" in card
    assert "Я не курю и не пью" in card


def test_listing_card_provider():
    """Карточка объявления (сдаёт жильё)."""
    user = {
        "role": "provider",
        "full_name": "Хост",
        "gender": "male",
        "city": "Астана",
        "district": "Есиль",
        "preferred_gender": "female",
        "budget": 150000,
        "about": "2 комнаты, есть мебель",
    }
    card = texts.listing_card(user)
    assert card.startswith("🏠 Есть жильё — ищу соседа")
    assert "Астана, Есиль" in card
    assert "150 000 тг/мес" in card
    assert "2 комнаты, есть мебель" in card
    # Строка «Сожитель» убрана из карточки
    assert "Сожитель" not in card


def test_user_card_dispatch_by_role():
    """user_card выбирает объявление для provider и анкету для seeker."""
    provider = {
        "role": "provider", "full_name": "Х", "gender": "male", "city": "Алматы",
        "district": None, "preferred_gender": "any", "budget": 120000, "about": None,
    }
    assert texts.user_card(provider).startswith("🏠 Есть жильё — ищу соседа")


# ---------------------- match_message / user_link ----------------------

def test_user_link_is_clickable_by_id():
    link = texts.user_link("Аружан", 123456)
    assert link == '<a href="tg://user?id=123456">Аружан</a>'


def test_user_link_escapes_html():
    # Спецсимволы в имени экранируются, чтобы не сломать HTML-разметку
    link = texts.user_link("A<b>&", 1)
    assert "<b>" not in link.replace('<a href="tg://user?id=1">', "")
    assert "&lt;b&gt;&amp;" in link


def test_match_message_name_is_link_without_username():
    msg = texts.match_message("Аружан", None, 555)
    assert '<a href="tg://user?id=555">Аружан</a>' in msg
    assert "нет username" not in msg
    assert "У вас мэтч" in msg


def test_match_message_with_username():
    msg = texts.match_message("Аружан", "aruzhan", 555)
    assert "@aruzhan" in msg
    assert '<a href="tg://user?id=555">Аружан</a>' in msg


# ---------------------- incoming_like_header ----------------------

def test_incoming_like_header_like():
    header = texts.incoming_like_header(is_super=False)
    assert "лайк" in header.lower() or "понрав" in header.lower()
    assert "СУПЕР" not in header


def test_incoming_like_header_superlike():
    header = texts.incoming_like_header(is_super=True)
    assert "СУПЕР" in header
