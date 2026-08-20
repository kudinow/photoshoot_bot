"""Тесты оркестрации чеков НПД на стабах клиента и бота.

Запуск без pytest: python3 tests/test_npd_receipts.py

В отличие от test_npd_payload.py и test_npd_storage.py этому файлу нужен
.env в корне: npd_receipts.py импортирует settings и клавиатуры aiogram.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.services import user_limits  # noqa: E402


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    user_limits._get_db_path = lambda: Path(tmp.name)
    user_limits.init_db()


class FakePackage:
    def __init__(self, pkg_id="pack_5", credits=5, kopecks=14900):
        self.id = pkg_id
        self.credits = credits
        self.price_kopecks = kopecks
        self.price_rub = kopecks // 100


class FakeBot:
    """Считает отправленные сообщения."""

    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


def _patch_client(module, *, fails=0, uuid_value="uuid-1"):
    """Заменяет add_income стабом, падающим первые `fails` раз."""
    state = {"calls": 0}

    async def fake_add_income(service_name, amount_rub):
        state["calls"] += 1
        if state["calls"] <= fails:
            raise module.NpdClientError("сеть легла")
        return uuid_value, f"https://lknpd/receipt/{uuid_value}/print"

    module.npd_client.add_income = fake_add_income
    return state


def _no_sleep(module):
    async def instant(_seconds):
        return None

    module.asyncio.sleep = instant


def test_disabled_flag_short_circuits():
    _fresh_db()
    import bot.services.npd_receipts as nr
    from bot.services.npd_storage import get_receipt

    nr.settings.npd_enabled = False
    bot = FakeBot()
    asyncio.run(nr.issue_receipt(bot, 100, 555, FakePackage()))

    assert get_receipt(100) is None
    assert bot.messages == []


def test_successful_receipt_marks_sent_and_notifies_user():
    _fresh_db()
    import bot.services.npd_receipts as nr
    from bot.services.npd_storage import get_receipt

    nr.settings.npd_enabled = True
    _patch_client(nr)
    bot = FakeBot()
    asyncio.run(nr.issue_receipt(bot, 101, 555, FakePackage()))

    row = get_receipt(101)
    assert row["status"] == "sent"
    assert row["receipt_uuid"] == "uuid-1"
    assert row["service_name"] == (
        "Обработка фотографии (генерация портрета), 5 шт."
    )
    assert any(chat == 555 for chat, _ in bot.messages)


def test_watermark_package_uses_its_own_service_name():
    _fresh_db()
    import bot.services.npd_receipts as nr
    from bot.services.npd_storage import get_receipt

    nr.settings.npd_enabled = True
    _patch_client(nr)
    pkg = FakePackage(pkg_id="watermark_unlock", credits=0, kopecks=5000)
    asyncio.run(nr.issue_receipt(FakeBot(), 102, 555, pkg))

    assert get_receipt(102)["service_name"] == (
        "Обработка фотографии (снятие водяного знака)"
    )


def test_duplicate_call_does_not_issue_second_receipt():
    _fresh_db()
    import bot.services.npd_receipts as nr

    nr.settings.npd_enabled = True
    state = _patch_client(nr)
    bot = FakeBot()
    asyncio.run(nr.issue_receipt(bot, 103, 555, FakePackage()))
    asyncio.run(nr.issue_receipt(bot, 103, 555, FakePackage()))

    assert state["calls"] == 1, "чек пробит дважды за один платёж"


def test_transient_failure_is_retried_then_succeeds():
    _fresh_db()
    import bot.services.npd_receipts as nr
    from bot.services.npd_storage import get_receipt

    nr.settings.npd_enabled = True
    _no_sleep(nr)
    state = _patch_client(nr, fails=2)
    asyncio.run(nr.issue_receipt(FakeBot(), 104, 555, FakePackage()))

    assert state["calls"] == 3
    assert get_receipt(104)["status"] == "sent"


def test_exhausted_retries_mark_failed_and_alert_admin():
    _fresh_db()
    import bot.services.npd_receipts as nr
    from bot.services.npd_storage import get_receipt

    nr.settings.npd_enabled = True
    _no_sleep(nr)
    _patch_client(nr, fails=99)
    bot = FakeBot()
    asyncio.run(nr.issue_receipt(bot, 105, 555, FakePackage()))

    row = get_receipt(105)
    assert row["status"] == "failed"
    assert row["attempts"] == nr.MAX_ATTEMPTS
    assert any(chat == user_limits.ADMIN_ID for chat, _ in bot.messages)


def test_user_is_never_told_about_fiscalization_failure():
    _fresh_db()
    import bot.services.npd_receipts as nr

    nr.settings.npd_enabled = True
    _no_sleep(nr)
    _patch_client(nr, fails=99)
    bot = FakeBot()
    asyncio.run(nr.issue_receipt(bot, 106, 555, FakePackage()))

    user_msgs = [t for chat, t in bot.messages if chat == 555]
    assert user_msgs == [], f"юзеру ушёл шум: {user_msgs}"


def test_sweep_retries_failed_receipts():
    _fresh_db()
    import bot.services.npd_receipts as nr
    from bot.services.npd_storage import get_receipt

    nr.settings.npd_enabled = True
    _no_sleep(nr)
    _patch_client(nr, fails=99)
    asyncio.run(nr.issue_receipt(FakeBot(), 107, 555, FakePackage()))
    assert get_receipt(107)["status"] == "failed"

    _patch_client(nr, fails=0, uuid_value="uuid-2")
    healed = asyncio.run(nr.retry_pending_receipts(FakeBot()))

    assert healed == 1
    assert get_receipt(107)["status"] == "sent"


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
