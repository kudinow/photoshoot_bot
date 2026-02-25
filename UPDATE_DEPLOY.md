# Инструкция по обновлению бота на сервере

## Статус
✅ Архив с обновлениями скопирован на сервер: `/tmp/photoshoot_ai_update.tar.gz`

## Что изменилось

- Обновлена модель AI с GPT-4o-mini на GPT-5.2
- Расширен список одежды (casual/smart casual)
- Расширена цветовая палитра (~30 цветов)
- Добавлены инструкции о разнообразии в системный промпт
- Улучшен механизм retry с exponential backoff

## Шаги для обновления

### 1. Подключиться к серверу

```bash
ssh kudinow@89.169.163.73
```

### 2. Остановить бота

```bash
sudo systemctl stop photoshoot_ai
```

### 3. Распаковать обновления

```bash
cd /tmp
tar -xzvf photoshoot_ai_update.tar.gz
```

### 4. Обновить файлы бота

```bash
# Бэкап текущей версии (на всякий случай)
sudo cp -r /opt/photoshoot_ai/bot /opt/photoshoot_ai/bot.backup_$(date +%Y%m%d_%H%M%S)

# Обновить файлы
sudo cp -r photoshoot_ai/bot/* /opt/photoshoot_ai/bot/
sudo cp photoshoot_ai/PROMPT_IMPROVEMENTS.md /opt/photoshoot_ai/

# Установить правильные права
sudo chown -R deploy:deploy /opt/photoshoot_ai
```

### 5. Обновить .env файл (КРИТИЧЕСКИ ВАЖНО!)

Нужно обновить переменные для работы с OpenRouter вместо OpenAI:

```bash
sudo nano /opt/photoshoot_ai/.env
```

**Замените:**
```env
# OpenAI
OPENAI_API_KEY=ваш_старый_ключ
```

**На:**
```env
# OpenRouter (замена OpenAI для работы из РФ)
OPENROUTER_API_KEY=ваш_ключ_openrouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

**Где взять OPENROUTER_API_KEY:**
1. Зайдите на https://openrouter.ai/
2. Зарегистрируйтесь/войдите
3. Перейдите в Keys → Create Key
4. Скопируйте ключ и вставьте в .env

**Полный пример .env файла:**
```env
# Telegram Bot
BOT_TOKEN=ваш_токен_telegram

# kie.ai API
KIE_API_KEY=ваш_ключ_kie
KIE_API_URL=https://kie.ai

# OpenRouter (замена OpenAI для работы из РФ)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Settings
DEBUG=false
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 6. Проверить конфигурацию (опционально)

```bash
# Проверить что Python может прочитать config
sudo -u deploy /opt/photoshoot_ai/venv/bin/python -c "from bot.config import settings; print('Config OK')"
```

### 7. Запустить бота

```bash
sudo systemctl start photoshoot_ai
```

### 8. Проверить статус

```bash
# Статус сервиса
sudo systemctl status photoshoot_ai

# Должно показать: Active: active (running)
```

### 9. Проверить логи

```bash
# Последние 30 строк логов
sudo journalctl -u photoshoot_ai -n 30

# Логи в реальном времени (нажмите Ctrl+C для выхода)
sudo journalctl -u photoshoot_ai -f
```

## Проверка работы

После запуска проверьте:
1. Бот отвечает в Telegram
2. Можно сгенерировать фото
3. Разнообразие одежды увеличилось

## Если что-то пошло не так

### Бот не запускается

```bash
# Посмотреть подробные логи
sudo journalctl -u photoshoot_ai -n 50 --no-pager

# Частые причины:
# - Не обновлен .env (нет OPENROUTER_API_KEY)
# - Неверный формат ключа OpenRouter
# - Недостаточно баланса на OpenRouter
```

### Восстановить предыдущую версию

```bash
# Остановить бота
sudo systemctl stop photoshoot_ai

# Найти бэкап
ls -la /opt/photoshoot_ai/ | grep bot.backup

# Восстановить из последнего бэкапа
sudo rm -rf /opt/photoshoot_ai/bot
sudo cp -r /opt/photoshoot_ai/bot.backup_YYYYMMDD_HHMMSS /opt/photoshoot_ai/bot

# Восстановить старый .env (если меняли)
# (сделайте бэкап .env перед изменениями!)

# Запустить
sudo systemctl start photoshoot_ai
```

## Дополнительные команды

```bash
# Перезапустить бота
sudo systemctl restart photoshoot_ai

# Посмотреть использование ресурсов
top
# Найдите процесс python с ботом

# Проверить место на диске
df -h

# Очистить старые бэкапы (если нужно)
sudo rm -rf /opt/photoshoot_ai/bot.backup_*
```

## Поддержка

Если возникли проблемы:
1. Скопируйте логи: `sudo journalctl -u photoshoot_ai -n 100 > ~/bot_logs.txt`
2. Отправьте логи для анализа

## Важные заметки

⚠️ **OpenRouter требует баланс**
- GPT-5.2 стоит дороже чем GPT-4o-mini
- Проверьте баланс на https://openrouter.ai/credits
- Пополните при необходимости

✅ **Преимущества обновления**
- Значительно больше разнообразия в одежде
- Лучшее качество генерации промптов
- Более стабильная работа (retry механизм)
- Только casual/smart casual стиль (как запрошено)
