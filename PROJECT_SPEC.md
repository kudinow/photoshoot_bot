# Photoshoot AI Bot — Project Specification

## Обзор проекта

Telegram-бот для трансформации обычных фотографий пользователей в профессиональные студийные снимки с использованием AI (kie.ai / Nano Banana).

---

## Технический стек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.11+ |
| Telegram API | aiogram 3.x |
| HTTP клиент | aiohttp |
| Конфигурация | python-dotenv |
| Валидация | Pydantic |

---

## Архитектура

```
User → Telegram → Bot (aiogram) → kie.ai API → Bot → User
```

### Структура проекта

```
photoshoot_ai/
├── bot/
│   ├── __init__.py
│   ├── main.py                 # Точка входа, инициализация бота
│   ├── config.py               # Настройки из .env
│   │
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py            # /start, онбординг
│   │   └── photo.py            # Приём и обработка фото
│   │
│   ├── states/
│   │   ├── __init__.py
│   │   └── generation.py       # FSM состояния
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── kie_client.py       # Клиент kie.ai API
│   │
│   └── keyboards/
│       ├── __init__.py
│       └── inline.py           # Inline-клавиатуры
│
├── .env                        # Секреты (не в git!)
├── .env.example                # Пример .env
├── requirements.txt
├── PROJECT_SPEC.md             # Этот файл
└── README.md
```

---

## kie.ai API Integration

### Credentials

```
API Key: c0536267e32dedd2c232f2882a6aec08
Base URL: https://kie.ai
```

### Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/jobs/createTask` | POST | Создание задачи на генерацию |
| `/api/v1/jobs/recordInfo` | GET | Проверка статуса задачи |

### Используемая модель

**google/nano-banana-edit** — редактирование изображений с промптом

### Flow работы с API

1. **POST /api/v1/jobs/createTask** — отправляем фото + промпт, получаем task_id
2. **GET /api/v1/jobs/recordInfo?id={task_id}** — polling статуса до завершения
3. Получаем URL результата из ответа

### Параметры запроса

| Параметр | Тип | Описание |
|----------|-----|----------|
| `prompt` | string (required) | Инструкция для трансформации |
| `image_urls` | array (required) | URL изображений (до 10 шт) |
| `output_format` | string | "png" или "jpeg" |
| `image_size` | string | Соотношение сторон |

### Поддерживаемые размеры

- `1:1` — квадрат
- `9:16` — вертикальный (сторис)
- `16:9` — горизонтальный
- `3:4`, `4:3` — классический портрет/ландшафт
- `auto` — автоматически

---

## User Flow

```
┌─────────────────────────────────────────────────────────┐
│  1. START                                               │
│     User: /start                                        │
│     Bot: Приветствие + инструкция                       │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  2. SELECT_GENDER                                       │
│     Bot: "Выберите пол для стиля фото"                 │
│     User: Нажимает кнопку [Мужской] или [Женский]      │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  3. AWAITING_PHOTO                                      │
│     User: Отправляет фото                               │
│     Bot: "Фото получено! Обрабатываю..."               │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  4. PROCESSING                                          │
│     Bot: Загружает фото → отправляет в kie.ai          │
│     Bot: Polling статуса задачи                         │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  5. RESULT                                              │
│     Bot: Отправляет готовое фото                        │
│     Bot: "Хотите обработать ещё?" + кнопки             │
└─────────────────────────────────────────────────────────┘
```

---

## FSM States

```python
class GenerationStates(StatesGroup):
    selecting_gender = State()    # Выбор пола для промпта
    awaiting_photo = State()      # Ждём фото от пользователя
    processing = State()          # Обрабатываем через API
```

---

## Система генерации промптов

### Архитектура

Промпты генерируются динамически через OpenAI GPT-4o-mini на основе системного гайдлайна.

**Файлы:**
- `bot/config.py` — содержит `PROMPT_SYSTEM` (гайдлайн для GPT) и `PROMPT_CRITICAL_SUFFIX`
- `bot/services/openai_client.py` — клиент OpenAI

### Системный гайдлайн (PROMPT_SYSTEM)

Гайдлайн описывает стиль **профессиональной студийной портретной фотографии**:

**Студийная обстановка:**
- Фон: seamless backdrop (белый, серый, чёрный) или градиент
- Освещение: Rembrandt, butterfly, loop, split lighting
- Модификаторы: softbox, beauty dish, rim light

**Одежда и стиль:**
- Женщины: blazer, blouse, tailored dress, элегантные украшения
- Мужчины: suit, dress shirt, smart casual, минимальные аксессуары
- Палитра: navy, burgundy, black, white, emerald, cream

**Технические детали:**
- Кадрирование: headshot (chest-up) или half-body
- Глубина резкости: f/2.8-f/5.6
- Фокус на глазах, catchlights обязательны

### Критический суффикс (PROMPT_CRITICAL_SUFFIX)

Добавляется к каждому промпту для сохранения черт лица:

```
CRITICAL: Preserve the exact facial features, face shape, skin tone, and all
unique characteristics from the original photo. Do not alter, enhance,
beautify, or modify the face in any way. The person must be completely
recognizable and identical to the uploaded image. Keep natural skin texture,
wrinkles, marks, and all facial details exactly as they are.
```

### Flow генерации промпта

1. Пользователь выбирает пол (male/female)
2. `openai_client.generate_prompt(gender)` отправляет запрос в GPT-4o-mini
3. GPT генерирует уникальный промпт на основе гайдлайна
4. К промпту добавляется `PROMPT_CRITICAL_SUFFIX`
5. Готовый промпт отправляется в kie.ai вместе с фото

---

## Environment Variables (.env)

```bash
# Telegram
BOT_TOKEN=your_telegram_bot_token

# kie.ai
KIE_API_KEY=c0536267e32dedd2c232f2882a6aec08
KIE_API_URL=https://api.kie.ai

# OpenAI (для генерации промптов)
OPENAI_API_KEY=your_openai_api_key

# Settings
DEBUG=false
```

---

## Зависимости (requirements.txt)

```
aiogram==3.13.1
aiohttp==3.10.5
python-dotenv==1.0.1
pydantic==2.9.2
pydantic-settings==2.5.2
openai>=1.0.0
```

---

## API Client Interface

```python
class KieClient:
    async def transform_photo(
        self,
        image_url: str,
        prompt: str,
        output_format: str = "jpeg",
        image_size: str = "auto"
    ) -> bytes:
        """
        Отправляет фото в kie.ai и возвращает результат.

        Args:
            image_url: URL исходного изображения
            prompt: Промпт для трансформации
            output_format: Формат выхода (jpeg/png)
            image_size: Соотношение сторон

        Returns:
            bytes: Обработанное изображение
        """
        pass
```

---

## Ограничения и допущения

- **Без монетизации** — все функции бесплатны
- **Без лимитов** — нет ограничений на количество генераций
- **Без хранения** — не сохраняем историю, фото удаляются после обработки
- **Один результат** — на входе 1+ фото, на выходе 1 обработанное фото

---

## TODO перед разработкой

1. [x] Получить токен Telegram бота через @BotFather
2. [x] Уточнить точный endpoint kie.ai API
3. [x] Определить цветовую гамму/стиль для промпта
4. [ ] Протестировать API вручную (curl/Postman) — опционально

---

## Следующие шаги

1. Создать базовую структуру проекта
2. Реализовать конфиг и точку входа
3. Написать клиент kie.ai
4. Реализовать хендлеры бота
5. Протестировать end-to-end

---

*Документ создан: 2026-01-15*
*Последнее обновление: 2026-01-16*
*Версия: 1.1*
