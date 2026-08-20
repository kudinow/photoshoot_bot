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
) -> bool:
    """Пробивает чек с ретраями. True при успехе.

    Бюджет попыток локальный и всегда свежий: sweep и /receipts_retry —
    это новый заход, иначе исчерпанный чек нельзя было бы починить уже
    никогда. В БД параллельно копится пожизненный счётчик попыток.
    """
    amount_rub = kopecks_to_rubles(amount_kopecks)
    tries = 0

    while tries < MAX_ATTEMPTS:
        try:
            receipt_uuid, print_url = await npd_client.add_income(
                service_name, amount_rub
            )
        except NpdClientError as exc:
            tries += 1
            total = record_attempt(payment_id, str(exc))
            logger.warning(
                "НПД: попытка %d/%d (всего %d) для платежа %s не прошла: %s",
                tries, MAX_ATTEMPTS, total, payment_id, exc,
            )
            pause = retry_delay(tries)
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
