# Деплой Photoshoot AI Bot на Яндекс.Облако

## Требования к ВМ

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| vCPU | 2 (shared) | 2 |
| RAM | 1 GB | 2 GB |
| Диск | 10 GB | 20 GB |
| ОС | Ubuntu 22.04 | Ubuntu 22.04 |
| Сеть | Публичный IP | Публичный IP |

## Шаг 1: Создание ВМ в Яндекс.Облаке

1. Перейдите в [Консоль Яндекс.Облака](https://console.cloud.yandex.ru/)
2. Compute Cloud → Создать ВМ
3. Настройки:
   - **Имя**: `photoshoot-ai-bot`
   - **Зона**: `ru-central1-a` (или ближайшая)
   - **ОС**: Ubuntu 22.04
   - **vCPU**: 2 (shared-core, достаточно 20%)
   - **RAM**: 2 GB
   - **Диск**: 20 GB SSD
   - **Публичный IP**: автоматически
   - **SSH-ключ**: ваш публичный ключ

4. Создайте ВМ и дождитесь запуска

## Шаг 2: Подключение к ВМ

```bash
# Замените на ваш IP
ssh yc-user@<IP-АДРЕС-ВМ>
```

## Шаг 3: Загрузка проекта на ВМ

### Вариант A: Через Git (рекомендуется)

```bash
# Если проект в Git репозитории
cd /tmp
git clone https://github.com/your-username/photoshoot_ai.git
cd photoshoot_ai
```

### Вариант B: Через SCP (копирование файлов)

На локальной машине:
```bash
# Архивирование проекта (исключая venv и .env)
cd /Users/kudinow/Documents/Cursor_PRO
tar --exclude='photoshoot_ai/venv' \
    --exclude='photoshoot_ai/.env' \
    --exclude='photoshoot_ai/__pycache__' \
    -czvf photoshoot_ai.tar.gz photoshoot_ai

# Копирование на сервер
scp photoshoot_ai.tar.gz yc-user@<IP-АДРЕС-ВМ>:/tmp/
```

На сервере:
```bash
cd /tmp
tar -xzvf photoshoot_ai.tar.gz
cd photoshoot_ai
```

## Шаг 4: Запуск деплоя

```bash
# Сделать скрипт исполняемым
chmod +x deploy.sh

# Запустить деплой
sudo bash deploy.sh
```

Скрипт автоматически:
- Установит Python и зависимости
- Создаст системного пользователя `deploy`
- Скопирует проект в `/opt/photoshoot_ai`
- Создаст виртуальное окружение
- Установит systemd сервис

## Шаг 5: Настройка .env

```bash
sudo nano /opt/photoshoot_ai/.env
```

Заполните следующие значения:

```env
# Telegram Bot
BOT_TOKEN=ваш_токен_от_botfather

# kie.ai API
KIE_API_KEY=ваш_ключ_kie
KIE_API_URL=https://api.kie.ai

# OpenAI API
OPENAI_API_KEY=ваш_ключ_openai

# Настройки
DEBUG=false
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

## Шаг 6: Запуск бота

```bash
# Запустить
sudo systemctl start photoshoot_ai

# Проверить статус
sudo systemctl status photoshoot_ai
```

Должно показать `Active: active (running)`.

## Управление ботом

```bash
# Статус
sudo systemctl status photoshoot_ai

# Перезапуск
sudo systemctl restart photoshoot_ai

# Остановка
sudo systemctl stop photoshoot_ai

# Логи (в реальном времени)
sudo journalctl -u photoshoot_ai -f

# Логи за последний час
sudo journalctl -u photoshoot_ai --since "1 hour ago"

# Включить автозапуск
sudo systemctl enable photoshoot_ai

# Выключить автозапуск
sudo systemctl disable photoshoot_ai
```

## Обновление бота

```bash
# 1. Остановить бота
sudo systemctl stop photoshoot_ai

# 2. Обновить файлы
cd /opt/photoshoot_ai
sudo -u deploy git pull  # если через git
# или скопируйте новые файлы через scp

# 3. Обновить зависимости (если изменились)
sudo -u deploy /opt/photoshoot_ai/venv/bin/pip install -r requirements.txt

# 4. Запустить бота
sudo systemctl start photoshoot_ai
```

## Решение проблем

### Бот не запускается

```bash
# Проверить логи
sudo journalctl -u photoshoot_ai -n 50

# Частые причины:
# - Неверный BOT_TOKEN
# - Не заполнен .env файл
# - Ошибка в API ключах
```

### Ошибка прав доступа

```bash
# Проверить владельца файлов
ls -la /opt/photoshoot_ai/

# Исправить права
sudo chown -R deploy:deploy /opt/photoshoot_ai
```

### Проверить что Python работает

```bash
cd /opt/photoshoot_ai
sudo -u deploy ./venv/bin/python -c "from bot.config import settings; print('OK')"
```

## Firewall (если включен)

Бот использует polling (исходящие соединения), поэтому входящие порты открывать не нужно.

Если в будущем перейдёте на webhook:
```bash
sudo ufw allow 443/tcp
```

## Мониторинг

### Простой мониторинг через cron

```bash
# Создать скрипт проверки
sudo nano /opt/photoshoot_ai/health_check.sh
```

```bash
#!/bin/bash
if ! systemctl is-active --quiet photoshoot_ai; then
    systemctl restart photoshoot_ai
    echo "$(date): Bot restarted" >> /var/log/photoshoot_ai_health.log
fi
```

```bash
# Сделать исполняемым
sudo chmod +x /opt/photoshoot_ai/health_check.sh

# Добавить в cron (проверка каждые 5 минут)
sudo crontab -e
# Добавить строку:
*/5 * * * * /opt/photoshoot_ai/health_check.sh
```

## Структура после деплоя

```
/opt/photoshoot_ai/
├── bot/
│   ├── main.py
│   ├── config.py
│   ├── handlers/
│   ├── services/
│   ├── states/
│   └── keyboards/
├── venv/
├── .env              # секреты (chmod 600)
├── requirements.txt
└── photoshoot_ai.service
```
