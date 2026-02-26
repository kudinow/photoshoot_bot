from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    """Состояния для процесса генерации фото"""

    selecting_gender = State()  # Выбор пола для промпта
    selecting_style = State()   # Выбор стиля одежды
    awaiting_photo = State()    # Ждём фото от пользователя
    processing = State()        # Обрабатываем через API
