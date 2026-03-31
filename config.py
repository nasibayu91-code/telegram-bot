import os

# ==============================
# НАСТРОЙКИ КАЗИНО БОТА
# ==============================

BOT_TOKEN = os.environ.get("8603411643:AAG4WVEpibqoD4QqvLfKKIOCUvOf21d3klc")

# ADMIN_ID: берем из переменной, если нет - используем 7564112818
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7564112818"))

# CryptoBot
CRYPTOBOT_API_KEY = os.environ.get("559904:AAz43Da1Rty1m7AdVud8QHjzwFaxhGUG2iG")
CRYPTOBOT_APP_ID = os.environ.get("Porcine Skua App")

TOKEN_EMOJI = "💎"
TOKEN_NAME = "Gems"

REGISTRATION_BONUS = 100
WIN_RATE = 0.30
MIN_BET = 1
MAX_BET = 10000
MIN_WITHDRAWAL = 50

STARS_TO_TOKENS = 10
USD_TO_TOKENS = 100

PAYMENT_DETAILS = "USDT TRC-20: TXXXXXXXXXXXXyouraddressXXXXXXXXXXX"

REFERRAL_BONUS_REFERRER = 50
REFERRAL_BONUS_INVITED = 25
