import asyncio
import logging
from typing import Optional

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


class KieClientError(Exception):
    """Ошибка клиента kie.ai"""
    pass


class KieClient:
    """Клиент для работы с kie.ai API"""

    def __init__(self):
        self.base_url = settings.kie_api_url
        self.api_key = settings.kie_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_task(
        self,
        image_url: str,
        prompt: str,
        output_format: str = "jpeg",
        image_size: str = "auto",
    ) -> str:
        """
        Создаёт задачу на генерацию изображения.

        Args:
            image_url: URL исходного изображения
            prompt: Промпт для трансформации
            output_format: Формат выхода (jpeg/png)
            image_size: Соотношение сторон

        Returns:
            str: ID созданной задачи
        """
        url = f"{self.base_url}/api/v1/jobs/createTask"

        payload = {
            "model": "google/nano-banana-edit",
            "input": {
                "prompt": prompt,
                "image_urls": [image_url],
                "output_format": output_format,
                "image_size": image_size,
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Failed to create task: {resp.status} - {text}")
                    raise KieClientError(f"Failed to create task: {resp.status}")

                data = await resp.json()

                # Ответ: {"code": 200, "message": "success", "data": {"taskId": "..."}}
                if data.get("code") != 200:
                    raise KieClientError(f"API error: {data.get('message')}")

                task_id = data.get("data", {}).get("taskId")

                if not task_id:
                    logger.error(f"No taskId in response: {data}")
                    raise KieClientError("No taskId in response")

                logger.info(f"Created task: {task_id}")
                return task_id

    async def get_task_status(self, task_id: str) -> dict:
        """
        Получает статус задачи.

        Args:
            task_id: ID задачи

        Returns:
            dict: Информация о задаче (поле data из ответа)
        """
        url = f"{self.base_url}/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self.headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Failed to get task status: {resp.status} - {text}")
                    raise KieClientError(f"Failed to get task status: {resp.status}")

                response = await resp.json()
                return response.get("data", {})

    async def wait_for_result(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: int = 3,
    ) -> str:
        """
        Ожидает завершения задачи и возвращает URL результата.

        Args:
            task_id: ID задачи
            timeout: Максимальное время ожидания в секундах
            poll_interval: Интервал между проверками в секундах

        Returns:
            str: URL готового изображения
        """
        import json

        elapsed = 0

        while elapsed < timeout:
            data = await self.get_task_status(task_id)
            logger.debug(f"Task {task_id} status: {data}")

            state = data.get("state")

            if state == "success":
                # resultJson содержит JSON-строку: {"resultUrls": ["https://..."]}
                result_json_str = data.get("resultJson")
                if result_json_str:
                    try:
                        result_data = json.loads(result_json_str)
                        result_urls = result_data.get("resultUrls", [])
                        if result_urls:
                            logger.info(f"Task {task_id} completed: {result_urls[0]}")
                            return result_urls[0]
                    except json.JSONDecodeError:
                        pass

                raise KieClientError(f"Task completed but no result URL: {data}")

            if state == "fail":
                fail_msg = data.get("failMsg") or "Unknown error"
                raise KieClientError(f"Task failed: {fail_msg}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise KieClientError(f"Task {task_id} timed out after {timeout}s")

    async def transform_photo(
        self,
        image_url: str,
        prompt: str,
        output_format: str = "jpeg",
        image_size: str = "auto",
    ) -> str:
        """
        Полный цикл трансформации фото: создание задачи и ожидание результата.

        Args:
            image_url: URL исходного изображения
            prompt: Промпт для трансформации
            output_format: Формат выхода (jpeg/png)
            image_size: Соотношение сторон

        Returns:
            str: URL готового изображения
        """
        task_id = await self.create_task(image_url, prompt, output_format, image_size)
        return await self.wait_for_result(task_id)

    async def download_image(self, url: str) -> bytes:
        """
        Скачивает изображение по URL.

        Args:
            url: URL изображения

        Returns:
            bytes: Содержимое изображения
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise KieClientError(f"Failed to download image: {resp.status}")
                return await resp.read()


# Singleton instance
kie_client = KieClient()
