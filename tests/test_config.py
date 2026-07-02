# -*- coding: utf-8 -*-
"""Тесты конфигурации (config.py)."""

import config


def test_statement_cache_size_default_none(monkeypatch):
    monkeypatch.delenv("DB_STATEMENT_CACHE_SIZE", raising=False)
    assert config.get_statement_cache_size() is None


def test_statement_cache_size_empty_is_none(monkeypatch):
    monkeypatch.setenv("DB_STATEMENT_CACHE_SIZE", "")
    assert config.get_statement_cache_size() is None


def test_statement_cache_size_zero_for_txn_pooler(monkeypatch):
    # Значение для transaction-mode пулера
    monkeypatch.setenv("DB_STATEMENT_CACHE_SIZE", "0")
    assert config.get_statement_cache_size() == 0


def test_int_env_fallback_and_parse(monkeypatch):
    monkeypatch.delenv("DB_POOL_MAX_SIZE", raising=False)
    assert config._int_env("DB_POOL_MAX_SIZE", 5) == 5
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "20")
    assert config._int_env("DB_POOL_MAX_SIZE", 5) == 20
