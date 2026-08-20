"""Тесты хранилища чеков НПД на временной БД.

Запуск без pytest: python3 tests/test_npd_storage.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.services import user_limits  # noqa: E402


def _fresh_db():
    """Подменяет путь к БД на временный файл и инициализирует схему."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    user_limits._get_db_path = lambda: Path(tmp.name)
    user_limits.init_db()
    return tmp.name


def test_create_row_returns_true_on_first_insert():
    _fresh_db()
    from bot.services.npd_storage import create_receipt_row

    assert create_receipt_row(1, 555, 14900, "Услуга") is True


def test_create_row_returns_false_on_duplicate_payment():
    _fresh_db()
    from bot.services.npd_storage import create_receipt_row

    assert create_receipt_row(2, 555, 14900, "Услуга") is True
    assert create_receipt_row(2, 555, 14900, "Услуга") is False


def test_new_row_starts_pending_with_zero_attempts():
    _fresh_db()
    from bot.services.npd_storage import create_receipt_row, get_receipt

    create_receipt_row(3, 555, 5000, "Снятие знака")
    row = get_receipt(3)
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert row["amount"] == 5000
    assert row["service_name"] == "Снятие знака"


def test_mark_sent_stores_uuid_and_url():
    _fresh_db()
    from bot.services.npd_storage import (
        create_receipt_row,
        get_receipt,
        mark_sent,
    )

    create_receipt_row(4, 555, 14900, "Услуга")
    mark_sent(4, "uuid-1", "https://example/print")
    row = get_receipt(4)
    assert row["status"] == "sent"
    assert row["receipt_uuid"] == "uuid-1"
    assert row["print_url"] == "https://example/print"


def test_record_attempt_increments_and_stores_error():
    _fresh_db()
    from bot.services.npd_storage import (
        create_receipt_row,
        get_receipt,
        record_attempt,
    )

    create_receipt_row(5, 555, 14900, "Услуга")
    assert record_attempt(5, "boom") == 1
    assert record_attempt(5, "boom again") == 2
    row = get_receipt(5)
    assert row["attempts"] == 2
    assert row["last_error"] == "boom again"
    assert row["status"] == "pending"


def test_mark_failed_sets_status():
    _fresh_db()
    from bot.services.npd_storage import (
        create_receipt_row,
        get_receipt,
        mark_failed,
    )

    create_receipt_row(6, 555, 14900, "Услуга")
    mark_failed(6)
    assert get_receipt(6)["status"] == "failed"


def test_unfinished_returns_pending_and_failed_but_not_sent():
    _fresh_db()
    from bot.services.npd_storage import (
        create_receipt_row,
        get_unfinished_receipts,
        mark_failed,
        mark_sent,
    )

    create_receipt_row(10, 555, 100, "A")   # остаётся pending
    create_receipt_row(11, 556, 200, "B")
    mark_failed(11)
    create_receipt_row(12, 557, 300, "C")
    mark_sent(12, "u", "url")

    ids = {r["payment_id"] for r in get_unfinished_receipts()}
    assert ids == {10, 11}


def test_get_receipt_returns_none_for_unknown_payment():
    _fresh_db()
    from bot.services.npd_storage import get_receipt

    assert get_receipt(9999) is None


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"\n{'FAILED' if failures else 'OK'} — {failures} failure(s)")
    sys.exit(1 if failures else 0)
