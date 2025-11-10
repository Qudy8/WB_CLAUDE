# Production HTTPS Setup Checklist

Критические настройки для работы Google OAuth через HTTPS на production сервере.

## ✅ Обязательные настройки для HTTPS

### 1. **auth.py** - Отключить OAUTHLIB_INSECURE_TRANSPORT

```python
# auth.py (строки 12-16)
# Google OAuth configuration
# OAUTHLIB_INSECURE_TRANSPORT removed for production HTTPS
# Only enable insecure transport for local development without HTTPS
# os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
```

⚠️ **ВАЖНО**: `OAUTHLIB_INSECURE_TRANSPORT = '1'` **НЕЛЬЗЯ** использовать на production с HTTPS! Это заставляет OAuth использовать HTTP вместо HTTPS.

---

### 2. **config.py** - Установить PREFERRED_URL_SCHEME

```python
# config.py (строка ~30)
# URL Scheme
# Force HTTPS URLs in production (always use HTTPS for external URLs)
PREFERRED_URL_SCHEME = 'https'
```

⚠️ **ВАЖНО**: Flask должен знать что нужно генерировать HTTPS URLs для OAuth redirect_uri.

---

### 3. **app.py** - Добавить ProxyFix middleware

```python
# app.py (строки 1-16)
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from models import db, User
from auth import auth_bp
import os

app = Flask(__name__)
app.config.from_object(Config)

# Configure app to work behind HTTPS proxy (Nginx)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)
```

⚠️ **ВАЖНО**: ProxyFix обрабатывает заголовки `X-Forwarded-Proto` от Nginx, чтобы Flask знал что запрос пришел через HTTPS.

---

### 4. **nginx.conf** - Правильная HTTPS конфигурация

```nginx
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    upstream flask_app {
        server web:5000;
    }

    # HTTP server - redirect to HTTPS
    server {
        listen 80;
        server_name managerwbb.ru www.managerwbb.ru;

        client_max_body_size 20M;

        # Certbot challenge
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        # Redirect to HTTPS
        location / {
            return 301 https://$host$request_uri;
        }
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name managerwbb.ru www.managerwbb.ru;

        ssl_certificate /etc/letsencrypt/live/managerwbb.ru/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/managerwbb.ru/privkey.pem;

        client_max_body_size 20M;

        location / {
            proxy_pass http://flask_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;  # ← КРИТИЧЕСКИ ВАЖНО!
            proxy_redirect off;
        }

        location /static {
            alias /app/static;
            expires 30d;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

⚠️ **ВАЖНО**:
- HTTPS секция **ДОЛЖНА БЫТЬ РАСКОММЕНТИРОВАНА**
- `proxy_set_header X-Forwarded-Proto $scheme;` **ОБЯЗАТЕЛЕН** - передает информацию о HTTPS в Flask
- HTTP редирект **ДОЛЖЕН БЫТЬ ВКЛЮЧЕН** для автоматического перенаправления на HTTPS

---

### 5. **Dockerfile** - Системные библиотеки

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libdmtx0b \
    libdmtx-dev \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p static/labels temp fonts

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]
```

⚠️ **ВАЖНО**: `libdmtx0b`, `libdmtx-dev`, `libzbar0` нужны для генерации этикеток с DataMatrix.

---

### 6. **requirements.txt** - Python зависимости

```txt
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-Migrate==4.0.5
psycopg2-binary==2.9.9  # ← ОБЯЗАТЕЛЕН для PostgreSQL
cryptography==41.0.7
python-dotenv==1.0.0
google-auth==2.25.2
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
requests==2.31.0
Werkzeug==3.0.1
pypdf==6.1.2
PyMuPDF
reportlab
pylibdmtx
python-barcode
Pillow
gunicorn
```

⚠️ **ВАЖНО**: `psycopg2-binary` обязателен для работы с PostgreSQL в Docker.

---

### 7. **Google Cloud Console** - OAuth Redirect URI

В Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID:

**Authorized redirect URIs:**
```
https://managerwbb.ru/auth/callback
https://www.managerwbb.ru/auth/callback
```

⚠️ **ВАЖНО**:
- Используйте **HTTPS** (не HTTP)
- **Нажмите кнопку "Save"** внизу страницы
- Подождите 5-10 минут для применения изменений

---

## 🔧 Проверка настроек

### Проверить что Flask генерирует HTTPS redirect_uri:

```bash
docker-compose exec web python -c "
from app import app
from flask import url_for
with app.test_request_context('/', base_url='https://managerwbb.ru'):
    print('Redirect URI:', url_for('auth.callback', _external=True))
"
```

**Ожидаемый вывод:**
```
Redirect URI: https://managerwbb.ru/auth/callback
```

❌ Если видите `http://` вместо `https://` - проверьте все настройки выше!

---

### Проверить nginx конфигурацию:

```bash
docker-compose exec nginx nginx -t
```

---

### Проверить SSL сертификат:

```bash
curl -I https://managerwbb.ru
```

Должно вернуть `HTTP/2 200` без ошибок SSL.

---

## 🚀 Deployment команды

### После обновления кода:

```bash
cd /root/WB_CLAUDE
git pull
docker-compose up -d --build
```

### После изменения nginx.conf:

```bash
docker-compose exec nginx nginx -t  # проверка синтаксиса
docker-compose restart nginx
```

### Полная перезагрузка:

```bash
docker-compose down
docker-compose up -d --build
```

---

## ⚠️ Типичные ошибки

### Ошибка: `redirect_uri_mismatch` при входе через Google

**Причина:** Flask генерирует `http://` вместо `https://`

**Решение:**
1. ✅ Проверить что `OAUTHLIB_INSECURE_TRANSPORT` **ЗАКОММЕНТИРОВАН** в auth.py
2. ✅ Проверить что `PREFERRED_URL_SCHEME = 'https'` в config.py
3. ✅ Проверить что ProxyFix добавлен в app.py
4. ✅ Проверить что nginx передает `X-Forwarded-Proto: https`
5. ✅ Проверить что HTTPS секция в nginx.conf **РАСКОММЕНТИРОВАНА**

---

### Ошибка: `ModuleNotFoundError: No module named 'psycopg2'`

**Причина:** Отсутствует `psycopg2-binary` в requirements.txt

**Решение:**
```bash
# Добавить в requirements.txt:
psycopg2-binary==2.9.9

# Пересобрать контейнер:
docker-compose up -d --build web
```

---

### Ошибка: `ImportError: Unable to find dmtx shared library`

**Причина:** Отсутствуют системные библиотеки в Dockerfile

**Решение:**
```bash
# Добавить в Dockerfile:
RUN apt-get update && apt-get install -y \
    libdmtx0b \
    libdmtx-dev \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# Пересобрать контейнер:
docker-compose build --no-cache web
docker-compose up -d web
```

---

## 📝 Changelog

- **2025-11-10**: Настроена production HTTPS конфигурация для OAuth
  - Удален OAUTHLIB_INSECURE_TRANSPORT из auth.py
  - Добавлен PREFERRED_URL_SCHEME в config.py
  - Добавлен ProxyFix middleware в app.py
  - Обновлен nginx.conf с правильной HTTPS конфигурацией
  - Добавлен psycopg2-binary в requirements.txt
  - Добавлены системные библиотеки в Dockerfile

---

## ✅ Финальный чеклист перед deployment

- [ ] `OAUTHLIB_INSECURE_TRANSPORT` закомментирован в auth.py
- [ ] `PREFERRED_URL_SCHEME = 'https'` установлен в config.py
- [ ] `ProxyFix` добавлен в app.py
- [ ] nginx.conf имеет HTTPS секцию с `proxy_set_header X-Forwarded-Proto $scheme`
- [ ] `psycopg2-binary` добавлен в requirements.txt
- [ ] Системные библиотеки (`libdmtx0b`, `libdmtx-dev`, `libzbar0`) добавлены в Dockerfile
- [ ] SSL сертификат установлен в `/etc/letsencrypt/live/managerwbb.ru/`
- [ ] Google OAuth redirect URIs включают `https://managerwbb.ru/auth/callback`
- [ ] Docker контейнеры пересобраны: `docker-compose up -d --build`
- [ ] Проверка: `curl -I https://managerwbb.ru` возвращает `HTTP/2 200`
- [ ] Проверка: Вход через Google работает без ошибок

---

**Все настройки протестированы и работают на production сервере managerwbb.ru (81.200.147.245)**
