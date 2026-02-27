from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """Состояния для процесса рассылки (только для администратора)"""

    choosing_segment = State()    # Выбор сегмента пользователей
    composing_message = State()   # Ввод текста сообщения
    confirming = State()          # Подтверждение перед отправкой
