"""Хранилище чеков НПД: очередь фискализации платежей.

Отдельный модуль, а не часть user_limits.py — тот уже 859 строк.
Импортирует только user_limits (stdlib-only), поэтому тестируется без .env.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from bot.services.user_limits import get_conn

logger = logging.getLogger(__name__)

_COLUMNS = (
    "payment_id, user_id, amount, service_name, status, "
    "receipt_uuid, print_url, attempts, last_error, created_at"
)


def _row_to_dict(row) -> Dict[str, Any]:
    keys = [c.strip() for c in _COLUMNS.split(",")]
    return dict(zip(keys, row))


def create_receipt_row(
    payment_id: int, user_id: int, amount: int, service_name: str
) -> bool:
    """Ставит платёж в очередь на фискализацию.

    Returns:
        True — строку создали мы, можно пробивать чек.
        False — строка уже есть (гонка polling'а с ручной кнопкой либо
        повторный вызов), чек уже в работе или пробит.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO npd_receipts
               (payment_id, user_id, amount, service_name)
               VALUES (?, ?, ?, ?)""",
            (payment_id, user_id, amount, service_name),
        )
        return cur.rowcount == 1


def mark_sent(payment_id: int, receipt_uuid: str, print_url: str) -> None:
    """Чек успешно зарегистрирован в ФНС."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE npd_receipts
               SET status = 'sent', receipt_uuid = ?, print_url = ?,
                   updated_at = datetime('now')
               WHERE payment_id = ?""",
            (receipt_uuid, print_url, payment_id),
        )


def record_attempt(payment_id: int, error: str) -> int:
    """Фиксирует неудачную попытку. Возвращает новое число попыток."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE npd_receipts
               SET attempts = attempts + 1, last_error = ?,
                   updated_at = datetime('now')
               WHERE payment_id = ?""",
            (error[:500], payment_id),
        )
        row = conn.execute(
            "SELECT attempts FROM npd_receipts WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        return row[0] if row else 0


def mark_failed(payment_id: int) -> None:
    """Попытки исчерпаны — чек требует ручного пробития."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE npd_receipts
               SET status = 'failed', updated_at = datetime('now')
               WHERE payment_id = ?""",
            (payment_id,),
        )


def get_receipt(payment_id: int) -> Optional[Dict[str, Any]]:
    """Строка чека по id платежа или None."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM npd_receipts WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_unfinished_receipts() -> List[Dict[str, Any]]:
    """Все незакрытые чеки (pending + failed), старые первыми."""
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT {_COLUMNS} FROM npd_receipts
                WHERE status IN ('pending', 'failed')
                ORDER BY created_at ASC"""
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
