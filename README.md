# Wildberries Manager

Веб-приложение для работы с Wildberries API, создания этикеток и управления заказами.

## Возможности

- Авторизация через Google OAuth
- Безопасное хранение API ключей Wildberries (с шифрованием)
- Управление настройками бизнеса
- Создание этикеток для заказов
- Просмотр и управление заказами

## Требования

- Python 3.8+
- Flask 3.0+
- SQLite (или другая БД)
- Google Cloud Project с настроенным OAuth 2.0

## Установка

### 1. Клонирование репозитория

```bash
cd wb_claude
```

### 2. Создание виртуального окружения

```bash
python -m venv venv
```

Активация виртуального окружения:

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка Google OAuth

1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Включите Google+ API
4. Перейдите в "Credentials" → "Create Credentials" → "OAuth client ID"
5. Выберите "Web application"
6. Добавьте Authorized redirect URIs:
   - `http://localhost:5000/auth/callback`
   - `http://127.0.0.1:5000/auth/callback`
7. Скопируйте Client ID и Client Secret

### 5. Настройка переменных окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Откройте `.env` и заполните следующие переменные:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here-change-in-production

# Database
DATABASE_URL=sqlite:///wb_app.db

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Encryption Key
ENCRYPTION_KEY=your-encryption-key-here
```

**Генерация ENCRYPTION_KEY:**

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Генерация SECRET_KEY:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 6. Инициализация базы данных

```bash
python app.py
```

База данных создастся автоматически при первом запуске.

## Запуск приложения

```bash
python app.py
```

Приложение будет доступно по адресу: `http://localhost:5000`

## Структура проекта

```
wb_claude/
├── app.py                  # Главный файл приложения
├── auth.py                 # Модуль аутентификации
├── config.py               # Конфигурация приложения
├── models.py               # Модели базы данных
├── requirements.txt        # Зависимости Python
├── .env                    # Переменные окружения (не в Git)
├── .env.example           # Пример переменных окружения
├── .gitignore             # Игнорируемые файлы Git
├── templates/             # HTML шаблоны
│   ├── base.html          # Базовый шаблон
│   ├── login.html         # Страница входа
│   ├── dashboard.html     # Главная страница
│   └── settings.html      # Страница настроек
└── static/                # Статические файлы (CSS, JS, изображения)
```

## Использование

### 1. Первый вход

1. Откройте приложение в браузере
2. Нажмите "Войти через Google"
3. Авторизуйтесь через Google аккаунт

### 2. Настройка API ключа Wildberries

1. Перейдите в раздел "Настройки"
2. Введите наименование вашего ИП/Организации
3. Получите API ключ в [личном кабинете Wildberries](https://seller.wildberries.ru/supplier-settings/access-to-api)
4. Вставьте API ключ в соответствующее поле
5. Нажмите "Сохранить изменения"

### 3. Работа с приложением

После настройки API ключа вы сможете:
- Создавать этикетки для заказов
- Просматривать информацию о заказах
- Экспортировать данные

## Безопасность

- API ключи хранятся в зашифрованном виде с использованием библиотеки `cryptography`
- Используется Fernet симметричное шифрование
- Сессии защищены от CSRF атак
- Все пароли и секретные ключи должны храниться в `.env` файле

## Production deployment

Для развертывания в production:

1. Установите `SESSION_COOKIE_SECURE = True` в `config.py`
2. Используйте HTTPS
3. Измените `SECRET_KEY` и `ENCRYPTION_KEY` на уникальные значения
4. Используйте production-ready WSGI сервер (Gunicorn, uWSGI)
5. Настройте reverse proxy (Nginx, Apache)
6. Используйте production базу данных (PostgreSQL, MySQL)

Пример запуска с Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Troubleshooting

### Ошибка "Invalid state parameter"

Убедитесь, что:
- Включены cookies в браузере
- Используете правильный redirect URI в Google OAuth настройках
- Не используете режим инкогнито

### Ошибка шифрования API ключа

Проверьте:
- Правильно ли сгенерирован `ENCRYPTION_KEY`
- Не изменился ли ключ после сохранения данных

## Лицензия

MIT License

## Автор

Создано для работы с Wildberries API
