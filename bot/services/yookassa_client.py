"""Сервис для работы с YooKassa API"""

from __future__ import annotations

import asyncio
import logging
import uuid
from functools import partial

from yookassa import Payment

from bot.config import settings

logger = logging.getLogger(__name__)


async def create_yookassa_payment(
    amount_kopecks: int,
    description: str,
    user_id: int,
    package_id: str,
    internal_payment_id: int,
) -> tuple[str, str]:
    """
    Создаёт платёж в YooKassa.

    Возвращает (yookassa_payment_id, confirmation_url).
    """
    amount_rub = f"{amount_kopecks / 100:.2f}"

    payment_data = {
        "amount": {
            "value": amount_rub,
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": settings.yookassa_return_url,
        },
        "capture": True,
        "description": description,
        "metadata": {
            "user_id": str(user_id),
            "package_id": package_id,
            "internal_payment_id": str(internal_payment_id),
        },
    }

    idempotency_key = str(uuid.uuid4())

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        partial(Payment.create, payment_data, idempotency_key),
    )

    logger.info(
        f"YooKassa payment created: {response.id} "
        f"for user {user_id}, amount {amount_rub} RUB"
    )

    return response.id, response.confirmation.confirmation_url


async def check_yookassa_payment(
    yookassa_payment_id: str,
) -> str:
    """
    Проверяет статус платежа в YooKassa.

    Возвращает статус: 'pending', 'succeeded', 'canceled',
    'waiting_for_capture'.
    """
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        partial(Payment.find_one, yookassa_payment_id),
    )

    logger.debug(
        f"YooKassa payment {yookassa_payment_id} "
        f"status: {response.status}"
    )

    return response.status
