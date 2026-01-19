import asyncio
import logging

from openai import AsyncOpenAI

from bot.config import PROMPT_CRITICAL_SUFFIX, PROMPT_SYSTEM, settings

logger = logging.getLogger(__name__)


class OpenAIClientError(Exception):
    """Ошибка клиента OpenAI/OpenRouter"""

    pass


class OpenAIClient:
    """Клиент для генерации промптов через OpenRouter API.

    Совместим с OpenAI SDK.
    """

    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        # OpenRouter использует тот же формат модели
        # GPT-5.2 для максимального качества генерации промптов
        self.model = "openai/gpt-5.2"

    async def generate_prompt(self, gender: str, max_retries: int = 3) -> str:
        """
        Генерирует промпт для изображения на основе пола.

        Args:
            gender: "male" или "female"
            max_retries: максимальное количество попыток

        Returns:
            Сгенерированный промпт для kie.ai
        """
        gender_text = "мужчины" if gender == "male" else "женщины"

        user_message = (
            f"Сгенерируй один уникальный промпт для профессионального "
            f"студийного портрета {gender_text}. "
            f"Следуй структуре промпта из гайдлайнов. "
            f"ВАЖНО: Выбери РАЗНЫЕ предметы одежды, цвет и текстуру, "
            f"чем в предыдущих примерах. "
            f"Создай оригинальную комбинацию из расширенного списка "
            f"casual/smart casual одежды. "
            f"Верни ТОЛЬКО текст промпта на английском, без пояснений."
        )

        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Generating prompt for {gender}, "
                    f"attempt {attempt + 1}/{max_retries}"
                )

                response = await self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=500,
                    messages=[
                        {"role": "system", "content": PROMPT_SYSTEM},
                        {"role": "user", "content": user_message},
                    ],
                )

                generated_prompt = (
                    response.choices[0].message.content.strip()
                )
                full_prompt = generated_prompt + PROMPT_CRITICAL_SUFFIX

                logger.info(
                    f"Generated prompt for {gender}: "
                    f"{generated_prompt[:100]}..."
                )

                return full_prompt

            except Exception as e:
                last_error = e
                logger.error(
                    f"OpenAI API error (attempt {attempt + 1}/"
                    f"{max_retries}): {type(e).__name__}: {e}"
                )
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(2 ** attempt)

        logger.error(
            f"OpenAI API failed after {max_retries} attempts: "
            f"{last_error}"
        )
        raise OpenAIClientError(
            f"Ошибка генерации промпта: {last_error}"
        ) from last_error


openai_client = OpenAIClient()
