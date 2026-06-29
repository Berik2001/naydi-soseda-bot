# -*- coding: utf-8 -*-
"""
SQL-схема базы данных.
Таблицы создаются при старте бота функцией init_db() в db.py.
"""

# Таблица анкет пользователей
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    username        TEXT,
    full_name       TEXT,
    gender          TEXT,
    goal            TEXT,
    preferred_gender TEXT,
    city            TEXT,
    district        TEXT,
    budget          INTEGER,
    move_in         TEXT,
    smoking         TEXT,
    pets            TEXT,
    occupation      TEXT,
    photo_file_id   TEXT,
    about           TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    is_premium      BOOLEAN DEFAULT FALSE,
    premium_until   TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);
"""

# Кого пользователь уже просмотрел (чтобы не показывать повторно)
CREATE_VIEWS = """
CREATE TABLE IF NOT EXISTS views (
    id          SERIAL PRIMARY KEY,
    viewer_id   BIGINT NOT NULL,
    viewed_id   BIGINT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (viewer_id, viewed_id)
);
"""

# Лайки и супер-лайки (для определения взаимного мэтча)
CREATE_LIKES = """
CREATE TABLE IF NOT EXISTS likes (
    id          SERIAL PRIMARY KEY,
    from_id     BIGINT NOT NULL,
    to_id       BIGINT NOT NULL,
    is_super    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (from_id, to_id)
);
"""

ALL_TABLES = [CREATE_USERS, CREATE_VIEWS, CREATE_LIKES]

# Идемпотентные миграции — применяются при каждом старте (ADD COLUMN IF NOT EXISTS).
# Позволяют доезжать изменениям схемы на уже существующую БД без ручного ALTER.
MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP",
]
