# Changelog - 19 января 2026

## Сессия: Настройка GitHub и деплой обновлений

### 1. Улучшения промпта в bot/config.py

**Коммит:** `ddf94b4` - "Improve prompt to preserve original hairstyles and prevent unwanted accessories"

#### Основные изменения в PROMPT_SYSTEM:

**Сохранение оригинальной прически:**
- Добавлена инструкция: "Hair: Keep original hairstyle from photo - only minor grooming improvements allowed"
- Удалены все конкретные примеры причесок (loose waves, messy bun, etc.)
- Разрешены только минимальные улучшения, как будто человек причесался

**Запрет на добавление аксессуаров:**
- Добавлено: "NEVER add glasses if not in original photo"
- Для женщин: "earrings only for face" - можно добавлять только серьги
- Для мужчин: "NO facial accessories unless present in original" - никаких аксессуаров на лице

**Улучшения в Universal Prompt Template:**
- Обновлен шаблон: вместо [Styling details: hair, accessories, grooming - VARY THESE]
- Стало: [Styling details: accessories, grooming - VARY THESE, but NEVER change hairstyle or add glasses if not in original]

#### Расширенные инструкции в PROMPT_CRITICAL_SUFFIX:

**До:**
```
CRITICAL: Preserve the exact facial features, face shape, skin tone, eye color, hair color,
and all unique characteristics from the original photo. Do not alter, enhance, beautify, or
modify the face in any way. Never change eye color or hair color. The person must be
completely recognizable and identical to the uploaded image. Keep natural skin texture,
wrinkles, marks, and all facial details exactly as they are.
```

**После:**
```
CRITICAL FACE AND APPEARANCE PRESERVATION REQUIREMENTS:
Preserve the exact facial features, face shape, skin tone, eye color, hair color, hairstyle,
and all unique characteristics from the original photo. Do not alter, enhance, beautify, or
modify the face in any way. Never change eye color or hair color under any circumstances.
Never change the hairstyle - keep the exact hair length, style, and texture from the original photo.
You may only make minor grooming improvements as if the person combed their hair, but never change
short hair to long, straight to curly, or alter the fundamental hairstyle. If a man has short hair,
keep it short. If a woman has long hair, keep it long. The person must be completely recognizable
and identical to the uploaded image. Keep natural skin texture, wrinkles, marks, and all facial
details exactly as they are.

Never add glasses or any facial accessories if they are not present in the original photo.
For women, earrings may be added as the only acceptable facial accessory. For men, no facial
accessories should be added at all if not present in the original.
```

**Ключевые добавления:**
1. Явное упоминание "hairstyle" в списке сохраняемых характеристик
2. Детальные инструкции о том, что можно (причесать) и нельзя (изменить длину, стиль, текстуру)
3. Конкретные примеры: "never change short hair to long, straight to curly"
4. Четкое разделение политики аксессуаров для мужчин и женщин
5. Усиление формулировок: "under any circumstances", "Never change the hairstyle"

#### Улучшения форматирования:

- Удалены лишние пустые строки для лучшей читаемости
- Улучшена структура списков (bullets переделаны в обычные строки для части секций)
- Более консистентное форматирование инструкций для разнообразия

### 2. Настройка GitHub репозитория

**Репозиторий:** https://github.com/kudinow/photoshoot_bot

**Выполненные действия:**

1. **Добавлен SSH ключ на GitHub:**
   - Ключ: `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKnbQFHD4NnXM3PaAaTZbaE28SYZmsFtYFf/C4kQK8PS`
   - Настроен на локальной машине

2. **Инициализирован Git репозиторий:**
   ```bash
   git remote add origin git@github.com:kudinow/photoshoot_bot.git
   git push -u origin main
   ```

3. **Отправлены все коммиты:**
   - `04afb93` - Improve clothing diversity in generated photos with GPT-5.2
   - `e0ec2b4` - Update PROJECT_STATUS.md with deployment and limits info
   - `12891d3` - Initial commit: Photoshoot AI Bot with user limits
   - `ddf94b4` - Improve prompt to preserve original hairstyles and prevent unwanted accessories

### 3. Деплой на сервер

**Сервер:** `89.169.163.73` (kudinow@89.169.163.73)

**Выполненные действия:**

1. **Настроен Git на сервере:**
   ```bash
   cd /opt/photoshoot_ai
   sudo -u deploy git init
   sudo -u deploy git remote add origin https://github.com/kudinow/photoshoot_bot.git
   ```

2. **Подтянуты изменения с GitHub:**
   ```bash
   sudo -u deploy git fetch origin main
   sudo -u deploy git reset --hard origin/main
   ```
   - HEAD установлен на коммит `ddf94b4`

3. **Перезапущен бот:**
   ```bash
   sudo systemctl restart photoshoot_ai
   ```
   - Статус: `active (running)`
   - Бот: `@photoshoot_generator_bot`

### 4. Структура проекта на сервере

```
/opt/photoshoot_ai/
├── .git/                    # Git репозиторий (добавлен)
├── bot/
│   ├── config.py           # Обновлен промпт
│   ├── handlers/
│   │   └── photo.py
│   ├── main.py
│   └── ...
├── venv/
├── .env
└── requirements.txt
```

### 5. Текущее состояние

**GitHub:**
- ✅ Репозиторий создан и настроен
- ✅ Все изменения отправлены
- ✅ SSH ключ добавлен для локальной машины

**Сервер:**
- ✅ Git репозиторий инициализирован
- ✅ Подключен к GitHub (HTTPS)
- ✅ Код синхронизирован с main веткой
- ✅ Бот работает с обновленным промптом

**Бот:**
- ✅ Использует новый промпт с улучшенными инструкциями
- ✅ Сохраняет оригинальную прическу
- ✅ Не добавляет очки, если их нет в оригинале
- ✅ Корректно работает с аксессуарами для женщин/мужчин

## Команды для будущих обновлений

### На локальной машине:

```bash
# Внести изменения в код
cd /Users/kudinow/Documents/Cursor_PRO/photoshoot_ai

# Закоммитить
git add .
git commit -m "Описание изменений"

# Отправить на GitHub
git push origin main
```

### На сервере:

```bash
# Подключиться
ssh kudinow@89.169.163.73

# Остановить бота
sudo systemctl stop photoshoot_ai

# Обновить код
cd /opt/photoshoot_ai
sudo -u deploy git pull origin main

# Если изменились зависимости
sudo -u deploy /opt/photoshoot_ai/venv/bin/pip install -r requirements.txt

# Запустить бота
sudo systemctl start photoshoot_ai

# Проверить статус
sudo systemctl status photoshoot_ai

# Посмотреть логи
sudo journalctl -u photoshoot_ai -f
```

## Важные заметки

1. **Git на сервере настроен через HTTPS** (не SSH), так как у пользователя `deploy` нет домашней директории
2. **SSH ключ добавлен только на локальной машине**, на сервере используется публичный доступ к репозиторию
3. **Бот автоматически запускается при старте сервера** (enabled в systemd)
4. **Все изменения в bot/config.py вступают в силу только после перезапуска бота**

## Следующие шаги (рекомендации)

1. Протестировать новый промпт на нескольких фото с разными прическами
2. Проверить, что очки не добавляются на фото без очков
3. Убедиться, что прическа остается оригинальной (короткая остается короткой, длинная - длинной)
4. При необходимости дальше уточнить промпт на основе результатов тестирования

## Технические детали

- **Python версия:** 3.9
- **Systemd сервис:** photoshoot_ai.service
- **Рабочая директория:** /opt/photoshoot_ai
- **Пользователь для запуска:** deploy
- **Метод обновления:** Git pull from GitHub
- **Логи:** journalctl -u photoshoot_ai

## Контакты и ссылки

- **GitHub репозиторий:** https://github.com/kudinow/photoshoot_bot
- **Сервер:** 89.169.163.73
- **Telegram бот:** @photoshoot_generator_bot
- **Документация по деплою:** DEPLOY.md, SERVER_COMMANDS.md, UPDATE_DEPLOY.md
