#!/bin/bash
# Автоматический скрипт установки WB Claude на VPS
# Использование: bash setup_server.sh

set -e  # Остановка при ошибке

echo "=================================================="
echo "   Установка WB Claude на VPS сервер"
echo "=================================================="
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода с цветом
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Шаг 1: Обновление системы
echo ""
echo "Шаг 1/8: Обновление системы..."
apt update && apt upgrade -y
print_status "Система обновлена"

# Шаг 2: Установка необходимых пакетов
echo ""
echo "Шаг 2/8: Установка необходимых пакетов..."
apt install -y git curl wget nano ufw
print_status "Пакеты установлены"

# Шаг 3: Установка Docker
echo ""
echo "Шаг 3/8: Установка Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
    print_status "Docker установлен"
else
    print_status "Docker уже установлен"
fi

# Шаг 4: Установка Docker Compose
echo ""
echo "Шаг 4/8: Установка Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    print_status "Docker Compose установлен"
else
    print_status "Docker Compose уже установлен"
fi

# Проверка версий
echo ""
echo "Установленные версии:"
docker --version
docker-compose --version

# Шаг 5: Клонирование репозитория
echo ""
echo "Шаг 5/8: Клонирование репозитория..."
cd /root
if [ -d "WB_CLAUDE" ]; then
    print_warning "Директория WB_CLAUDE уже существует. Обновляем..."
    cd WB_CLAUDE
    git pull
else
    git clone https://github.com/Qudy8/WB_CLAUDE.git
    cd WB_CLAUDE
    print_status "Репозиторий склонирован"
fi

# Шаг 6: Создание необходимых директорий
echo ""
echo "Шаг 6/8: Создание директорий..."
mkdir -p static/labels temp fonts certbot/conf certbot/www
print_status "Директории созданы"

# Шаг 7: Настройка Firewall
echo ""
echo "Шаг 7/8: Настройка Firewall..."
print_warning "Настраиваем UFW firewall..."
ufw --force enable
ufw allow 22/tcp  # SSH
ufw allow 80/tcp  # HTTP
ufw allow 443/tcp # HTTPS
print_status "Firewall настроен (порты 22, 80, 443 открыты)"

# Шаг 8: Генерация ключей
echo ""
echo "Шаг 8/8: Генерация секретных ключей..."
echo ""
echo "=================================================="
echo "   СЕКРЕТНЫЕ КЛЮЧИ ДЛЯ .env ФАЙЛА"
echo "=================================================="
echo ""

# Проверка наличия Python
if command -v python3 &> /dev/null; then
    python3 generate_keys.py
else
    print_warning "Python3 не найден. Устанавливаем..."
    apt install -y python3 python3-pip
    python3 generate_keys.py
fi

echo ""
echo "=================================================="
echo "   Установка завершена!"
echo "=================================================="
echo ""
print_status "Все зависимости установлены"
print_status "Репозиторий находится в: /root/WB_CLAUDE"
echo ""
print_warning "СЛЕДУЮЩИЕ ШАГИ:"
echo ""
echo "1. Скопируйте секретные ключи выше"
echo "2. Создайте .env файл командой:"
echo "   nano /root/WB_CLAUDE/.env"
echo ""
echo "3. Вставьте следующее содержимое (замените значения):"
echo ""
echo "SECRET_KEY=ваш_сгенерированный_secret_key"
echo "ENCRYPTION_KEY=ваш_сгенерированный_encryption_key"
echo "GOOGLE_CLIENT_ID=ваш_google_client_id"
echo "GOOGLE_CLIENT_SECRET=ваш_google_client_secret"
echo "FLASK_ENV=production"
echo ""
echo "4. Сохраните файл: Ctrl+X, затем Y, затем Enter"
echo ""
echo "5. Запустите приложение:"
echo "   cd /root/WB_CLAUDE"
echo "   docker-compose up -d"
echo ""
echo "=================================================="
