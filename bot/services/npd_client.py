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
