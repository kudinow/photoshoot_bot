# Полезные команды для сервера

## Подключение

```bash
ssh kudinow@89.169.163.73
```

## Управление ботом

```bash
# Статус
sudo systemctl status photoshoot_ai

# Запуск
sudo systemctl start photoshoot_ai

# Остановка
sudo systemctl stop photoshoot_ai

# Перезапуск
sudo systemctl restart photoshoot_ai

# Включить автозапуск
sudo systemctl enable photoshoot_ai

# Выключить автозапуск
sudo systemctl disable photoshoot_ai
```

## Логи

```bash
# Логи в реальном времени
sudo journalctl -u photoshoot_ai -f

# Последние 50 строк
sudo journalctl -u photoshoot_ai -n 50

# Логи за последний час
sudo journalctl -u photoshoot_ai --since "1 hour ago"

# Логи за сегодня
sudo journalctl -u photoshoot_ai --since today
```

## Файлы на сервере

```bash
# Директория проекта
cd /opt/photoshoot_ai

# Редактировать .env
sudo nano /opt/photoshoot_ai/.env

# Посмотреть .env
sudo cat /opt/photoshoot_ai/.env
```

## Обновление бота

```bash
# 1. Остановить бота
sudo systemctl stop photoshoot_ai

# 2. На локальной машине: заархивировать и скопировать
cd /Users/kudinow/Documents/Cursor_PRO
tar --exclude='photoshoot_ai/venv' \
    --exclude='photoshoot_ai/.env' \
    --exclude='photoshoot_ai/__pycache__' \
    --exclude='photoshoot_ai/.claude' \
    -czvf /tmp/photoshoot_ai.tar.gz photoshoot_ai
scp /tmp/photoshoot_ai.tar.gz kudinow@89.169.163.73:/tmp/

# 3. На сервере: распаковать и обновить
cd /tmp && tar -xzvf photoshoot_ai.tar.gz
sudo cp -r photoshoot_ai/bot /opt/photoshoot_ai/
sudo chown -R deploy:deploy /opt/photoshoot_ai

# 4. Обновить зависимости (если изменились)
sudo -u deploy /opt/photoshoot_ai/venv/bin/pip install -r /opt/photoshoot_ai/requirements.txt

# 5. Запустить бота
sudo systemctl start photoshoot_ai
```

## Информация о сервере

| Параметр | Значение |
|----------|----------|
| IP | 89.169.163.73 |
| Пользователь | kudinow |
| ОС | Ubuntu 22.04 |
| Директория бота | /opt/photoshoot_ai |
| Systemd сервис | photoshoot_ai |
