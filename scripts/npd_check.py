#!/usr/bin/env python3
"""Диагностика интеграции с «Мой налог» (lknpd.nalog.ru).

Два режима:

  auth    — только вход по ИНН+паролю. Ничего не создаёт, налог не начисляет.
            С этого всегда начинай: проверяет креды, device id и доступность API.

  income  — создаёт РЕАЛЬНЫЙ чек на указанную сумму. Это настоящий доход
            в ФНС с настоящим налогом. Требует флага --yes-real-income.
            Аннулировать потом — в приложении «Мой налог».

Примеры:
    python3 scripts/npd_check.py auth
    python3 scripts/npd_check.py income --amount 10 --yes-real-income
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import settings  # noqa: E402
from bot.services.npd_client import NpdClientError, npd_client  # noqa: E402

DEFAULT_SERVICE_NAME = "Обработка фотографии (проверка интеграции)"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _check_env() -> bool:
    """Проверяет, что креды заданы. Пароль не печатаем."""
    ok = True
    print("Конфигурация:")
    print(f"  NPD_INN       = {settings.npd_inn or '(пусто)'}")
    print(f"  NPD_PASSWORD  = {'задан' if settings.npd_password else '(пусто)'}")
    print(f"  NPD_DEVICE_ID = {settings.npd_device_id or '(пусто — будет сгенерирован)'}")
    print(f"  NPD_ENABLED   = {settings.npd_enabled}  (на этот скрипт не влияет)")
    print()

    if not settings.npd_inn or not settings.npd_password:
        print("✗ NPD_INN и NPD_PASSWORD обязательны. Заполни .env и повтори.")
        ok = False
    if not settings.npd_device_id:
        print("⚠ NPD_DEVICE_ID пуст — device id будет разный при каждом запуске,")
        print("  и ФНС будет считать это новым входом. Для прода впиши его в .env.")
        print()
    return ok


async def cmd_auth() -> int:
    """Только логин. Ничего не создаёт."""
    print("Пробую войти в «Мой налог»...\n")
    try:
        await npd_client._authenticate()
    except NpdClientError as exc:
        print(f"\n✗ Вход не удался: {exc}\n")
        print("Что проверить:")
        print("  • Пароль задан именно для входа ПО ИНН на lknpd.nalog.ru?")
        print("    Вход по SMS или через Госуслуги здесь не работает —")
        print("    пароль надо один раз задать в приложении «Мой налог».")
        print("  • ИНН введён без пробелов и лишних символов?")
        print("  • Статус самозанятого активен?")
        return 1

    print("\n✓ Вход выполнен.")
    print(f"  ИНН из профиля : {npd_client._inn}")
    print(f"  Токен получен  : {'да' if npd_client._token else 'нет'}")
    print(f"  Refresh-токен  : {'да' if npd_client._refresh_token else 'нет'}")
    print(f"  Device id      : {npd_client._device_id}")
    print("\nАвторизация работает. Чек при этом НЕ создавался.")
    return 0


async def cmd_income(amount: float, service_name: str) -> int:
    """Создаёт реальный чек."""
    print(f"Создаю РЕАЛЬНЫЙ чек на {amount:.2f} ₽...")
    print(f"Наименование: {service_name}\n")
    try:
        receipt_uuid, print_url = await npd_client.add_income(
            service_name, amount
        )
    except NpdClientError as exc:
        print(f"\n✗ Чек не создан: {exc}")
        return 1

    print("\n✓ Чек зарегистрирован в ФНС.")
    print(f"  UUID   : {receipt_uuid}")
    print(f"  Ссылка : {print_url}")
    print("\nОткрой ссылку и проверь, что чек отображается.")
    print("Он уже виден в приложении «Мой налог» и учтён как доход.")
    print("Чтобы убрать — аннулируй его там же ('Чек сформирован ошибочно').")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Диагностика интеграции с «Мой налог»"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("auth", help="только вход, ничего не создаёт")

    p_income = sub.add_parser("income", help="создать РЕАЛЬНЫЙ чек")
    p_income.add_argument(
        "--amount", type=float, required=True, help="сумма в рублях"
    )
    p_income.add_argument(
        "--name", default=DEFAULT_SERVICE_NAME, help="наименование услуги"
    )
    p_income.add_argument(
        "--yes-real-income",
        action="store_true",
        help="подтверждение: это реальный доход с реальным налогом",
    )

    args = parser.parse_args()
    _configure_logging()

    if not _check_env():
        return 1

    if args.mode == "auth":
        return asyncio.run(cmd_auth())

    if not args.yes_real_income:
        print("✗ Режим income создаёт РЕАЛЬНЫЙ чек в ФНС с реальным налогом.")
        print("  Песочницы у «Мой налог» нет.")
        print("  Если понимаешь — добавь флаг --yes-real-income")
        return 1

    return asyncio.run(cmd_income(args.amount, args.name))


if __name__ == "__main__":
    sys.exit(main())
