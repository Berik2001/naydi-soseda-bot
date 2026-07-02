# -*- coding: utf-8 -*-
"""Тесты целостности списка версионных миграций (database.models.MIGRATIONS)."""

from database.models import MIGRATIONS


def test_migrations_are_version_sql_tuples():
    for item in MIGRATIONS:
        assert isinstance(item, tuple) and len(item) == 2
        version, sql = item
        assert isinstance(version, int)
        assert isinstance(sql, str) and sql.strip()


def test_migration_versions_unique():
    versions = [v for v, _ in MIGRATIONS]
    assert len(versions) == len(set(versions)), "версии миграций должны быть уникальны"


def test_migration_versions_strictly_increasing():
    versions = [v for v, _ in MIGRATIONS]
    assert versions == sorted(versions)
    assert all(b > a for a, b in zip(versions, versions[1:])), "версии только растут"
