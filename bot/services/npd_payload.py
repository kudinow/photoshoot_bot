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
