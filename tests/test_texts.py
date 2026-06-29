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
        "budget": 120000,
        "move_in": "🔥 Срочно, сейчас",
        "smoking": "Нет",
        "pets": "❌ Нет",
        "schedule": "🦉 Сова",
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
