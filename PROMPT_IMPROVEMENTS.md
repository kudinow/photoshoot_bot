# Улучшения системных промптов для разнообразия одежды

## Дата: 2026-01-19

## Проблема
Бот генерировал фотографии с однообразной одеждой - пользователи часто получали портреты с похожими предметами гардероба и цветами.

## Решение

### 1. Расширение списка одежды

#### Для женщин (добавлено):
- Casual knit sweaters (различные вырезы и фасоны)
- Soft cardigans (разные стили)
- Cotton t-shirts (базовые футболки)
- Chambray/denim shirts (рубашки в стиле денима)
- Linen blouses (льняные блузки)
- Henley tops
- Jersey wrap tops
- Lightweight hoodies (минималистичные худи)

#### Для мужчин (добавлено):
- Casual sweaters (включая quarter-zip, cardigan)
- Cotton t-shirts (включая henley, pocket tee)
- Button-up shirts (Oxford, chambray, denim, flannel, linen)
- Polo shirts
- Lightweight hoodies
- Casual jackets (denim, bomber, shirt jacket, field jacket)
- Layered looks (многослойные образы)

### 2. Расширение цветовой палитры

**Сохранена нюдовая/пастельная эстетика, но добавлено больше вариантов:**

#### Neutrals (нейтральные):
cream, ivory, beige, oatmeal, sand, warm grey, cool grey, charcoal grey, soft white, off-white, black

#### Earth tones (земляные):
olive, sage green, moss green, forest green, terracotta, rust, clay, dusty rose, camel, brown tones

#### Muted pastels (приглушенные пастели):
powder blue, sky blue, dusty pink, lavender, mint, peach, soft coral

#### Soft brights (мягкие яркие):
muted mustard, soft burgundy, mauve, warm taupe, burgundy, maroon

### 3. Добавлены инструкции о разнообразии

В начало `PROMPT_SYSTEM` добавлено:
```
IMPORTANT: Generate DIVERSE and VARIED clothing combinations for each request.
Never repeat the same garment or color combination. Mix and match different
styles, colors, and textures to create unique looks every time.
```

В конец промпта добавлен раздел:
```
CRITICAL INSTRUCTION FOR DIVERSITY:
Each time you generate a prompt, you MUST:
1. Choose a DIFFERENT garment type than recent prompts
2. Select a DIFFERENT color from the expanded palette
3. Vary textures and fabric types
4. Mix up accessories and styling details
5. Create UNIQUE combinations — never repeat the same outfit formula
6. Think creatively about layering and style variations
```

### 4. Обновление модели AI

Модель обновлена с `openai/gpt-4o-mini` на `openai/gpt-5.2` через OpenRouter для максимального качества генерации промптов и лучшего понимания инструкций о разнообразии.

### 5. Улучшение user message в генерации

Обновлен запрос к GPT-5.2:
```python
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
```

### 6. Фокус на casual/smart casual стиле

**Полностью исключена деловая одежда:**
- ❌ Нет костюмов
- ❌ Нет галстуков
- ❌ Нет формальных блейзеров
- ✅ Только casual и smart casual стиль

### 7. Расширены примеры промптов

- **Женщины**: 6 примеров (было 4)
- **Мужчины**: 7 примеров (было 5)

Каждый пример демонстрирует уникальную комбинацию одежды, цвета и стиля.

## Измененные файлы

1. **[bot/config.py](bot/config.py)** - обновлен `PROMPT_SYSTEM`
2. **[bot/services/openai_client.py](bot/services/openai_client.py)** - улучшен `user_message` с акцентом на разнообразие

## Ожидаемый результат

После этих изменений бот должен генерировать:
- ✅ Большое разнообразие предметов одежды
- ✅ Различные цветовые комбинации (в рамках нюдовой палитры)
- ✅ Уникальные образы для каждого запроса
- ✅ Сохранение визуального стиля студийных портретов
- ✅ Только casual и smart casual одежда

## Как проверить

1. Запустите бота
2. Сгенерируйте несколько портретов подряд для одного пола
3. Убедитесь, что одежда, цвета и стили различаются
4. Проверьте, что визуальный стиль (освещение, фон, композиция) остается консистентным

## Технические улучшения

### Использование GPT-5.2
Модель GPT-5.2 обеспечивает:
- Более точное следование сложным инструкциям о разнообразии
- Лучшее понимание контекста и нюансов casual/smart casual стиля
- Повышенную креативность в комбинировании элементов одежды
- Более последовательное соблюдение ограничений (никакой деловой одежды)

## Дальнейшие улучшения (опционально)

Если разнообразие все еще недостаточное, можно:
- Добавить параметр `temperature` в OpenAI API (например, 0.8-0.9 для большей креативности)
- Добавить систему отслеживания последних N сгенерированных промптов и передавать их в контекст с инструкцией "не повторять эти комбинации"
