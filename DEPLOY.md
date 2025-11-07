# Руководство по развертыванию приложения Wildberries Manager

## 🚀 Вариант 1: Render.com (Рекомендуется для начала)

### Преимущества:
- ✅ Бесплатный план (с ограничениями)
- ✅ Автоматический HTTPS
- ✅ Встроенная PostgreSQL
- ✅ Простая настройка через GitHub
- ✅ Автодеплой при push

### Пошаговая инструкция:

#### 1. Подготовка репозитория

```bash
# Инициализируйте git (если еще не сделано)
git init
git add .
git commit -m "Initial commit"

# Создайте репозиторий на GitHub и загрузите код
git remote add origin https://github.com/your-username/wb-claude.git
git branch -M main
git push -u origin main
```

#### 2. Настройка Google OAuth для production

1. Откройте [Google Cloud Console](https://console.cloud.google.com/)
2. Выберите ваш проект
3. Перейдите в **Credentials** → **OAuth 2.0 Client IDs**
4. Добавьте Authorized redirect URIs:
   ```
   https://your-app-name.onrender.com/auth/callback
   ```
   (замените `your-app-name` на имя, которое выберете на Render)

#### 3. Регистрация на Render.com

1. Перейдите на [render.com](https://render.com)
2. Зарегистрируйтесь через GitHub
3. Нажмите **New +** → **Web Service**
4. Подключите ваш GitHub репозиторий

#### 4. Настройка Web Service

**Build & Deploy:**
- **Name:** `wb-claude` (или любое другое имя)
- **Environment:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`

**Environment Variables** (добавьте в разделе Environment):

```env
SECRET_KEY=<сгенерируйте через: python -c "import secrets; print(secrets.token_hex(32))">
ENCRYPTION_KEY=<сгенерируйте через: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
DATABASE_URL=<будет автоматически создан при добавлении PostgreSQL>
GOOGLE_CLIENT_ID=<ваш Client ID из Google Console>
GOOGLE_CLIENT_SECRET=<ваш Client Secret из Google Console>
```

#### 5. Добавление PostgreSQL базы данных

1. В Render Dashboard нажмите **New +** → **PostgreSQL**
2. Выберите **Free Plan**
3. Назовите базу: `wb-claude-db`
4. После создания скопируйте **Internal Database URL**
5. Вставьте его в переменную окружения `DATABASE_URL` вашего Web Service

#### 6. Инициализация базы данных

После первого деплоя база будет пустой. Подключитесь к консоли:

```bash
# В Render Dashboard откройте Shell вашего Web Service
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

#### 7. Проверка работы

Откройте `https://your-app-name.onrender.com` - приложение должно работать!

---

## 🔧 Вариант 2: VPS (DigitalOcean, Hetzner, Contabo)

### Преимущества:
- ✅ Полный контроль
- ✅ Не засыпает
- ✅ Лучшая производительность
- ❌ Требует настройки сервера

### Пошаговая инструкция:

#### 1. Создание сервера

1. Зарегистрируйтесь на DigitalOcean / Hetzner / Contabo
2. Создайте Droplet/VPS:
   - OS: Ubuntu 22.04 LTS
   - Plan: Basic ($6/месяц минимум)
   - Datacenter: ближайший к вашим пользователям

#### 2. Подключение к серверу

```bash
ssh root@your-server-ip
```

#### 3. Установка зависимостей

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Python и PostgreSQL
apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib nginx certbot python3-certbot-nginx

# Создание пользователя для приложения
adduser --disabled-password --gecos "" wbmanager
```

#### 4. Настройка PostgreSQL

```bash
# Переключение на пользователя postgres
sudo -u postgres psql

# В psql:
CREATE DATABASE wb_claude;
CREATE USER wb_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE wb_claude TO wb_user;
\q
```

#### 5. Клонирование и настройка приложения

```bash
# Переключение на пользователя приложения
su - wbmanager

# Клонирование репозитория
git clone https://github.com/your-username/wb-claude.git
cd wb-claude

# Создание виртуального окружения
python3.11 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Создание .env файла
nano .env
```

Содержимое `.env`:
```env
SECRET_KEY=<сгенерируйте>
ENCRYPTION_KEY=<сгенерируйте>
DATABASE_URL=postgresql://wb_user:your_secure_password@localhost/wb_claude
GOOGLE_CLIENT_ID=<ваш Client ID>
GOOGLE_CLIENT_SECRET=<ваш Client Secret>
```

#### 6. Инициализация базы данных

```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

#### 7. Настройка Gunicorn как службы

```bash
# Выход из пользователя wbmanager
exit

# Создание systemd service файла
nano /etc/systemd/system/wb-claude.service
```

Содержимое файла:
```ini
[Unit]
Description=Wildberries Manager Flask Application
After=network.target

[Service]
User=wbmanager
WorkingDirectory=/home/wbmanager/wb-claude
Environment="PATH=/home/wbmanager/wb-claude/venv/bin"
ExecStart=/home/wbmanager/wb-claude/venv/bin/gunicorn --workers 4 --bind 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

Запуск службы:
```bash
systemctl daemon-reload
systemctl start wb-claude
systemctl enable wb-claude
systemctl status wb-claude
```

#### 8. Настройка Nginx

```bash
nano /etc/nginx/sites-available/wb-claude
```

Содержимое файла:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /home/wbmanager/wb-claude/static;
    }

    client_max_body_size 20M;
}
```

Активация конфигурации:
```bash
ln -s /etc/nginx/sites-available/wb-claude /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

#### 9. Настройка HTTPS с Let's Encrypt

```bash
certbot --nginx -d your-domain.com
```

#### 10. Настройка Google OAuth

Добавьте в Google Cloud Console redirect URI:
```
https://your-domain.com/auth/callback
```

---

## 🌐 Вариант 3: Railway.app

### Преимущества:
- ✅ Очень простой деплой
- ✅ $5 бесплатно каждый месяц
- ✅ Автоматический HTTPS
- ✅ Встроенная PostgreSQL

### Инструкция:

1. Перейдите на [railway.app](https://railway.app)
2. Нажмите **Start a New Project**
3. Выберите **Deploy from GitHub repo**
4. Выберите ваш репозиторий
5. Railway автоматически определит Python приложение
6. Добавьте PostgreSQL: **New** → **Database** → **Add PostgreSQL**
7. Добавьте переменные окружения в Settings
8. Deploy!

---

## 📱 Вариант 4: PythonAnywhere (для небольших проектов)

### Преимущества:
- ✅ Бесплатный plan
- ✅ Специализируется на Python
- ❌ Ограничения на бесплатном плане

### Инструкция:

1. Зарегистрируйтесь на [pythonanywhere.com](https://www.pythonanywhere.com)
2. Откройте Bash консоль
3. Клонируйте репозиторий
4. Следуйте инструкциям по настройке Flask приложения
5. Настройте Web app через Dashboard

---

## ⚙️ Важные настройки для production

### 1. Обновите config.py

Убедитесь, что `SESSION_COOKIE_SECURE = True` для HTTPS:

```python
class Config:
    # ... существующие настройки ...

    # Production security
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
```

### 2. Создайте директории для файлов

```bash
mkdir -p static/labels temp fonts
```

### 3. Загрузите необходимые файлы

- `fonts/Arial.ttf` - шрифт для этикеток
- `static/images/chestniy_znak.png` - логотип для этикеток

---

## 🔒 Безопасность

1. **Никогда не коммитьте `.env` файл** в git
2. **Используйте сильные пароли** для базы данных
3. **Регулярно обновляйте зависимости**: `pip install --upgrade -r requirements.txt`
4. **Включите firewall** на VPS: `ufw allow 22,80,443/tcp`
5. **Настройте автоматические бэкапы** базы данных

---

## 📊 Мониторинг

### Логи на Render/Railway:
- Просматривайте в Dashboard → Logs

### Логи на VPS:
```bash
# Логи приложения
journalctl -u wb-claude -f

# Логи Nginx
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## 🆘 Поддержка

При возникновении проблем проверьте:
1. Логи приложения
2. Переменные окружения
3. Подключение к базе данных
4. Google OAuth redirect URIs

---

## 📝 Чеклист перед деплоем

- [ ] Все зависимости в `requirements.txt`
- [ ] `.env` не в git (проверьте `.gitignore`)
- [ ] Google OAuth настроен с правильными redirect URIs
- [ ] `SESSION_COOKIE_SECURE = True` для HTTPS
- [ ] Созданы необходимые директории (`static/labels`, `temp`, `fonts`)
- [ ] Загружены шрифты и логотипы
- [ ] База данных инициализирована (`db.create_all()`)
- [ ] Все секретные ключи сгенерированы заново для production

Удачи с деплоем! 🚀
