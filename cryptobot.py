import requests
import hashlib
import hmac
import json
from flask import Flask, request, jsonify
import threading
import config
import database as db

app = Flask(__name__)

def verify_cryptobot_webhook(data, signature):
    """Проверка подписи CryptoBot"""
    secret = config.CRYPTOBOT_API_KEY
    expected = hmac.new(
        secret.encode(),
        json.dumps(data, separators=(',', ':')).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route('/cryptobot-webhook', methods=['POST'])
def cryptobot_webhook():
    """Обработка уведомлений от CryptoBot"""
    signature = request.headers.get('crypto-pay-api-signature')
    data = request.get_json()
    
    if not verify_cryptobot_webhook(data, signature):
        return jsonify({"ok": False}), 403
    
    if data.get('update_type') == 'invoice_paid':
        payload = data['payload']['payload']
        amount = data['payload']['amount']
        asset = data['payload']['asset']
        
        # Получаем user_id из payload
        user_id = int(payload.split('_')[1])
        
        # Конвертируем в токены (например 1 USDT = 100 токенов)
        tokens = int(amount * 100)
        
        # Начисляем токены
        db.update_balance(user_id, tokens)
        db.add_transaction(user_id, "deposit", tokens, f"CryptoBot {asset} {amount}")
        
        # Уведомляем пользователя
        try:
            import bot
            # Отправить сообщение пользователю
        except:
            pass
    
    return jsonify({"ok": True})

def run_webhook():
    app.run(host='0.0.0.0', port=8080)

def start_webhook():
    thread = threading.Thread(target=run_webhook, daemon=True)
    thread.start()
