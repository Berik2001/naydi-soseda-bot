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
    role            TEXT,
    apartment_photos TEXT[],
    profile_media       TEXT[],
    profile_media_type  TEXT,
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
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS apartment_photos TEXT[]",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_media TEXT[]",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_media_type TEXT",
    # Бэкфилл роли для уже существующих анкет (по тексту цели)
    "UPDATE users SET role = 'seeker' WHERE role IS NULL AND goal LIKE '%Ищу комнату%'",
    "UPDATE users SET role = 'provider' WHERE role IS NULL AND goal IS NOT NULL",
    # Пол сожителя теперь всегда равен собственному полу (парни с парнями,
    # девушки с девушками). Приводим старые анкеты, где стояло 'any' или иное.
    "UPDATE users SET preferred_gender = gender "
    "WHERE gender IS NOT NULL AND preferred_gender IS DISTINCT FROM gender",
    # Индексы под горячие запросы. get_next_candidate фильтрует users по
    # city+is_active; has_like/who_liked_me ищут likes по to_id (UNIQUE на
    # (from_id,to_id) такой поиск не покрывает); лента исключает по views.viewer_id.
    "CREATE INDEX IF NOT EXISTS idx_users_city_active ON users (city, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_likes_to_id ON likes (to_id)",
    "CREATE INDEX IF NOT EXISTS idx_views_viewer ON views (viewer_id)",
]
