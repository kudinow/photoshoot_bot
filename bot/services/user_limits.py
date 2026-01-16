"""Сервис для отслеживания лимитов генераций пользователей"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Файл для хранения счётчиков (простое решение без БД)
DATA_FILE = Path("/opt/photoshoot_ai/user_generations.json")
# Для локальной разработки
LOCAL_DATA_FILE = Path(__file__).parent.parent.parent / "user_generations.json"

MAX_FREE_GENERATIONS = 3
ADMIN_ID = 91892537


def _get_data_file() -> Path:
    """Возвращает путь к файлу данных"""
    if DATA_FILE.parent.exists():
        return DATA_FILE
    return LOCAL_DATA_FILE


def _load_data() -> dict:
    """Загружает данные о генерациях"""
    data_file = _get_data_file()
    if data_file.exists():
        try:
            return json.loads(data_file.read_text())
        except Exception as e:
            logger.error(f"Error loading user data: {e}")
    return {}


def _save_data(data: dict) -> None:
    """Сохраняет данные о генерациях"""
    data_file = _get_data_file()
    try:
        data_file.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.error(f"Error saving user data: {e}")


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID


def get_generations_count(user_id: int) -> int:
    """Возвращает количество использованных генераций"""
    data = _load_data()
    return data.get(str(user_id), 0)


def get_remaining_generations(user_id: int) -> int:
    """Возвращает количество оставшихся генераций"""
    if is_admin(user_id):
        return -1  # Безлимит
    used = get_generations_count(user_id)
    return max(0, MAX_FREE_GENERATIONS - used)


def can_generate(user_id: int) -> bool:
    """Проверяет, может ли пользователь генерировать"""
    if is_admin(user_id):
        return True
    return get_remaining_generations(user_id) > 0


def increment_generations(user_id: int) -> None:
    """Увеличивает счётчик генераций пользователя"""
    if is_admin(user_id):
        return  # Админу не считаем

    data = _load_data()
    current = data.get(str(user_id), 0)
    data[str(user_id)] = current + 1
    _save_data(data)
    logger.info(f"User {user_id} generations: {current + 1}/{MAX_FREE_GENERATIONS}")
