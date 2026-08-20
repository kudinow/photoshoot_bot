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
