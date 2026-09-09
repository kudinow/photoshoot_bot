import asyncio
import logging
import signal
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import (
    admin_test, broadcast, payment, photo, rating, receipts, start, support,
    watermark,
)
from bot.services.npd_receipts import retry_pending_receipts
from bot.services.user_limits import init_db


# Паузы перед повторным запуском polling'а, если его уронила сеть
POLLING_RETRY_DELAYS = (5, 10, 20, 30, 60)


def setup_logging() -> None:
    """Настройка логирования"""
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def main() -> None:
    """Точка входа"""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting bot...")

    # Инициализируем БД
    init_db()

    # Создаём бота и диспетчер
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем роутеры
    dp.include_router(start.router)
    # support ДО photo: InSupportSession перехватывает текст/фото активной сессии
    dp.include_router(support.router)
    dp.include_router(broadcast.router)
    dp.include_router(payment.router)
    dp.include_router(receipts.router)
    dp.include_router(rating.router)
    dp.include_router(watermark.router)
    # admin_test ДО photo: photo.router имеет catch-all F.photo без FSM-фильтра
    dp.include_router(admin_test.router)
    dp.include_router(photo.router)

    # Запускаем бота.
    #
    # Сеть до api.telegram.org периодически виснет наглухо (выборочный DPI:
    # ICMP идёт, HTTPS таймаутится примерно в одном запросе из трёх). aiogram
    # переживает такое внутри _listen_updates, но самый первый bot.me() в
    # начале _polling ничем не защищён — его таймаут выходит наружу из
    # start_polling и роняет процесс. Без этой обёртки systemd крутит
    # рестарты, пока старт случайно не попадёт в живое окно.
    #
    # close_bot_session=False: иначе aiogram закроет сессию на выходе, и
    # повторный запуск пойдёт по закрытой. Закрываем её сами в finally.
    #
    # handle_signals=False и свои обработчики: штатный обработчик aiogram
    # работает, только пока polling реально крутится, и молча теряет SIGTERM
    # во время паузы между попытками — systemctl stop висел бы до SIGKILL.
    stop_requested = asyncio.Event()

    async def stop_polling_safely() -> None:
        with suppress(RuntimeError):  # polling мог ещё не стартовать
            await dp.stop_polling()

    def request_stop(sig: signal.Signals) -> None:
        logger.warning(f"Received {sig.name} signal, shutting down")
        stop_requested.set()
        asyncio.create_task(stop_polling_safely())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):  # Windows
            loop.add_signal_handler(sig, request_stop, sig)

    try:
        logger.info("Bot started successfully!")
        # Добиваем чеки, не пробитые до рестарта
        asyncio.create_task(retry_pending_receipts(bot))

        attempt = 0
        while not stop_requested.is_set():
            try:
                await dp.start_polling(
                    bot, close_bot_session=False, handle_signals=False
                )
                break  # штатная остановка
            except TelegramNetworkError as e:
                delay = POLLING_RETRY_DELAYS[
                    min(attempt, len(POLLING_RETRY_DELAYS) - 1)
                ]
                attempt += 1
                logger.warning(
                    f"Polling dropped by network error: {e}. "
                    f"Restarting in {delay}s (attempt {attempt})"
                )
                # Ждём паузу, но просыпаемся сразу, если попросили остановиться
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop_requested.wait(), timeout=delay)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
