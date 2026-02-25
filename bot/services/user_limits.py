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

        # Миграция: добавляем колонку paid_credits
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN paid_credits INTEGER NOT NULL DEFAULT 0"
            )
            logger.info("Added paid_credits column to users table")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

        # Таблица истории платежей
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                package_id TEXT NOT NULL,
                credits INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                confirmed_at TEXT,
                payment_provider_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
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
    """Возвращает количество использованных бесплатных генераций"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT generations FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row[0] if row else 0


def get_paid_credits(user_id: int) -> int:
    """Возвращает количество оплаченных генераций"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT paid_credits FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row[0] if row else 0


def get_remaining_generations(user_id: int) -> int:
    """Возвращает общее количество оставшихся генераций (бесплатные + платные)"""
    if is_admin(user_id):
        return -1  # Безлимит
    used = get_generations_count(user_id)
    free_remaining = max(0, MAX_FREE_GENERATIONS - used)
    paid = get_paid_credits(user_id)
    return free_remaining + paid


def can_generate(user_id: int) -> bool:
    """Проверяет, может ли пользователь генерировать (бесплатные + платные)"""
    if is_admin(user_id):
        return True
    return get_remaining_generations(user_id) > 0


def has_free_generations(user_id: int) -> bool:
    """Проверяет, есть ли ещё бесплатные генерации"""
    if is_admin(user_id):
        return True
    return get_generations_count(user_id) < MAX_FREE_GENERATIONS


def increment_generations(user_id: int) -> None:
    """Списывает одну генерацию (сначала бесплатные, потом платные)"""
    if is_admin(user_id):
        return

    with _get_conn() as conn:
        row = conn.execute(
            "SELECT generations, paid_credits FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        current_generations = row[0] if row else 0
        current_paid = row[1] if row else 0

        if current_generations < MAX_FREE_GENERATIONS:
            # Списываем бесплатную генерацию
            conn.execute(
                """INSERT INTO users (user_id, generations)
                   VALUES (?, 1)
                   ON CONFLICT(user_id)
                   DO UPDATE SET generations = generations + 1""",
                (user_id,),
            )
            logger.info(
                f"User {user_id}: used free generation "
                f"({current_generations + 1}/{MAX_FREE_GENERATIONS})"
            )
        elif current_paid > 0:
            # Списываем платный кредит
            conn.execute(
                "UPDATE users SET paid_credits = paid_credits - 1 WHERE user_id = ?",
                (user_id,),
            )
            logger.info(
                f"User {user_id}: used paid credit "
                f"({current_paid - 1} remaining)"
            )
        else:
            logger.warning(
                f"User {user_id}: no credits available "
                f"but increment_generations called"
            )


def add_paid_credits(user_id: int, credits: int) -> None:
    """Добавляет оплаченные генерации пользователю"""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO users (user_id, paid_credits)
               VALUES (?, ?)
               ON CONFLICT(user_id)
               DO UPDATE SET paid_credits = paid_credits + ?""",
            (user_id, credits, credits),
        )
    total = get_paid_credits(user_id)
    logger.info(f"User {user_id}: added {credits} paid credits, total now: {total}")


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


# --- Платежи ---


def create_payment(
    user_id: int, package_id: str, credits: int, amount: int
) -> int:
    """Создаёт запись о платеже, возвращает ID"""
    with _get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO payments (user_id, package_id, credits, amount, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (user_id, package_id, credits, amount),
        )
        payment_id = cursor.lastrowid
    logger.info(f"Created payment {payment_id} for user {user_id}: {package_id}")
    return payment_id


def confirm_payment(payment_id: int) -> bool:
    """Подтверждает платёж и начисляет кредиты. Возвращает True при успехе."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, credits, status FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()

        if not row:
            logger.error(f"Payment {payment_id} not found")
            return False

        user_id, credits, status = row

        if status != "pending":
            logger.warning(f"Payment {payment_id} already has status: {status}")
            return False

        conn.execute(
            """UPDATE payments
               SET status = 'confirmed', confirmed_at = datetime('now')
               WHERE id = ?""",
            (payment_id,),
        )

    # Начисляем кредиты
    add_paid_credits(user_id, credits)
    logger.info(f"Payment {payment_id} confirmed: {credits} credits for user {user_id}")
    return True


def get_payment(payment_id: int) -> dict | None:
    """Возвращает информацию о платеже"""
    with _get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
    return dict(row) if row else None


def update_payment_provider_id(
    payment_id: int, provider_id: str
) -> None:
    """Сохраняет ID платежа из YooKassa"""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE payments SET payment_provider_id = ? WHERE id = ?",
            (provider_id, payment_id),
        )
    logger.info(
        f"Payment {payment_id}: set provider_id={provider_id}"
    )


def cancel_payment(payment_id: int) -> None:
    """Помечает платёж как отменённый"""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE payments SET status = 'canceled' WHERE id = ?",
            (payment_id,),
        )
    logger.info(f"Payment {payment_id} canceled")


def get_pending_payment_by_provider_id(
    provider_id: str,
) -> dict | None:
    """Находит pending-платёж по ID из YooKassa"""
    with _get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM payments "
            "WHERE payment_provider_id = ? AND status = 'pending'",
            (provider_id,),
        ).fetchone()
    return dict(row) if row else None
