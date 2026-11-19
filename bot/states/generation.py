from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    """Состояния для процесса генерации фото"""

    selecting_gender = State()  # Выбор пола для промпта
    selecting_style = State()   # Выбор стиля одежды
    awaiting_photo = State()    # Ждём фото от пользователя
    processing = State()        # Обрабатываем через API
    awaiting_feedback_text = State()  # Ждём текст фидбека после низкой оценки


class AdminTestStates(StatesGroup):
    """Состояния для админского теста модели GPT Image 2 (/test_gpt)"""

    selecting_gender = State()
    selecting_style = State()
    awaiting_photo = State()
    processing = State()


class ModelTestStates(StatesGroup):
    """Состояния админского сравнения моделей kie.ai (/test_models)"""

    selecting_gender = State()
    selecting_style = State()
    selecting_models = State()
    awaiting_photo = State()
    processing = State()
