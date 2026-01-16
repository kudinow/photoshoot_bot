import logging

from openai import AsyncOpenAI

from bot.config import PROMPT_CRITICAL_SUFFIX, PROMPT_SYSTEM, settings

logger = logging.getLogger(__name__)


class OpenAIClientError(Exception):
    """Ошибка клиента OpenAI"""

    pass


class OpenAIClient:
    """Клиент для генерации промптов через OpenAI API"""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"

    async def generate_prompt(self, gender: str) -> str:
        """
        Генерирует промпт для изображения на основе пола.

        Args:
            gender: "male" или "female"

        Returns:
            Сгенерированный промпт для kie.ai
        """
        gender_text = "мужчины" if gender == "male" else "женщины"

        user_message = (
            f"Сгенерируй один промпт для профессионального студийного портрета {gender_text}. "
            f"Следуй структуре промпта из гайдлайнов. "
            f"Верни ТОЛЬКО текст промпта на английском, без пояснений."
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
            )

            generated_prompt = response.choices[0].message.content.strip()
            full_prompt = generated_prompt + PROMPT_CRITICAL_SUFFIX

            logger.info(f"Generated prompt for {gender}: {generated_prompt[:100]}...")

            return full_prompt

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise OpenAIClientError(f"Ошибка генерации промпта: {e}") from e


openai_client = OpenAIClient()
