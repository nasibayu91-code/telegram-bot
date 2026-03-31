import os

# ==============================
# НАСТРОЙКИ КАЗИНО БОТА
# ==============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))

# CryptoBot
CRYPTOBOT_API_KEY = os.environ.get("CRYPTOBOT_API_KEY")
CRYPTOBOT_APP_ID = os.environ.get("CRYPTOBOT_APP_ID")

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
