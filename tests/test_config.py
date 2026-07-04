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


def test_command_timeout_default_none(monkeypatch):
    monkeypatch.delenv("DB_COMMAND_TIMEOUT", raising=False)
    assert config.get_command_timeout() is None


def test_command_timeout_empty_is_none(monkeypatch):
    monkeypatch.setenv("DB_COMMAND_TIMEOUT", "")
    assert config.get_command_timeout() is None


def test_command_timeout_parsed_as_float(monkeypatch):
    monkeypatch.setenv("DB_COMMAND_TIMEOUT", "30")
    assert config.get_command_timeout() == 30.0


def test_int_env_fallback_and_parse(monkeypatch):
    monkeypatch.delenv("DB_POOL_MAX_SIZE", raising=False)
    assert config._int_env("DB_POOL_MAX_SIZE", 5) == 5
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "20")
    assert config._int_env("DB_POOL_MAX_SIZE", 5) == 20


# ---------------------- чистка просмотров ----------------------

def test_views_cleanup_defaults_are_sane_ints():
    # Дефолты по умолчанию (env не задан в тестах): хранение 60 дн, прогон раз в сутки.
    assert isinstance(config.VIEWS_RETENTION_DAYS, int)
    assert isinstance(config.VIEWS_CLEANUP_INTERVAL_HOURS, int)
    assert config.VIEWS_RETENTION_DAYS == 60
    assert config.VIEWS_CLEANUP_INTERVAL_HOURS == 24


# ---------------------- премиум и лимит лайков ----------------------

def test_premium_price_is_50_stars():
    assert config.PREMIUM_STARS == 50


def test_free_daily_likes_default_100():
    assert config.FREE_DAILY_LIKES == 100


# ---------------------- наблюдаемость ----------------------

def test_sentry_dsn_default_none(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert config.get_sentry_dsn() is None


def test_sentry_dsn_present(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://k@o.ingest.sentry.io/1")
    assert config.get_sentry_dsn() == "https://k@o.ingest.sentry.io/1"


def test_log_level_default_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert config.get_log_level() == "INFO"


def test_log_level_uppercased(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert config.get_log_level() == "DEBUG"


def test_environment_default_production(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    assert config.get_environment() == "production"
