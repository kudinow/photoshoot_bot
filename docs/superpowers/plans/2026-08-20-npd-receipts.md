# Автоматические чеки НПД («Мой налог») — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После каждого подтверждённого платежа автоматически регистрировать доход в «Мой налог» и присылать пользователю ссылку на чек прямо в боте.

**Architecture:** Свой тонкий async-клиент к `lknpd.nalog.ru` (3 вызова: логин, refresh, создание дохода) + таблица-очередь `npd_receipts` с ретраями + fire-and-forget вызов после `confirm_payment()`. Фискализация никогда не блокирует выдачу оплаченного товара. Чистая логика вынесена в модули без зависимостей от `bot.config`, чтобы тесты бежали без `.env`.

**Tech Stack:** Python 3.9 (локально) / 3.10 (прод), aiogram 3.13, aiohttp 3.10 (уже в зависимостях — новых пакетов не требуется), SQLite.

**Spec:** [docs/superpowers/specs/2026-08-20-npd-receipts-design.md](../specs/2026-08-20-npd-receipts-design.md)

## Global Constraints

- **Новых зависимостей не добавлять.** `aiohttp==3.10.5` уже в `requirements.txt`.
- **Аннотации полей pydantic `Settings` — только `Optional[str]`, никогда `str | None`.** Pydantic вычисляет аннотации в рантайме, локальная разработка идёт на Python 3.9.6.
- **Каждый новый модуль начинается с `from __future__ import annotations`** — как все существующие модули проекта.
- **UI-тексты и docstrings — на русском**, как во всей кодовой базе.
- **Модули с чистой логикой (`npd_payload.py`) не импортируют `bot.config`** — иначе тесты потребуют `.env`.
- **Базовый URL API:** `https://lknpd.nalog.ru/api/v1`
- **Задержки ретраев:** `2, 5, 15, 60, 300` секунд. **Максимум попыток: 6** (одна немедленная + 5 ретраев).
- **Наименования услуг в чеке:** `«Обработка фотографии (генерация портрета), {credits} шт.»` и `«Обработка фотографии (снятие водяного знака)»`.
- **Фича-флаг `npd_enabled` по умолчанию `False`** — код едет на прод мёртвым.
- **Тесты — self-contained, без pytest**, запуск `python3 tests/test_<name>.py`, по образцу [tests/test_prompt_fallback.py](../../../tests/test_prompt_fallback.py).

---

## File Structure

| Файл | Ответственность | Зависимости |
|------|-----------------|-------------|
| `bot/services/npd_payload.py` (создать) | Чистые функции: сборка тела запроса, print_url, backoff, протухание токена, наименование услуги | **никаких** (кроме stdlib) |
| `bot/services/npd_storage.py` (создать) | CRUD по таблице `npd_receipts` | `user_limits` (stdlib-only) |
| `bot/services/npd_client.py` (создать) | HTTP-клиент к `lknpd.nalog.ru`: логин, refresh, `add_income` | `aiohttp`, `settings`, `npd_payload` |
| `bot/services/npd_receipts.py` (создать) | Оркестрация: очередь, ретраи, доставка юзеру, алерт админу | `npd_client`, `npd_storage`, `npd_payload`, aiogram |
| `bot/handlers/receipts.py` (создать) | Админ-команды `/receipts_failed`, `/receipts_retry` | `npd_receipts`, `npd_storage` |
| `bot/config.py` (изменить) | Поля `Settings` для НПД | — |
| `bot/services/user_limits.py` (изменить) | Таблица `npd_receipts` в `init_db()`, публичный `get_conn` | — |
| `bot/handlers/payment.py` (изменить) | Два вызова `issue_receipt` после `confirm_payment` | — |
| `bot/keyboards/inline.py` (изменить) | Кнопка «🧾 Открыть чек» | — |
| `bot/main.py` (изменить) | Регистрация роутера + sweep на старте | — |
| `.env.example` (изменить) | Документация новых переменных | — |
| `tests/test_npd_payload.py` (создать) | Тесты чистых функций | — |
| `tests/test_npd_storage.py` (создать) | Тесты CRUD и идемпотентности на временной БД | — |
| `tests/test_npd_receipts.py` (создать) | Тесты оркестрации на стабах клиента и бота | — |

---

### Task 1: Чистые хелперы НПД (`npd_payload.py`)

**Files:**
- Create: `bot/services/npd_payload.py`
- Test: `tests/test_npd_payload.py`

**Interfaces:**
- Consumes: ничего (первая задача)
- Produces:
  - `NPD_API_BASE: str`
  - `RETRY_DELAYS: tuple`, `MAX_ATTEMPTS: int`
  - `build_service_name(is_watermark_unlock: bool, credits: int) -> str`
  - `build_print_url(inn: str, receipt_uuid: str) -> str`
  - `format_npd_time(moment: datetime) -> str`
  - `build_income_payload(service_name: str, amount_rub: float, moment: datetime) -> dict`
  - `kopecks_to_rubles(kopecks: int) -> float`
  - `retry_delay(attempt: int) -> Optional[int]`
  - `is_token_expired(expires_at: Optional[float], now: float, skew: int = 60) -> bool`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_npd_payload.py`:

```python
"""Тесты чистых хелперов интеграции с «Мой налог».

Запуск без pytest: python3 tests/test_npd_payload.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.services.npd_payload import (  # noqa: E402
    MAX_ATTEMPTS,
    RETRY_DELAYS,
    build_income_payload,
    build_print_url,
    build_service_name,
    format_npd_time,
    is_token_expired,
    kopecks_to_rubles,
    retry_delay,
)

MSK = timezone(timedelta(hours=3))
MOMENT = datetime(2026, 8, 20, 12, 34, 56, tzinfo=MSK)


def test_service_name_for_credit_package_mentions_count():
    name = build_service_name(False, 5)
    assert name == "Обработка фотографии (генерация портрета), 5 шт."


def test_service_name_for_watermark_unlock():
    name = build_service_name(True, 0)
    assert name == "Обработка фотографии (снятие водяного знака)"


def test_print_url_uses_inn_and_uuid():
    url = build_print_url("123456789012", "abc-def")
    assert url == (
        "https://lknpd.nalog.ru/api/v1/receipt/123456789012/abc-def/print"
    )


def test_npd_time_has_colon_in_offset():
    stamp = format_npd_time(MOMENT)
    assert stamp == "2026-08-20T12:34:56+03:00", stamp


def test_npd_time_converts_to_moscow():
    utc_moment = datetime(2026, 8, 20, 9, 34, 56, tzinfo=timezone.utc)
    assert format_npd_time(utc_moment) == "2026-08-20T12:34:56+03:00"


def test_npd_time_drops_microseconds():
    noisy = MOMENT.replace(microsecond=123456)
    assert format_npd_time(noisy) == "2026-08-20T12:34:56+03:00"


def test_kopecks_convert_to_rubles():
    assert kopecks_to_rubles(14900) == 149.0
    assert kopecks_to_rubles(5000) == 50.0


def test_income_payload_has_required_top_level_fields():
    payload = build_income_payload("Услуга", 149.0, MOMENT)
    assert payload["paymentType"] == "CASH"
    assert payload["ignoreMaxTotalIncomeRestriction"] is False
    assert payload["requestTime"] == "2026-08-20T12:34:56+03:00"
    assert payload["operationTime"] == "2026-08-20T12:34:56+03:00"


def test_income_payload_marks_individual_client():
    payload = build_income_payload("Услуга", 149.0, MOMENT)
    assert payload["client"]["incomeType"] == "FROM_INDIVIDUAL"
    assert payload["client"]["contactPhone"] is None
    assert payload["client"]["displayName"] is None
    assert payload["client"]["inn"] is None


def test_income_payload_services_and_total():
    payload = build_income_payload("Обработка фото", 149.0, MOMENT)
    assert payload["services"] == [
        {"name": "Обработка фото", "amount": 149.0, "quantity": 1}
    ]
    assert payload["totalAmount"] == "149.00"


def test_income_payload_total_is_string_with_two_decimals():
    payload = build_income_payload("Услуга", 50.0, MOMENT)
    assert payload["totalAmount"] == "50.00"


def test_retry_delay_follows_the_documented_backoff():
    assert [retry_delay(n) for n in range(1, 6)] == [2, 5, 15, 60, 300]


def test_retry_delay_is_none_when_attempts_exhausted():
    assert retry_delay(MAX_ATTEMPTS) is None
    assert retry_delay(99) is None


def test_max_attempts_matches_delay_table():
    assert MAX_ATTEMPTS == len(RETRY_DELAYS) + 1


def test_token_without_expiry_counts_as_expired():
    assert is_token_expired(None, now=1000.0) is True


def test_token_expires_early_because_of_skew():
    # Токен истекает в 1000, запас 60 → уже протух в 950
    assert is_token_expired(1000.0, now=950.0) is True


def test_fresh_token_is_not_expired():
    assert is_token_expired(1000.0, now=800.0) is False


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
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `python3 tests/test_npd_payload.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.npd_payload'`

- [ ] **Step 3: Написать минимальную реализацию**

Создать `bot/services/npd_payload.py`:

```python
"""Чистые хелперы для интеграции с API «Мой налог» (lknpd.nalog.ru).

Модуль намеренно НЕ импортирует ничего из bot.config — благодаря этому
тесты запускаются без .env (тот же приём, что в prompt_fallback.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

NPD_API_BASE = "https://lknpd.nalog.ru/api/v1"

# Московское время — ФНС ждёт метки именно в нём
MSK = timezone(timedelta(hours=3))

# Задержки (сек) перед ретраями после неудачных попыток 1..5
RETRY_DELAYS = (2, 5, 15, 60, 300)

# Всего попыток: одна немедленная + по одной на каждую задержку
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1

# Запас перед формальным истечением токена (сек)
TOKEN_EXPIRY_SKEW = 60


def build_service_name(is_watermark_unlock: bool, credits: int) -> str:
    """Наименование услуги, которое попадёт в чек."""
    if is_watermark_unlock:
        return "Обработка фотографии (снятие водяного знака)"
    return f"Обработка фотографии (генерация портрета), {credits} шт."


def build_print_url(inn: str, receipt_uuid: str) -> str:
    """Ссылка на печатную форму чека."""
    return f"{NPD_API_BASE}/receipt/{inn}/{receipt_uuid}/print"


def format_npd_time(moment: datetime) -> str:
    """Время в формате, который принимает ФНС: 2026-08-20T12:34:56+03:00"""
    return moment.astimezone(MSK).replace(microsecond=0).isoformat()


def kopecks_to_rubles(kopecks: int) -> float:
    """Копейки → рубли. В payments суммы хранятся в копейках."""
    return round(kopecks / 100, 2)


def build_income_payload(
    service_name: str, amount_rub: float, moment: datetime
) -> Dict[str, Any]:
    """Тело запроса POST /income."""
    stamp = format_npd_time(moment)
    amount = round(float(amount_rub), 2)
    return {
        "paymentType": "CASH",
        "ignoreMaxTotalIncomeRestriction": False,
        "client": {
            "incomeType": "FROM_INDIVIDUAL",
            "contactPhone": None,
            "displayName": None,
            "inn": None,
        },
        "requestTime": stamp,
        "operationTime": stamp,
        "services": [
            {"name": service_name, "amount": amount, "quantity": 1}
        ],
        "totalAmount": f"{amount:.2f}",
    }


def retry_delay(attempt: int) -> Optional[int]:
    """Пауза перед следующей попыткой.

    Args:
        attempt: номер уже сделанной попытки (1 — первая).

    Returns:
        Секунды до следующей попытки или None, если попытки исчерпаны.
    """
    if attempt < 1 or attempt > len(RETRY_DELAYS):
        return None
    return RETRY_DELAYS[attempt - 1]


def is_token_expired(
    expires_at: Optional[float],
    now: float,
    skew: int = TOKEN_EXPIRY_SKEW,
) -> bool:
    """Протух ли access-токен (с запасом skew секунд)."""
    if expires_at is None:
        return True
    return now >= expires_at - skew
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `python3 tests/test_npd_payload.py`
Expected: PASS для всех 17 тестов, последняя строка `OK — 0 failure(s)`

- [ ] **Step 5: Коммит**

```bash
git add bot/services/npd_payload.py tests/test_npd_payload.py
git commit -m "feat: pure helpers for НПД receipt payloads"
```

---

### Task 2: Конфиг и переменные окружения

**Files:**
- Modify: `bot/config.py:10-38` (класс `Settings`)
- Modify: `.env.example`

**Interfaces:**
- Consumes: ничего
- Produces: `settings.npd_inn`, `settings.npd_password`, `settings.npd_device_id`, `settings.npd_enabled` — все `Optional[str]`, кроме `npd_enabled: bool = False`

- [ ] **Step 1: Добавить поля в `Settings`**

В `bot/config.py`, сразу после блока YooKassa (перед `# Settings`), вставить:

```python
    # «Мой налог» (НПД) — автоматические чеки самозанятого.
    # Аннотации строго Optional[str]: pydantic вычисляет их в рантайме,
    # а локальная разработка идёт на Python 3.9.
    npd_inn: Optional[str] = None
    npd_password: Optional[str] = None
    # sourceDeviceId обязан быть стабильным — токен привязан к нему.
    npd_device_id: Optional[str] = None
    # Фича-флаг: пока False, фискализация полностью выключена.
    npd_enabled: bool = False
```

- [ ] **Step 2: Проверить, что конфиг грузится**

Run: `python3 -c "from bot.config import settings; print(settings.npd_enabled, settings.npd_inn)"`
Expected: `False None`

Если падает с `ValidationError` про отсутствующие обязательные поля — значит в корне нет `.env`. Скопировать `.env.example` в `.env` и заполнить существующие ключи; новые НПД-поля заполнять не нужно, у них есть значения по умолчанию.

- [ ] **Step 3: Задокументировать переменные в `.env.example`**

Добавить в конец `.env.example`, перед блоком `# Settings`:

```
# «Мой налог» (НПД) — автоматические чеки самозанятого.
# ЮKassa отключила чеки для самозанятых 29.12.2025, поэтому доход
# регистрируется напрямую в ФНС через lknpd.nalog.ru.
# NPD_PASSWORD — пароль для входа на lknpd.nalog.ru ПО ИНН.
# Если вход только по SMS/Госуслугам — сначала задать пароль в приложении.
# NPD_DEVICE_ID — любой стабильный UUID. К нему привязывается токен,
# поэтому менять его между рестартами нельзя.
NPD_ENABLED=false
NPD_INN=
NPD_PASSWORD=
NPD_DEVICE_ID=
```

- [ ] **Step 4: Убедиться, что переменные подхватываются**

Run:
```bash
NPD_ENABLED=true NPD_INN=123456789012 python3 -c "from bot.config import settings; print(settings.npd_enabled, settings.npd_inn)"
```
Expected: `True 123456789012`

- [ ] **Step 5: Коммит**

```bash
git add bot/config.py .env.example
git commit -m "feat: НПД settings and env documentation"
```

---

### Task 3: Таблица `npd_receipts` и хранилище

**Files:**
- Modify: `bot/services/user_limits.py:42-45` (добавить публичный `get_conn`)
- Modify: `bot/services/user_limits.py` (создание таблицы внутри `init_db()`)
- Create: `bot/services/npd_storage.py`
- Test: `tests/test_npd_storage.py`

**Interfaces:**
- Consumes: `bot.services.user_limits.get_conn`
- Produces:
  - `create_receipt_row(payment_id: int, user_id: int, amount: int, service_name: str) -> bool` — `True`, если строку создали именно мы
  - `mark_sent(payment_id: int, receipt_uuid: str, print_url: str) -> None`
  - `record_attempt(payment_id: int, error: str) -> int` — возвращает новое число попыток
  - `mark_failed(payment_id: int) -> None`
  - `get_receipt(payment_id: int) -> Optional[dict]`
  - `get_unfinished_receipts() -> list`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_npd_storage.py`:

```python
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
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `python3 tests/test_npd_storage.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.npd_storage'`

- [ ] **Step 3: Добавить публичный `get_conn` в `user_limits.py`**

Сразу после существующей функции `_get_conn` (строка ~45) вставить:

```python
def get_conn() -> sqlite3.Connection:
    """Публичный алиас _get_conn для других сервисных модулей.

    Namespace БД общий, но запросы по своим таблицам живут в своих модулях —
    user_limits.py уже 859 строк.
    """
    return _get_conn()
```

- [ ] **Step 4: Создать таблицу в `init_db()`**

В `bot/services/user_limits.py`, внутри `init_db()`, в конец блока `with _get_conn() as conn:` (после создания последней существующей таблицы) добавить:

```python
        # Чеки НПД («Мой налог») — очередь фискализации платежей
        conn.execute("""
            CREATE TABLE IF NOT EXISTS npd_receipts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id    INTEGER NOT NULL UNIQUE,
                user_id       INTEGER NOT NULL,
                amount        INTEGER NOT NULL,
                service_name  TEXT    NOT NULL,
                status        TEXT    NOT NULL DEFAULT 'pending',
                receipt_uuid  TEXT,
                print_url     TEXT,
                attempts      INTEGER NOT NULL DEFAULT 0,
                last_error    TEXT,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
```

- [ ] **Step 5: Написать `npd_storage.py`**

Создать `bot/services/npd_storage.py`:

```python
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
```

- [ ] **Step 6: Запустить тест и убедиться, что он проходит**

Run: `python3 tests/test_npd_storage.py`
Expected: PASS для всех 8 тестов, `OK — 0 failure(s)`

- [ ] **Step 7: Убедиться, что миграция не ломает существующую БД**

Run: `python3 -c "from bot.services.user_limits import init_db; init_db(); print('init_db ok')"`
Expected: `init_db ok` — и существующая локальная `user_data.db` продолжает открываться.

- [ ] **Step 8: Коммит**

```bash
git add bot/services/npd_storage.py bot/services/user_limits.py tests/test_npd_storage.py
git commit -m "feat: npd_receipts table and storage layer"
```

---

### Task 4: HTTP-клиент к «Мой налог»

**Files:**
- Create: `bot/services/npd_client.py`

**Interfaces:**
- Consumes: `npd_payload.build_income_payload`, `npd_payload.build_print_url`, `npd_payload.is_token_expired`, `npd_payload.NPD_API_BASE`, `settings`
- Produces:
  - `class NpdClientError(Exception)`
  - `class NpdClient` с методом `async add_income(service_name: str, amount_rub: float) -> Tuple[str, str]` (возвращает `(receipt_uuid, print_url)`)
  - `npd_client = NpdClient()` — модульный синглтон, как `kie_client` / `openai_client`

- [ ] **Step 1: Написать клиент**

Создать `bot/services/npd_client.py`:

```python
"""Клиент API «Мой налог» (lknpd.nalog.ru) для чеков самозанятого.

API неофициальный — ФНС может изменить контракт без предупреждения.
Все сбои пробрасываются как NpdClientError и обрабатываются вызывающим
кодом ретраями (см. npd_receipts.py).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import aiohttp

from bot.config import settings
from bot.services.npd_payload import (
    NPD_API_BASE,
    build_income_payload,
    build_print_url,
    is_token_expired,
)

logger = logging.getLogger(__name__)


class NpdClientError(Exception):
    """Ошибка клиента «Мой налог»"""

    pass


class _Unauthorized(Exception):
    """Внутренний сигнал 401 — наружу не выходит."""

    pass


class NpdClient:
    """Тонкий async-клиент: логин, refresh токена, регистрация дохода."""

    REQUEST_TIMEOUT = 30
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # Токен ФНС живёт около часа; точное значение приходит в ответе
    DEFAULT_TOKEN_TTL = 3600

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._inn: Optional[str] = settings.npd_inn
        self._device_id = settings.npd_device_id or self._new_device_id()

    @staticmethod
    def _new_device_id() -> str:
        generated = uuid.uuid4().hex[:21]
        logger.warning(
            "NPD_DEVICE_ID is empty — generated a temporary one (%s). "
            "Put it into .env: токен ФНС привязан к device id, "
            "иначе каждый рестарт = новый вход.",
            generated,
        )
        return generated

    def _device_info(self) -> Dict[str, Any]:
        return {
            "sourceDeviceId": self._device_id,
            "sourceType": "WEB",
            "appVersion": "1.0.0",
            "metaDetails": {"userAgent": self.USER_AGENT},
        }

    async def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST с JSON-телом. Бросает NpdClientError на любой не-2xx."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Referrer": "https://lknpd.nalog.ru/",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{NPD_API_BASE}{path}", json=payload, headers=headers
                ) as resp:
                    body = await resp.text()
                    if resp.status == 401:
                        raise _Unauthorized(body[:200])
                    if resp.status >= 400:
                        raise NpdClientError(
                            f"НПД {path} вернул {resp.status}: {body[:200]}"
                        )
        except aiohttp.ClientError as exc:
            raise NpdClientError(f"Сеть недоступна для {path}: {exc}") from exc

        # Парсим уже вычитанный text, а не resp.json(): тело прочитано выше,
        # и ФНС иногда отдаёт JSON с неожиданным Content-Type.
        try:
            return json.loads(body)
        except ValueError as exc:
            raise NpdClientError(
                f"НПД {path} вернул не-JSON: {body[:200]}"
            ) from exc

    async def _authenticate(self) -> None:
        """Полный вход по ИНН и паролю."""
        if not settings.npd_inn or not settings.npd_password:
            raise NpdClientError(
                "NPD_INN или NPD_PASSWORD не заданы в .env"
            )

        data = await self._post(
            "/auth/lkfl",
            {
                "username": settings.npd_inn,
                "password": settings.npd_password,
                "deviceInfo": self._device_info(),
            },
        )
        self._store_tokens(data)
        logger.info("НПД: успешный вход по ИНН")

    async def _refresh(self) -> None:
        """Обновление access-токена по refreshToken."""
        if not self._refresh_token:
            raise NpdClientError("Нет refreshToken для обновления")

        data = await self._post(
            "/auth/token",
            {
                "refreshToken": self._refresh_token,
                "deviceInfo": self._device_info(),
            },
        )
        self._store_tokens(data)
        logger.info("НПД: токен обновлён")

    def _store_tokens(self, data: Dict[str, Any]) -> None:
        token = data.get("token")
        if not token:
            raise NpdClientError(f"В ответе нет token: {str(data)[:200]}")

        self._token = token
        self._refresh_token = data.get("refreshToken") or self._refresh_token
        self._expires_at = time.time() + self.DEFAULT_TOKEN_TTL

        profile = data.get("profile") or {}
        if profile.get("inn"):
            self._inn = str(profile["inn"])

    async def _ensure_token(self) -> str:
        """Возвращает живой access-токен, обновляя или перелогиниваясь."""
        if not is_token_expired(self._expires_at, time.time()):
            return self._token

        if self._refresh_token:
            try:
                await self._refresh()
                return self._token
            except (NpdClientError, _Unauthorized) as exc:
                logger.warning(
                    "НПД: refresh не прошёл (%s), делаю полный вход", exc
                )

        await self._authenticate()
        return self._token

    async def add_income(
        self, service_name: str, amount_rub: float
    ) -> Tuple[str, str]:
        """Регистрирует доход и возвращает (receipt_uuid, print_url).

        Raises:
            NpdClientError: любой сбой сети, авторизации или API.
        """
        token = await self._ensure_token()
        payload = build_income_payload(
            service_name, amount_rub, datetime.now(timezone.utc)
        )

        try:
            data = await self._post("/income", payload, token=token)
        except _Unauthorized:
            # Токен протух раньше срока — один прозрачный перелогин
            logger.info("НПД: 401 на /income, перелогиниваюсь")
            self._token = None
            self._expires_at = None
            token = await self._ensure_token()
            try:
                data = await self._post("/income", payload, token=token)
            except _Unauthorized as exc:
                raise NpdClientError(
                    f"НПД отклонил авторизацию повторно: {exc}"
                ) from exc

        receipt_uuid = data.get("approvedReceiptUuid")
        if not receipt_uuid:
            raise NpdClientError(
                f"В ответе нет approvedReceiptUuid: {str(data)[:200]}"
            )

        if not self._inn:
            raise NpdClientError("ИНН неизвестен — не могу собрать ссылку")

        return receipt_uuid, build_print_url(self._inn, receipt_uuid)


npd_client = NpdClient()
```

- [ ] **Step 2: Проверить, что модуль импортируется и синглтон создаётся**

Run: `python3 -c "from bot.services.npd_client import npd_client; print(type(npd_client).__name__)"`
Expected: `NpdClient` (плюс WARNING в логе про пустой `NPD_DEVICE_ID` — это ожидаемо)

- [ ] **Step 3: Проверить, что без кредов клиент падает понятной ошибкой**

Run:
```bash
python3 -c "
import asyncio
from bot.services.npd_client import npd_client, NpdClientError
try:
    asyncio.run(npd_client.add_income('Тест', 50.0))
except NpdClientError as e:
    print('OK:', e)
"
```
Expected: `OK: NPD_INN или NPD_PASSWORD не заданы в .env`

- [ ] **Step 4: Коммит**

```bash
git add bot/services/npd_client.py
git commit -m "feat: lknpd.nalog.ru API client"
```

---

### Task 5: Оркестрация — очередь, ретраи, доставка

**Files:**
- Create: `bot/services/npd_receipts.py`
- Modify: `bot/keyboards/inline.py` (добавить в конец файла)
- Test: `tests/test_npd_receipts.py`

**Interfaces:**
- Consumes: `npd_client.add_income`, `npd_storage.*`, `npd_payload.retry_delay`, `npd_payload.MAX_ATTEMPTS`, `npd_payload.build_service_name`, `npd_payload.kopecks_to_rubles`, `user_limits.ADMIN_ID`, `config.WATERMARK_UNLOCK_ID`
- Produces:
  - `async issue_receipt(bot, payment_id: int, user_id: int, pkg) -> None`
  - `async retry_pending_receipts(bot) -> int` — возвращает число успешно добитых чеков
  - `get_receipt_keyboard(print_url: str) -> InlineKeyboardMarkup` (в `inline.py`)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_npd_receipts.py`:

```python
"""Тесты оркестрации чеков НПД на стабах клиента и бота.

Запуск без pytest: python3 tests/test_npd_receipts.py
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
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `python3 tests/test_npd_receipts.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.npd_receipts'`

В отличие от тестов задач 1 и 3, этому файлу **нужен `.env` в корне**:
`npd_receipts.py` импортирует `settings` и клавиатуры aiogram. Если падает
`ValidationError` про отсутствующие поля — заполнить `.env` существующими
ключами (НПД-поля не требуются, у них есть значения по умолчанию).

- [ ] **Step 3: Добавить клавиатуру с чеком**

В конец `bot/keyboards/inline.py` добавить:

```python
def get_receipt_keyboard(print_url: str) -> InlineKeyboardMarkup:
    """Кнопка со ссылкой на чек НПД"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🧾 Открыть чек",
                url=print_url,
            )],
        ]
    )
```

- [ ] **Step 4: Написать оркестратор**

Создать `bot/services/npd_receipts.py`:

```python
"""Оркестрация фискализации: очередь, ретраи, доставка чека.

Ключевой инвариант: сбой фискализации НИКОГДА не мешает пользователю
получить оплаченное. Все ошибки уходят в лог и админу, но не юзеру.
"""

from __future__ import annotations

import asyncio
import logging

from bot.config import WATERMARK_UNLOCK_ID, settings
from bot.keyboards.inline import get_receipt_keyboard
from bot.services.npd_client import NpdClientError, npd_client
from bot.services.npd_payload import (
    MAX_ATTEMPTS,
    build_service_name,
    kopecks_to_rubles,
    retry_delay,
)
from bot.services.npd_storage import (
    create_receipt_row,
    get_unfinished_receipts,
    mark_failed,
    mark_sent,
    record_attempt,
)
from bot.services.user_limits import ADMIN_ID

logger = logging.getLogger(__name__)


async def issue_receipt(bot, payment_id: int, user_id: int, pkg) -> None:
    """Регистрирует доход в «Мой налог» и присылает юзеру ссылку на чек.

    Вызывается через asyncio.create_task — никогда не блокирует выдачу
    оплаченного товара.
    """
    if not settings.npd_enabled:
        return

    service_name = build_service_name(
        pkg.id == WATERMARK_UNLOCK_ID, pkg.credits
    )

    # INSERT OR IGNORE: защита от гонки polling'а с ручной кнопкой
    if not create_receipt_row(
        payment_id, user_id, pkg.price_kopecks, service_name
    ):
        logger.debug(
            "НПД: чек для платежа %s уже в работе, пропускаю", payment_id
        )
        return

    await _fiscalize(
        bot, payment_id, user_id, service_name, pkg.price_kopecks
    )


async def retry_pending_receipts(bot) -> int:
    """Добивает все незакрытые чеки. Возвращает число успешных."""
    if not settings.npd_enabled:
        return 0

    unfinished = get_unfinished_receipts()
    if not unfinished:
        return 0

    logger.info("НПД: добиваю %d незакрытых чеков", len(unfinished))
    healed = 0
    for row in unfinished:
        ok = await _fiscalize(
            bot,
            row["payment_id"],
            row["user_id"],
            row["service_name"],
            row["amount"],
            start_attempt=row["attempts"],
        )
        if ok:
            healed += 1
    return healed


async def _fiscalize(
    bot,
    payment_id: int,
    user_id: int,
    service_name: str,
    amount_kopecks: int,
    start_attempt: int = 0,
) -> bool:
    """Пробивает чек с ретраями. True при успехе."""
    amount_rub = kopecks_to_rubles(amount_kopecks)
    attempt = start_attempt

    while attempt < MAX_ATTEMPTS:
        try:
            receipt_uuid, print_url = await npd_client.add_income(
                service_name, amount_rub
            )
        except NpdClientError as exc:
            attempt = record_attempt(payment_id, str(exc))
            logger.warning(
                "НПД: попытка %d/%d для платежа %s не прошла: %s",
                attempt, MAX_ATTEMPTS, payment_id, exc,
            )
            pause = retry_delay(attempt)
            if pause is None:
                break
            await asyncio.sleep(pause)
            continue

        mark_sent(payment_id, receipt_uuid, print_url)
        logger.info(
            "НПД: чек для платежа %s зарегистрирован (%s)",
            payment_id, receipt_uuid,
        )
        await _send_receipt_to_user(bot, user_id, print_url)
        return True

    mark_failed(payment_id)
    logger.error(
        "НПД: чек для платежа %s не пробит после %d попыток",
        payment_id, MAX_ATTEMPTS,
    )
    await _alert_admin(bot, payment_id, user_id, service_name, amount_rub)
    return False


async def _send_receipt_to_user(bot, user_id: int, print_url: str) -> None:
    """Присылает пользователю ссылку на чек отдельным сообщением."""
    try:
        await bot.send_message(
            user_id,
            "🧾 Чек по твоей оплате готов — он зарегистрирован в ФНС.",
            reply_markup=get_receipt_keyboard(print_url),
        )
    except Exception as exc:
        # Юзер мог заблокировать бота — чек всё равно пробит и валиден
        logger.error("НПД: не смог отправить чек юзеру %s: %s", user_id, exc)


async def _alert_admin(
    bot,
    payment_id: int,
    user_id: int,
    service_name: str,
    amount_rub: float,
) -> None:
    """Зовёт админа пробить чек руками."""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ Чек НПД не пробит!\n\n"
            f"Платёж: {payment_id}\n"
            f"Пользователь: {user_id}\n"
            f"Сумма: {amount_rub:.2f} ₽\n"
            f"Наименование: {service_name}\n\n"
            f"Пробей вручную в «Мой налог» "
            f"или повтори через /receipts_retry",
        )
    except Exception as exc:
        logger.error("НПД: не смог уведомить админа: %s", exc)
```

- [ ] **Step 5: Запустить тест и убедиться, что он проходит**

Run: `python3 tests/test_npd_receipts.py`
Expected: PASS для всех 8 тестов, `OK — 0 failure(s)`

- [ ] **Step 6: Коммит**

```bash
git add bot/services/npd_receipts.py bot/keyboards/inline.py tests/test_npd_receipts.py
git commit -m "feat: НПД receipt orchestration with retries and admin alerts"
```

---

### Task 6: Врезка в платёжный флоу

**Files:**
- Modify: `bot/handlers/payment.py:233` (ручная кнопка «Проверить оплату»)
- Modify: `bot/handlers/payment.py:325` (фоновый polling)

**Interfaces:**
- Consumes: `npd_receipts.issue_receipt`
- Produces: ничего нового

- [ ] **Step 1: Добавить импорт**

В `bot/handlers/payment.py`, в блок импортов после `from bot.services.user_limits import (...)`, добавить:

```python
from bot.services.npd_receipts import issue_receipt
```

- [ ] **Step 2: Врезать вызов в ручную ветку**

В `check_payment_status`, в блоке `if status == "succeeded":` — сразу после `success = confirm_payment(internal_id)` и строки `if success and pkg:` вставить первой строкой внутри `if`:

```python
            # Фискализация не блокирует выдачу — отдельной задачей
            asyncio.create_task(
                issue_receipt(callback.bot, internal_id, user_id, pkg)
            )
```

Важно: у `check_payment_status` нет параметра `bot`, поэтому именно `callback.bot`.

- [ ] **Step 3: Врезать вызов в фоновый polling**

В `_poll_payment`, в блоке `if status == "succeeded":` — сразу после `success = confirm_payment(internal_id)` и `if success:` вставить первой строкой внутри `if`:

```python
                asyncio.create_task(
                    issue_receipt(bot, internal_id, user_id, pkg)
                )
```

Здесь `bot` есть в аргументах функции.

- [ ] **Step 4: Проверить, что модуль импортируется без циклов**

Run: `python3 -c "import bot.handlers.payment; print('payment ok')"`
Expected: `payment ok`

Если появится `ImportError` про циклический импорт — проверить, что `npd_receipts.py` не импортирует ничего из `bot.handlers`.

- [ ] **Step 5: Убедиться, что вызовы стоят в обеих ветках**

Run: `grep -n "issue_receipt" bot/handlers/payment.py`
Expected: три строки — импорт и два вызова

- [ ] **Step 6: Коммит**

```bash
git add bot/handlers/payment.py
git commit -m "feat: issue НПД receipt after payment confirmation"
```

---

### Task 7: Админ-команды и запуск

**Files:**
- Create: `bot/handlers/receipts.py`
- Modify: `bot/main.py:11-13` (импорт хендлеров), `bot/main.py:45-54` (роутеры), `bot/main.py` (sweep после старта)

**Interfaces:**
- Consumes: `npd_receipts.retry_pending_receipts`, `npd_storage.get_unfinished_receipts`, `user_limits.is_admin`
- Produces: `router` в `bot/handlers/receipts.py`

- [ ] **Step 1: Написать хендлеры**

Создать `bot/handlers/receipts.py`:

```python
"""Админские команды по чекам НПД: просмотр и добивка незакрытых."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.npd_receipts import retry_pending_receipts
from bot.services.npd_storage import get_unfinished_receipts
from bot.services.user_limits import is_admin

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("receipts_failed"))
async def cmd_receipts_failed(message: Message) -> None:
    """Список незакрытых чеков (только для админа)"""
    if not is_admin(message.from_user.id):
        return

    rows = get_unfinished_receipts()
    if not rows:
        await message.answer("✅ Незакрытых чеков нет.")
        return

    lines = [f"🧾 <b>Незакрытые чеки: {len(rows)}</b>\n"]
    for row in rows[:20]:
        lines.append(
            f"• Платёж {row['payment_id']} — "
            f"{row['amount'] / 100:.2f} ₽, "
            f"{row['status']}, попыток {row['attempts']}\n"
            f"  <i>{row['service_name']}</i>"
        )
    if len(rows) > 20:
        lines.append(f"\n…и ещё {len(rows) - 20}")
    lines.append("\nДобить: /receipts_retry")

    await message.answer("\n".join(lines))


@router.message(Command("receipts_retry"))
async def cmd_receipts_retry(message: Message, bot: Bot) -> None:
    """Принудительная добивка незакрытых чеков (только для админа)"""
    if not is_admin(message.from_user.id):
        return

    pending = len(get_unfinished_receipts())
    if not pending:
        await message.answer("✅ Незакрытых чеков нет.")
        return

    await message.answer(f"⏳ Пробую добить {pending} чеков...")
    healed = await retry_pending_receipts(bot)
    await message.answer(
        f"Готово: пробито {healed} из {pending}.\n"
        f"Остаток смотри в /receipts_failed"
    )
```

- [ ] **Step 2: Зарегистрировать роутер в `main.py`**

В `bot/main.py` заменить импорт хендлеров:

```python
from bot.handlers import (
    admin_test, broadcast, payment, photo, rating, receipts, start, support,
    watermark,
)
```

И добавить регистрацию роутера сразу после `dp.include_router(payment.router)`:

```python
    dp.include_router(receipts.router)
```

- [ ] **Step 3: Добавить sweep незакрытых чеков на старте**

В `bot/main.py`, в блоке `try:` перед `await dp.start_polling(bot)`, добавить:

```python
        # Добиваем чеки, не пробитые до рестарта
        asyncio.create_task(retry_pending_receipts(bot))
```

И импорт рядом с `from bot.services.user_limits import init_db`:

```python
from bot.services.npd_receipts import retry_pending_receipts
```

- [ ] **Step 4: Проверить, что бот собирается**

Run: `python3 -c "import bot.main; print('main ok')"`
Expected: `main ok`

- [ ] **Step 5: Прогнать все тесты**

Run:
```bash
for t in tests/test_*.py; do echo "--- $t"; python3 "$t" || exit 1; done
```
Expected: каждый файл заканчивается `OK — 0 failure(s)`

- [ ] **Step 6: Коммит**

```bash
git add bot/handlers/receipts.py bot/main.py
git commit -m "feat: admin receipt commands and startup sweep"
```

---

### Task 8: Документация

**Files:**
- Modify: `CLAUDE.md` (таблица модулей, раздел про чеки, список таблиц БД, переменные окружения)

**Interfaces:**
- Consumes: всё предыдущее
- Produces: ничего кодового

- [ ] **Step 1: Добавить модули в таблицу «Key modules»**

В `CLAUDE.md`, в таблицу модулей, добавить строки:

```markdown
| `bot/services/npd_payload.py` | Чистые хелперы чеков НПД: тело запроса `/income`, `print_url`, backoff, протухание токена. Ничего не импортирует из `bot.config` — тесты бегут без `.env` |
| `bot/services/npd_client.py` | `NpdClient` — async-клиент `lknpd.nalog.ru`: вход по ИНН+паролю, refresh, `add_income()` |
| `bot/services/npd_storage.py` | CRUD по таблице `npd_receipts` (очередь фискализации) |
| `bot/services/npd_receipts.py` | Оркестрация чеков: очередь, ретраи, ссылка юзеру, алерт админу, sweep на старте |
| `bot/handlers/receipts.py` | Админские `/receipts_failed` и `/receipts_retry` |
```

- [ ] **Step 2: Добавить таблицу в список таблиц БД**

В разделе «Data persistence» добавить:

```markdown
- `npd_receipts(id, payment_id UNIQUE, user_id, amount, service_name, status, receipt_uuid, print_url, attempts, last_error, created_at, updated_at)` — очередь фискализации НПД. `payment_id UNIQUE` защищает от двойного пробития при гонке polling'а с ручной кнопкой «Проверить оплату»
```

- [ ] **Step 3: Добавить переменные окружения**

В раздел «Environment Variables» добавить:

```markdown
- `NPD_ENABLED` — фича-флаг автоматических чеков НПД (по умолчанию `false`)
- `NPD_INN`, `NPD_PASSWORD` — ИНН и пароль от `lknpd.nalog.ru` (вход **по ИНН**, не по SMS)
- `NPD_DEVICE_ID` — стабильный `sourceDeviceId`; токен ФНС привязан к нему, менять между рестартами нельзя
```

- [ ] **Step 4: Добавить раздел про чеки**

В `CLAUDE.md`, после раздела «Payment System», добавить:

```markdown
## Чеки НПД («Мой налог»)

Владелец — **самозанятый**, поэтому чеки по 54-ФЗ через ЮKassa невозможны:
онлайн-кассы нет, а канал чеков для самозанятых ЮKassa **отключила 29.12.2025**.
Доход регистрируется напрямую в ФНС через неофициальный API `lknpd.nalog.ru`.

**Поток:** `confirm_payment()` → `True` → `asyncio.create_task(issue_receipt(...))`
в обеих точках подтверждения ([payment.py:233](bot/handlers/payment.py#L233) ручная
кнопка, [payment.py:325](bot/handlers/payment.py#L325) фоновый polling) → строка в
`npd_receipts` через `INSERT OR IGNORE` → `POST /income` → `approvedReceiptUuid` →
ссылка `https://lknpd.nalog.ru/api/v1/receipt/{ИНН}/{uuid}/print` уходит юзеру
кнопкой «🧾 Открыть чек».

**Ключевой инвариант:** фискализация никогда не блокирует выдачу оплаченного —
вызов всегда fire-and-forget.

**Отказы:** до 6 попыток (немедленная + ретраи 2/5/15/60/300 сек). Исчерпали →
`status='failed'` + алерт админу. При старте бота `retry_pending_receipts()`
добивает всё незакрытое. Вручную — `/receipts_failed` и `/receipts_retry`.

**Токен** живёт ~1 час, привязан к `NPD_DEVICE_ID`. На 401 — прозрачный refresh,
при провале — полный перелогин.

**Ограничения НПД:** лимит 2,4 млн ₽/год, платить могут только физлица. При
подходе к лимиту — переход на ИП, и тогда станет доступен `receipt` в ЮKassa.

**Тесты:** `python3 tests/test_npd_payload.py`, `tests/test_npd_storage.py`,
`tests/test_npd_receipts.py` — все self-contained, без pytest. Первые два бегут
и без `.env` (не тянут `bot.config`); третий требует `.env`, потому что
`npd_receipts.py` импортирует `settings` и клавиатуры aiogram.

**Диагностика:** `sudo journalctl -u photoshoot_ai | grep 'НПД'`

**Design docs:** [docs/superpowers/specs/2026-08-20-npd-receipts-design.md](docs/superpowers/specs/2026-08-20-npd-receipts-design.md)
и [docs/superpowers/plans/2026-08-20-npd-receipts.md](docs/superpowers/plans/2026-08-20-npd-receipts.md).
```

- [ ] **Step 5: Коммит**

```bash
git add CLAUDE.md
git commit -m "docs: document НПД receipt integration"
```

---

## Раскатка на прод (после всех задач, вручную с пользователем)

Не часть автоматической реализации — выполняется вместе с владельцем бота.

1. **Проверить пароль.** Убедиться, что вход на `lknpd.nalog.ru` по ИНН + паролю работает в браузере. Если вход только по SMS/Госуслугам — задать пароль в приложении «Мой налог».
2. **Сгенерировать device id:** `python3 -c "import uuid; print(uuid.uuid4().hex[:21])"`
3. **Задеплоить код с `NPD_ENABLED=false`** — прод работает как раньше. Файлы копировать по одному через `/tmp` + `sudo cp` с проверкой содержимого перед стартом сервиса (рекурсивный `scp -r` может молча не перезаписать — см. CLAUDE.md).
4. **Заполнить `.env`** на сервере: `NPD_INN`, `NPD_PASSWORD`, `NPD_DEVICE_ID`. Проверить `chmod 600`.
5. **Включить `NPD_ENABLED=true`**, перезапустить сервис.
6. **Боевая проверка:** провести реальный платёж 50 ₽ (разблокировка водяного знака), убедиться что пришла кнопка «🧾 Открыть чек», ссылка открывается, и чек виден в приложении «Мой налог».
7. **Проверить логи:** `sudo journalctl -u photoshoot_ai | grep 'НПД'`
