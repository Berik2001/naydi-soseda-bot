# -*- coding: utf-8 -*-
"""Тесты чистых функций валидации и бизнес-правил (validators.py)."""

import pytest

from validators import (
    ABOUT_MAX_LEN,
    BUDGET_MAX,
    BUDGET_MIN,
    is_valid_about,
    parse_budget,
)


# ---------------------- parse_budget ----------------------

def test_parse_budget_simple():
    assert parse_budget("100000") == 100000


def test_parse_budget_with_spaces():
    # Пробелы между цифрами должны убираться
    assert parse_budget("100 000") == 100000
    assert parse_budget(" 1 0 0 0 0 0 ") == 100000


@pytest.mark.parametrize("text,expected", [
    ("до 100000", 100000),
    ("до 50000", 50000),
    ("примерно 120000", 120000),
    ("100 000 тг", 100000),
    ("бюджет 75000 тенге", 75000),
])
def test_parse_budget_extracts_from_text(text, expected):
    # Число извлекается из произвольного текста
    assert parse_budget(text) == expected


def test_parse_budget_min_boundary():
    assert parse_budget(str(BUDGET_MIN)) == BUDGET_MIN


def test_parse_budget_max_boundary():
    assert parse_budget(str(BUDGET_MAX)) == BUDGET_MAX


def test_parse_budget_below_min_rejected():
    assert parse_budget("9999") is None
    assert parse_budget("0") is None


def test_parse_budget_above_max_rejected():
    assert parse_budget(str(BUDGET_MAX + 1)) is None


@pytest.mark.parametrize("bad", ["", "abc", "сто тысяч", "до пяти тысяч", "тг"])
def test_parse_budget_no_number_rejected(bad):
    # Нет извлекаемого числа -> None
    assert parse_budget(bad) is None


@pytest.mark.parametrize("bad", ["100к", "до 5000", "9 999", "5000000000"])
def test_parse_budget_out_of_range_rejected(bad):
    # Число есть, но вне диапазона (100к->100, до 5000->5000, 9999<min, огромное>max)
    assert parse_budget(bad) is None


def test_parse_budget_none_input():
    assert parse_budget(None) is None


# ---------------------- is_valid_about ----------------------

def test_about_within_limit():
    assert is_valid_about("Тихая, учусь на 3 курсе") is True


def test_about_empty_is_valid():
    assert is_valid_about("") is True


def test_about_exactly_at_limit():
    assert is_valid_about("a" * ABOUT_MAX_LEN) is True


def test_about_over_limit_rejected():
    assert is_valid_about("a" * (ABOUT_MAX_LEN + 1)) is False
