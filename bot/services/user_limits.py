"""Сервис для отслеживания лимитов генераций пользователей (SQLite)"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Пути к БД
_PROD_DIR = Path("/opt/photoshoot_ai")
_LOCAL_DIR = Path(__file__).parent.parent.parent
_PROD_DB = _PROD_DIR / "user_data.db"
_LOCAL_DB = _LOCAL_DIR / "user_data.db"

# Старые JSON-файлы (для миграции)
_PROD_JSON = _PROD_DIR / "user_generations.json"
_LOCAL_JSON = _LOCAL_DIR / "user_generations.json"

MAX_FREE_GENERATIONS = 1
ADMIN_ID = 91892537


def _get_db_path() -> Path:
    """Возвращает путь к файлу БД"""
    if _PROD_DIR.exists():
        return _PROD_DB
    return _LOCAL_DB


def _get_json_path() -> Path:
    """Возвращает путь к старому JSON-файлу (для миграции)"""
    if _PROD_DIR.exists():
        return _PROD_JSON
    return _LOCAL_JSON


def _get_conn() -> sqlite3.Connection:
    """Возвращает соединение с БД"""
    return sqlite3.connect(_get_db_path())


def init_db() -> None:
    """Инициализирует БД и мигрирует данные из JSON, если он существует"""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                generations INTEGER NOT NULL DEFAULT 0,
                last_photo_url TEXT,
                last_gender TEXT
            )
        """)

    # Миграция из JSON
    json_path = _get_json_path()
    if json_path.exists():
        _migrate_from_json(json_path)


def _migrate_from_json(json_path: Path) -> None:
    """Мигрирует данные из старого JSON-файла в SQLite"""
    try:
        data = json.loads(json_path.read_text())
    except Exception as e:
        logger.error(f"Failed to read JSON for migration: {e}")
        return

    migrated = 0
    with _get_conn() as conn:
        for user_key, user_data in data.items():
            try:
                user_id = int(user_key)
            except ValueError:
                continue

            # Поддержка старого формата (просто число)
            if isinstance(user_data, int):
                generations = user_data
                last_photo_url = None
                last_gender = None
            else:
                generations = user_data.get("generations", 0)
                last_photo_url = user_data.get("last_photo_url")
                last_gender = user_data.get("last_gender")

            conn.execute(
                """INSERT OR IGNORE INTO users
                   (user_id, generations, last_photo_url, last_gender)
                   VALUES (?, ?, ?, ?)""",
                (user_id, generations, last_photo_url, last_gender),
            )
            migrated += 1

    # Переименовываем JSON в .bak
    backup_path = json_path.with_suffix(".json.bak")
    json_path.rename(backup_path)
    logger.info(
        f"Migrated {migrated} users from JSON to SQLite. "
        f"Backup: {backup_path}"
    )


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID


def get_generations_count(user_id: int) -> int:
    """Возвращает количество использованных генераций"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT generations FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row[0] if row else 0


def get_remaining_generations(user_id: int) -> int:
    """Возвращает количество оставшихся генераций"""
    if is_admin(user_id):
        return -1  # Безлимит
    used = get_generations_count(user_id)
    return max(0, MAX_FREE_GENERATIONS - used)


def can_generate(user_id: int) -> bool:
    """Проверяет, может ли пользователь генерировать"""
    if is_admin(user_id):
        return True
    return get_remaining_generations(user_id) > 0


def increment_generations(user_id: int) -> None:
    """Увеличивает счётчик генераций пользователя"""
    if is_admin(user_id):
        return

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO users (user_id, generations)
               VALUES (?, 1)
               ON CONFLICT(user_id)
               DO UPDATE SET generations = generations + 1""",
            (user_id,),
        )
    count = get_generations_count(user_id)
    logger.info(f"User {user_id} generations: {count}/{MAX_FREE_GENERATIONS}")


def save_last_photo(user_id: int, photo_url: str, gender: str) -> None:
    """Сохраняет последнюю фотографию пользователя"""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO users (user_id, last_photo_url, last_gender)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id)
               DO UPDATE SET last_photo_url = ?, last_gender = ?""",
            (user_id, photo_url, gender, photo_url, gender),
        )
    logger.info(f"Saved last photo for user {user_id}")


def get_last_photo(user_id: int) -> tuple[str | None, str | None]:
    """Возвращает последнюю фотографию и пол пользователя"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT last_photo_url, last_gender FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row:
        return row[0], row[1]
    return None, None
