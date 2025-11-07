#!/usr/bin/env python3
"""
Утилита для генерации секретных ключей для production деплоя.
Использование: python generate_keys.py
"""

import secrets
from cryptography.fernet import Fernet

print("=" * 60)
print("ГЕНЕРАЦИЯ СЕКРЕТНЫХ КЛЮЧЕЙ ДЛЯ PRODUCTION")
print("=" * 60)
print()

# Генерация SECRET_KEY
secret_key = secrets.token_hex(32)
print("SECRET_KEY (Flask session security):")
print(secret_key)
print()

# Генерация ENCRYPTION_KEY
encryption_key = Fernet.generate_key().decode()
print("ENCRYPTION_KEY (API keys encryption):")
print(encryption_key)
print()

print("=" * 60)
print("ВАЖНО: Сохраните эти ключи в безопасном месте!")
print("Используйте их для настройки переменных окружения.")
print("=" * 60)
