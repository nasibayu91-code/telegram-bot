import os

# ==============================
# НАСТРОЙКИ КАЗИНО БОТА
# ==============================

# Токен бота (получи у @BotFather)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8603411643:AAG4WVEpibqoD4QqvLfKKIOCUvOf21d3klc")

# Твой Telegram ID (узнай у @userinfobot)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7564112818"))

# Название и эмодзи токена
TOKEN_EMOJI = "💎"
TOKEN_NAME = "Gems"

# Бонус при регистрации
REGISTRATION_BONUS = 100

# Вероятность победы (30%)
WIN_RATE = 0.30

# Лимиты ставок
MIN_BET = 1
MAX_BET = 10000

# Минимальная сумма вывода
MIN_WITHDRAWAL = 50

# Обменные курсы
STARS_TO_TOKENS = 10   # 1 Star = 10 токенов
USD_TO_TOKENS   = 100  # 1 USD  = 100 токенов

# Реквизиты для USD оплаты (замени на свои)
PAYMENT_DETAILS = "USDT TRC-20: TXXXXXXXXXXXXyouraddressXXXXXXXXXXX"

# Реферальный бонус
REFERRAL_BONUS_REFERRER = 50   # тому кто пригласил
REFERRAL_BONUS_INVITED  = 25   # тому кого пригласили
