#!/bin/bash
set -e

# ===========================================
# Скрипт деплоя Photoshoot AI Bot
# Яндекс.Облако Ubuntu/Debian
# ===========================================

APP_NAME="photoshoot_ai"
APP_DIR="/opt/$APP_NAME"
SERVICE_USER="deploy"

echo "=========================================="
echo "  Деплой $APP_NAME"
echo "=========================================="

# Проверка root прав
if [ "$EUID" -ne 0 ]; then
    echo "Запустите скрипт с sudo: sudo bash deploy.sh"
    exit 1
fi

# 1. Обновление системы и установка зависимостей
echo ""
echo "[1/6] Установка системных зависимостей..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git

# 2. Создание пользователя для сервиса
echo ""
echo "[2/6] Настройка пользователя $SERVICE_USER..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false $SERVICE_USER
    echo "Пользователь $SERVICE_USER создан"
else
    echo "Пользователь $SERVICE_USER уже существует"
fi

# 3. Создание директории приложения
echo ""
echo "[3/6] Настройка директории $APP_DIR..."
mkdir -p $APP_DIR
cp -r . $APP_DIR/
chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR

# 4. Настройка виртуального окружения
echo ""
echo "[4/6] Создание виртуального окружения Python..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR/venv

# 5. Настройка .env файла
echo ""
echo "[5/6] Настройка конфигурации..."
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp $APP_DIR/.env.example $APP_DIR/.env
        echo ""
        echo "!!! ВАЖНО: Отредактируйте файл $APP_DIR/.env !!!"
        echo "    Заполните BOT_TOKEN, KIE_API_KEY, OPENAI_API_KEY"
        echo ""
    fi
else
    echo ".env файл уже существует"
fi

chmod 600 $APP_DIR/.env
chown $SERVICE_USER:$SERVICE_USER $APP_DIR/.env

# 6. Установка systemd сервиса
echo ""
echo "[6/6] Установка systemd сервиса..."
cp $APP_DIR/photoshoot_ai.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable $APP_NAME

echo ""
echo "=========================================="
echo "  Деплой завершён!"
echo "=========================================="
echo ""
echo "Следующие шаги:"
echo "  1. Отредактируйте .env файл:"
echo "     sudo nano $APP_DIR/.env"
echo ""
echo "  2. Запустите бота:"
echo "     sudo systemctl start $APP_NAME"
echo ""
echo "  3. Проверьте статус:"
echo "     sudo systemctl status $APP_NAME"
echo ""
echo "  4. Просмотр логов:"
echo "     sudo journalctl -u $APP_NAME -f"
echo ""
