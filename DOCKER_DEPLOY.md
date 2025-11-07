# 🐳 Деплой с Docker

Используйте Docker для быстрого и изолированного развертывания на любом сервере.

## Требования

- Docker 20.10+
- Docker Compose 2.0+
- Доменное имя (опционально, для HTTPS)

## Быстрый старт

### 1. Подготовка сервера

```bash
# Установка Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Проверка установки
docker --version
docker-compose --version
```

### 2. Клонирование репозитория

```bash
git clone https://github.com/your-username/wb-claude.git
cd wb-claude
```

### 3. Создание .env файла

```bash
# Сгенерируйте ключи
python3 generate_keys.py

# Создайте .env файл
cat > .env << EOF
SECRET_KEY=<ваш сгенерированный SECRET_KEY>
ENCRYPTION_KEY=<ваш сгенерированный ENCRYPTION_KEY>
GOOGLE_CLIENT_ID=<из Google Console>
GOOGLE_CLIENT_SECRET=<из Google Console>
EOF
```

### 4. Запуск приложения

```bash
# Сборка и запуск всех контейнеров
docker-compose up -d

# Просмотр логов
docker-compose logs -f web

# Проверка статуса
docker-compose ps
```

### 5. Инициализация базы данных

```bash
# Подключение к контейнеру приложения
docker-compose exec web python

# В Python shell:
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### 6. Проверка работы

Откройте в браузере: `http://your-server-ip`

## Настройка HTTPS с Let's Encrypt

### 1. Обновите nginx.conf

Замените `your-domain.com` на ваш домен в секции HTTPS.

### 2. Получите SSL сертификат

```bash
# Создайте директории для Certbot
mkdir -p certbot/conf certbot/www

# Установите Certbot
sudo apt-get install certbot

# Получите сертификат
sudo certbot certonly --webroot \
  -w ./certbot/www \
  -d your-domain.com \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email

# Скопируйте сертификаты
sudo cp -r /etc/letsencrypt/* ./certbot/conf/
sudo chown -R $USER:$USER ./certbot/conf
```

### 3. Обновите Google OAuth

Добавьте в Google Cloud Console redirect URI:
```
https://your-domain.com/auth/callback
```

### 4. Перезапустите Nginx

```bash
# Раскомментируйте HTTPS секцию в nginx.conf
# Закомментируйте временный HTTP доступ

# Перезапустите контейнер
docker-compose restart nginx
```

## Полезные команды

```bash
# Остановка всех контейнеров
docker-compose down

# Остановка с удалением данных
docker-compose down -v

# Пересборка после изменений кода
docker-compose up -d --build

# Просмотр логов конкретного сервиса
docker-compose logs -f web
docker-compose logs -f db
docker-compose logs -f nginx

# Выполнение команды в контейнере
docker-compose exec web python
docker-compose exec db psql -U wb_user -d wb_claude

# Резервное копирование базы данных
docker-compose exec db pg_dump -U wb_user wb_claude > backup.sql

# Восстановление базы данных
docker-compose exec -T db psql -U wb_user wb_claude < backup.sql

# Обновление приложения
git pull
docker-compose up -d --build

# Очистка старых образов
docker system prune -a
```

## Мониторинг

### Проверка использования ресурсов

```bash
# Использование ресурсов контейнерами
docker stats

# Размер контейнеров
docker-compose ps --size

# Логи в реальном времени
docker-compose logs -f --tail=100
```

### Автоматический перезапуск

Контейнеры настроены на автоматический перезапуск (`restart: unless-stopped`).
Они будут автоматически запускаться при перезагрузке сервера.

## Масштабирование

### Увеличение количества workers

Отредактируйте `docker-compose.yml`:

```yaml
services:
  web:
    deploy:
      replicas: 3  # Запустить 3 экземпляра
```

Или в Dockerfile измените:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "8", "app:app"]
```

### Использование Redis для сессий (опционально)

Добавьте в `docker-compose.yml`:

```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

## Безопасность

### 1. Firewall

```bash
# Разрешить только необходимые порты
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 2. Обновления

```bash
# Регулярно обновляйте образы
docker-compose pull
docker-compose up -d

# Обновление системы
sudo apt update && sudo apt upgrade -y
```

### 3. Secrets

Никогда не коммитьте `.env` файл!
Убедитесь, что он в `.gitignore`.

### 4. Ограничение доступа к базе данных

База данных доступна только внутри Docker сети.
Не открывайте порт 5432 наружу.

## Резервное копирование

### Автоматические бэкапы

Создайте cron job:

```bash
# Откройте crontab
crontab -e

# Добавьте строку для ежедневного бэкапа в 2:00 AM
0 2 * * * cd /path/to/wb-claude && docker-compose exec -T db pg_dump -U wb_user wb_claude > /backups/wb_claude_$(date +\%Y\%m\%d).sql
```

### Бэкап статических файлов

```bash
# Архивирование static и fonts
tar -czf backup_files_$(date +%Y%m%d).tar.gz static/ fonts/
```

## Миграция на другой сервер

```bash
# На старом сервере:
# 1. Бэкап базы
docker-compose exec db pg_dump -U wb_user wb_claude > db_backup.sql

# 2. Архив файлов
tar -czf files_backup.tar.gz static/ fonts/ temp/

# На новом сервере:
# 1. Клонируйте репозиторий и настройте .env
# 2. Запустите контейнеры
docker-compose up -d

# 3. Восстановите базу
docker-compose exec -T db psql -U wb_user wb_claude < db_backup.sql

# 4. Восстановите файлы
tar -xzf files_backup.tar.gz
```

## Troubleshooting

### Контейнер web не запускается

```bash
# Проверьте логи
docker-compose logs web

# Проверьте переменные окружения
docker-compose exec web env | grep -E 'SECRET_KEY|DATABASE_URL|GOOGLE'
```

### База данных недоступна

```bash
# Проверьте статус контейнера
docker-compose ps db

# Проверьте подключение
docker-compose exec web python -c "from app import db; print(db.engine.url)"

# Перезапустите базу
docker-compose restart db
```

### Nginx возвращает 502

```bash
# Проверьте, что web контейнер запущен
docker-compose ps web

# Проверьте конфигурацию nginx
docker-compose exec nginx nginx -t

# Перезапустите nginx
docker-compose restart nginx
```

### SSL сертификат не работает

```bash
# Проверьте пути в nginx.conf
docker-compose exec nginx ls -la /etc/letsencrypt/live/

# Проверьте права доступа
ls -la certbot/conf/

# Обновите сертификат
sudo certbot renew
```

## Production Checklist

- [ ] `.env` файл создан и не в git
- [ ] Сгенерированы новые SECRET_KEY и ENCRYPTION_KEY
- [ ] Google OAuth настроен с правильным redirect URI
- [ ] HTTPS настроен (для production)
- [ ] Firewall настроен
- [ ] Автоматические бэкапы настроены
- [ ] SSL сертификат валиден
- [ ] Мониторинг настроен
- [ ] Логи ротируются (Docker автоматически)

---

Удачи с деплоем! 🚀
