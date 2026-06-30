# -*- coding: utf-8 -*-
"""
Чистые функции валидации и бизнес-правил.

Вынесены отдельно от хендлеров, чтобы их можно было покрыть unit-тестами
без запуска Telegram-бота и без подключения к базе данных.
"""

from __future__ import annotations  # поддержка "X | None" на Python 3.9

import re

# Границы бюджета (тенге в месяц)
BUDGET_MIN = 10_000
BUDGET_MAX = 5_000_000

# Максимальная длина текста «о себе» / описания жилья
ABOUT_MAX_LEN = 2000

# Допустимая разница в бюджете при мэтчинге (±30%)
BUDGET_TOLERANCE = 0.3


def parse_budget(raw: str) -> int | None:
    """
    Разобрать бюджет из пользовательского ввода.

    Извлекает число из строки, игнорируя любой текст и разделители:
    - "100000"        -> 100000
    - "до 100000"     -> 100000
    - "100 000 тг"    -> 100000
    - "примерно 50000"-> 50000

    Значение должно быть в диапазоне [BUDGET_MIN, BUDGET_MAX].
    Возвращает число при успехе или None, если число не найдено / вне диапазона.
    """
    if raw is None:
        return None
    # Оставляем только цифры (убираем "до", пробелы, "тг", знаки и пр.)
    cleaned = re.sub(r"\D", "", raw)
    if not cleaned:
        return None
    amount = int(cleaned)
    if amount < BUDGET_MIN or amount > BUDGET_MAX:
        return None
    return amount


def is_valid_about(text: str) -> bool:
    """Проверить, что текст «о себе» не длиннее лимита."""
    return len(text) <= ABOUT_MAX_LEN


def budget_range(budget: int) -> tuple[int, int]:
    """
    Вернуть диапазон допустимых бюджетов кандидата для мэтчинга (±30%).
    Например, для 100000 -> (70000, 130000).
    """
    budget = budget or 0
    low = int(budget * (1 - BUDGET_TOLERANCE))
    high = int(budget * (1 + BUDGET_TOLERANCE))
    return low, high
