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

        # Миграция: добавляем колонку last_style
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN last_style TEXT"
            )
            logger.info("Added last_style column to users table")
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

        # Таблица источников переходов (диплинки)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Миграция: добавляем колонку created_at для отслеживания регистрации
        try:
            conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
            logger.info("Added created_at column to users table")
            # Бэкфил: из referrals.joined_at
            conn.execute("""
                UPDATE users SET created_at = (
                    SELECT joined_at FROM referrals
                    WHERE referrals.user_id = users.user_id
                ) WHERE created_at IS NULL
                  AND user_id IN (SELECT user_id FROM referrals)
            """)
            # Бэкфил: из первого платежа
            conn.execute("""
                UPDATE users SET created_at = (
                    SELECT MIN(created_at) FROM payments
                    WHERE payments.user_id = users.user_id
                ) WHERE created_at IS NULL
                  AND user_id IN (SELECT DISTINCT user_id FROM payments)
            """)
            # Остальные: сентинел
            conn.execute(
                "UPDATE users SET created_at = '2025-01-01 00:00:00' "
                "WHERE created_at IS NULL"
            )
            logger.info("Backfilled created_at for existing users")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

        # Таблица лога генераций (для аналитики и retention)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                gender TEXT,
                style TEXT,
                is_paid INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_genlog_user_date
            ON generations_log(user_id, created_at)
        """)

        # Таблица лога рассылок
        conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment TEXT NOT NULL,
                message_text TEXT NOT NULL,
                total_recipients INTEGER NOT NULL,
                sent INTEGER,
                blocked INTEGER,
                failed INTEGER,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at TEXT
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


def _ensure_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Создаёт запись пользователя, если её нет (с created_at)"""
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, created_at) "
        "VALUES (?, datetime('now'))",
        (user_id,),
    )


def log_generation(
    user_id: int, gender: str, style: str, is_paid: bool
) -> None:
    """Логирует генерацию для аналитики"""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO generations_log (user_id, gender, style, is_paid)
               VALUES (?, ?, ?, ?)""",
            (user_id, gender, style, int(is_paid)),
        )


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID


def is_new_user(user_id: int) -> bool:
    """Проверяет, является ли пользователь новым (нет записи в БД)"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row is None


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
        _ensure_user(conn, user_id)

        row = conn.execute(
            "SELECT generations, paid_credits FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        current_generations = row[0] if row else 0
        current_paid = row[1] if row else 0

        if current_generations < MAX_FREE_GENERATIONS:
            # Списываем бесплатную генерацию
            conn.execute(
                "UPDATE users SET generations = generations + 1 "
                "WHERE user_id = ?",
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
        _ensure_user(conn, user_id)
        conn.execute(
            "UPDATE users SET paid_credits = paid_credits + ? "
            "WHERE user_id = ?",
            (credits, user_id),
        )
    total = get_paid_credits(user_id)
    logger.info(f"User {user_id}: added {credits} paid credits, total now: {total}")


def save_last_photo(
    user_id: int, photo_url: str, gender: str, style: str = "casual"
) -> None:
    """Сохраняет последнюю фотографию пользователя"""
    with _get_conn() as conn:
        _ensure_user(conn, user_id)
        conn.execute(
            "UPDATE users SET last_photo_url = ?, last_gender = ?, "
            "last_style = ? WHERE user_id = ?",
            (photo_url, gender, style, user_id),
        )
    logger.info(f"Saved last photo for user {user_id}")


def get_last_photo(
    user_id: int,
) -> tuple[str | None, str | None, str | None]:
    """Возвращает последнюю фотографию, пол и стиль пользователя"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT last_photo_url, last_gender, last_style "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row:
        return row[0], row[1], row[2]
    return None, None, None


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


# --- Реферальная статистика ---


def save_referral(user_id: int, source: str) -> None:
    """Сохраняет источник перехода (только при первом визите с source)"""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO referrals (user_id, source) VALUES (?, ?)",
            (user_id, source),
        )


def get_referral_stats() -> list[tuple[str, int]]:
    """Возвращает статистику по источникам [(source, count), ...]"""
    with _get_conn() as conn:
        return conn.execute(
            "SELECT source, COUNT(*) FROM referrals "
            "GROUP BY source ORDER BY COUNT(*) DESC"
        ).fetchall()


# --- Рассылки ---

SEGMENT_QUERIES: dict[str, str] = {
    "all": """
        SELECT user_id FROM users ORDER BY user_id
    """,
    "free_exhausted": """
        SELECT u.user_id FROM users u
        WHERE u.generations >= 1
          AND u.paid_credits = 0
          AND NOT EXISTS (
              SELECT 1 FROM payments p
              WHERE p.user_id = u.user_id AND p.status = 'confirmed'
          )
        ORDER BY u.user_id
    """,
    "abandoned_cart": """
        SELECT DISTINCT p.user_id FROM payments p
        WHERE p.status = 'pending'
          AND NOT EXISTS (
              SELECT 1 FROM payments p2
              WHERE p2.user_id = p.user_id AND p2.status = 'confirmed'
          )
        ORDER BY p.user_id
    """,
    "never_generated": """
        SELECT user_id FROM users
        WHERE generations = 0 AND paid_credits = 0
        ORDER BY user_id
    """,
}

SEGMENT_LABELS: dict[str, str] = {
    "all": "Все пользователи",
    "free_exhausted": "Использовали бесплатную, не купили",
    "abandoned_cart": "Брошенная корзина",
    "never_generated": "Не начали использовать",
}


def get_segment_user_ids(segment: str) -> list[int]:
    """Возвращает список user_id для заданного сегмента"""
    query = SEGMENT_QUERIES.get(segment)
    if not query:
        logger.warning(f"Unknown broadcast segment: {segment}")
        return []
    with _get_conn() as conn:
        rows = conn.execute(query).fetchall()
    return [row[0] for row in rows]


def get_segment_count(segment: str) -> int:
    """Возвращает количество пользователей в сегменте"""
    return len(get_segment_user_ids(segment))


def create_broadcast_log(
    segment: str, message_text: str, total: int
) -> int:
    """Создаёт запись о рассылке, возвращает ID"""
    with _get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO broadcasts
               (segment, message_text, total_recipients)
               VALUES (?, ?, ?)""",
            (segment, message_text, total),
        )
        return cursor.lastrowid


def finish_broadcast_log(
    broadcast_id: int, sent: int, blocked: int, failed: int
) -> None:
    """Обновляет запись о рассылке после завершения"""
    with _get_conn() as conn:
        conn.execute(
            """UPDATE broadcasts
               SET sent = ?, blocked = ?, failed = ?,
                   finished_at = datetime('now')
               WHERE id = ?""",
            (sent, blocked, failed, broadcast_id),
        )
