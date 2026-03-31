"""
VIP Casino Bot — с поддержкой CryptoBot
Игры: Орёл/Решка, Кости, Дартс, Баскетбол, Футбол, Мины, Башня
Платежи: Telegram Stars, CryptoBot (USDT/BTC/TON)
"""

import asyncio
import logging
import random
import sys
import os
import requests
import json
import hmac
import hashlib
from threading import Thread
from flask import Flask, request, jsonify

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    MessageHandler, PreCheckoutQueryHandler,
    Filters, CallbackContext
)

import config
import database as db

# ─── ЛОГИРОВАНИЕ ─────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ─── CRYPTOBOT WEBHOOK ───────────────────────────────────────────────────────

crypto_app = Flask(__name__)

def verify_cryptobot_webhook(data, signature):
    """Проверка подписи CryptoBot"""
    secret = config.CRYPTOBOT_API_KEY
    if not secret:
        return False
    expected = hmac.new(
        secret.encode(),
        json.dumps(data, separators=(',', ':')).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@crypto_app.route('/cryptobot-webhook', methods=['POST'])
def cryptobot_webhook():
    """Обработка уведомлений от CryptoBot"""
    signature = request.headers.get('crypto-pay-api-signature')
    data = request.get_json()
    
    if not verify_cryptobot_webhook(data, signature):
        return jsonify({"ok": False}), 403
    
    if data.get('update_type') == 'invoice_paid':
        payload = data['payload']['payload']
        amount = float(data['payload']['amount'])
        asset = data['payload']['asset']
        
        try:
            user_id = int(payload.split('_')[1])
            tokens = int(amount * config.USD_TO_TOKENS)
            
            db.update_balance(user_id, tokens)
            db.add_transaction(user_id, "deposit", tokens, f"CryptoBot {asset} {amount} USD")
            
            logger.info(f"Deposit: user {user_id} +{tokens} tokens via {asset}")
            
            # Уведомление админу
            try:
                send_message_to_admin(f"💰 Новый депозит через CryptoBot\n👤 ID: {user_id}\n💵 {amount} {asset} → {tokens} токенов")
            except:
                pass
        except Exception as e:
            logger.error(f"CryptoBot webhook error: {e}")
    
    return jsonify({"ok": True})

def run_webhook():
    crypto_app.run(host='0.0.0.0', port=8080)

def start_webhook():
    thread = Thread(target=run_webhook, daemon=True)
    thread.start()

def send_message_to_admin(text):
    """Отправить сообщение админу"""
    try:
        import telegram
        bot = telegram.Bot(token=config.BOT_TOKEN)
        bot.send_message(chat_id=config.ADMIN_ID, text=text)
    except:
        pass

# ─── УТИЛИТЫ ─────────────────────────────────────────────────────────────────

def fmt(amount: float) -> str:
    return f"{amount:,.0f} {config.TOKEN_EMOJI}"

def win_check() -> bool:
    return random.random() < config.WIN_RATE

def ensure_registered(user):
    db.register_user(user.id, user.username or "", user.first_name or "")

# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────

def kb_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎮 Игры", callback_data="m:games"),
            InlineKeyboardButton("💼 Баланс", callback_data="m:balance"),
        ],
        [
            InlineKeyboardButton("➕ Пополнить", callback_data="m:deposit"),
            InlineKeyboardButton("➖ Вывести", callback_data="m:withdraw"),
        ],
        [
            InlineKeyboardButton("🏆 Топ игроков", callback_data="m:top"),
            InlineKeyboardButton("📊 Статистика", callback_data="m:stats"),
        ],
        [
            InlineKeyboardButton("👥 Реферал", callback_data="m:referral"),
        ],
    ])

def kb_games():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🪙 Орёл/Решка", callback_data="g:coinflip"),
            InlineKeyboardButton("🎲 Кости", callback_data="g:dice"),
        ],
        [
            InlineKeyboardButton("🎯 Дартс", callback_data="g:darts"),
            InlineKeyboardButton("🏀 Баскетбол", callback_data="g:basketball"),
        ],
        [
            InlineKeyboardButton("⚽ Футбол", callback_data="g:football"),
            InlineKeyboardButton("💣 Мины", callback_data="g:mines"),
        ],
        [
            InlineKeyboardButton("🗼 Башня", callback_data="g:tower"),
        ],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="m:main")],
    ])

def kb_bet(game: str):
    amounts = [1, 5, 10, 25, 50, 100, 250, 500, 1000]
    rows = []
    row = []
    for amt in amounts:
        row.append(InlineKeyboardButton(
            f"{amt}{config.TOKEN_EMOJI}", callback_data=f"b:{game}:{amt}"
        ))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m:games")])
    return InlineKeyboardMarkup(rows)

# ─── CRYPTOBOT ИНВОЙС ────────────────────────────────────────────────────────

def create_cryptobot_invoice(user_id, amount_usd, currency):
    """Создает инвойс в CryptoBot"""
    api_key = config.CRYPTOBOT_API_KEY
    if not api_key:
        return None
    
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": api_key}
    data = {
        "asset": currency,
        "amount": str(amount_usd),
        "description": f"Пополнение VIP Casino",
        "payload": f"user_{user_id}",
        "expires_in": 3600
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        result = response.json()
        if result.get("ok"):
            return result["result"]["pay_url"]
    except Exception as e:
        logger.error(f"CryptoBot invoice error: {e}")
    return None

# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: CallbackContext):
    user = update.effective_user
    ref_id = None
    if context.args:
        try:
            ref_id = int(context.args[0])
            if ref_id == user.id:
                ref_id = None
        except ValueError:
            ref_id = None

    is_new = db.register_user(user.id, user.username or "", user.first_name or "", ref_id)

    if is_new:
        db.update_balance(user.id, config.REGISTRATION_BONUS)
        db.add_transaction(user.id, "bonus", config.REGISTRATION_BONUS, "Приветственный бонус")

        text = (
            f"🎰 *Добро пожаловать в VIP Casino, {user.first_name}!*\n\n"
            f"🎁 Тебе начислен бонус при регистрации:\n"
            f"*{fmt(config.REGISTRATION_BONUS)}*\n\n"
            f"Удачи за столом! 🍀"
        )

        if ref_id and db.get_user(ref_id):
            db.update_balance(user.id, config.REFERRAL_BONUS_INVITED)
            db.update_balance(ref_id, config.REFERRAL_BONUS_REFERRER)
            db.add_transaction(user.id, "bonus", config.REFERRAL_BONUS_INVITED, "Реферальный бонус")
            db.add_transaction(ref_id, "bonus", config.REFERRAL_BONUS_REFERRER, "Реферальный бонус")
            text += f"\n➕ Реферальный бонус: +{fmt(config.REFERRAL_BONUS_INVITED)}"
    else:
        bal = db.get_balance(user.id)
        text = (
            f"🎰 *VIP Casino*\n\n"
            f"С возвращением, *{user.first_name}*!\n"
            f"💼 Баланс: *{fmt(bal)}*"
        )

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb_main())

# ─── ГЛАВНЫЙ CALLBACK ────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    ensure_registered(q.from_user)

    parts = q.data.split(":")
    action = parts[0]

    if action == "m":
        await _menu(q, context, parts[1])
    elif action == "g":
        await _game_select(q, context, parts[1])
    elif action == "b":
        await _bet(q, context, parts[1], int(parts[2]))
    elif action == "p":
        await _play(q, context, parts)
    elif action == "dep":
        await _deposit(q, context, parts)
    elif action == "crypto":
        await _crypto_pay(q, context, parts)
    elif action == "tower":
        await _tower(q, context, parts)
    elif action == "mines":
        await _mines(q, context, parts)
    elif action == "adm":
        await _admin_cb(q, context, parts)

# ─── МЕНЮ ────────────────────────────────────────────────────────────────────

async def _menu(q, context, section: str):
    uid = q.from_user.id

    if section == "main":
        bal = db.get_balance(uid)
        text = f"🎰 *VIP Casino*\n\n💼 Баланс: *{fmt(bal)}*\n\nВыбери раздел:"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb_main())

    elif section == "games":
        await q.edit_message_text(
            "🎮 *Выбери игру:*\n\nШанс выигрыша в каждой игре особый. Удачи! 🍀",
            parse_mode="Markdown", reply_markup=kb_games()
        )

    elif section == "balance":
        bal = db.get_balance(uid)
        await q.edit_message_text(
            f"💼 *Твой баланс*\n\n{fmt(bal)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Пополнить", callback_data="m:deposit")],
                [InlineKeyboardButton("➖ Вывести", callback_data="m:withdraw")],
                [InlineKeyboardButton("🔙 Назад", callback_data="m:main")],
            ])
        )

    elif section == "deposit":
        await q.edit_message_text(
            "💳 *Пополнение баланса*\n\nВыбери способ оплаты:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Telegram Stars", callback_data="dep:stars")],
                [InlineKeyboardButton("💎 CryptoBot (USDT/BTC/TON)", callback_data="dep:crypto")],
                [InlineKeyboardButton("🔙 Назад", callback_data="m:main")],
            ])
        )

    elif section == "withdraw":
        bal = db.get_balance(uid)
        if bal < config.MIN_WITHDRAWAL:
            await q.edit_message_text(
                f"❌ Минимум для вывода: *{fmt(config.MIN_WITHDRAWAL)}*\n"
                f"Твой баланс: *{fmt(bal)}*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="m:main")]
                ])
            )
            return
        context.user_data["state"] = "withdraw"
        await q.edit_message_text(
            f"💸 *Вывод средств*\n\n"
            f"Баланс: *{fmt(bal)}*\n"
            f"Минимум: *{fmt(config.MIN_WITHDRAWAL)}*\n\n"
            f"Напиши сумму и реквизиты одним сообщением:\n"
            f"`100 @username` или `500 USDT TRC20: TxADDRESS`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Отмена", callback_data="m:main")]
            ])
        )

    elif section == "top":
        rows = db.get_top_users(10)
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = ["🏆 *Топ 10 игроков*\n"]
        for i, u in enumerate(rows):
            name = u["first_name"] or u["username"] or f"Player{u['user_id']}"
            lines.append(f"{medals[i]} *{name}* — {fmt(u['balance'])}")
        await q.edit_message_text(
            "\n".join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="m:main")]
            ])
        )

    elif section == "stats":
        user_row = db.get_user(uid)
        gs = db.get_game_stats(uid)
        text = (
            f"📊 *Твоя статистика*\n\n"
            f"💼 Баланс: *{user_row['balance']}*\n"
            f"🎰 Всего игр: *{gs['total_bets']}*\n"
            f"✅ Побед: *{gs['total_won']}*\n"
            f"❌ Поражений: *{gs['total_lost']}*\n"
            f"🏆 Лучший выигрыш: *{fmt(gs['biggest_win'])}*\n"
            f"📅 В игре с: *{user_row['registered_at'][:10]}*"
        )
        await q.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="m:main")]
            ])
        )

    elif section == "referral":
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={uid}"
        await q.edit_message_text(
            f"👥 *Реферальная программа*\n\n"
            f"Приглашай друзей и получай бонусы!\n\n"
            f"🎁 Тебе: *+{fmt(config.REFERRAL_BONUS_REFERRER)}* за каждого\n"
            f"🎁 Другу: *+{fmt(config.REFERRAL_BONUS_INVITED)}* при регистрации\n\n"
            f"Твоя ссылка:\n`{link}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="m:main")]
            ])
        )

# ─── ПОПОЛНЕНИЕ ──────────────────────────────────────────────────────────────

async def _deposit(q, context, parts):
    method = parts[1]
    uid = q.from_user.id

    if method == "stars":
        buttons = [
            [InlineKeyboardButton(f"⭐ 10 Stars = 100 {config.TOKEN_EMOJI}", callback_data="dep:stars_buy:10:100")],
            [InlineKeyboardButton(f"⭐ 50 Stars = 500 {config.TOKEN_EMOJI}", callback_data="dep:stars_buy:50:500")],
            [InlineKeyboardButton(f"⭐ 100 Stars = 1000 {config.TOKEN_EMOJI}", callback_data="dep:stars_buy:100:1000")],
            [InlineKeyboardButton("🔙 Назад", callback_data="m:deposit")]
        ]
        await q.edit_message_text(
            "⭐ *Пополнение через Telegram Stars*\n\nВыбери пакет:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif method == "stars_buy":
        stars = int(parts[2])
        tokens = int(parts[3])
        try:
            await context.bot.send_invoice(
                chat_id=uid,
                title=f"VIP Casino — {tokens} токенов",
                description=f"Пополнение: {tokens} {config.TOKEN_EMOJI}",
                payload=f"stars:{uid}:{tokens}",
                currency="XTR",
                prices=[LabeledPrice(f"{tokens} Токенов", stars)],
            )
            await q.edit_message_text(
                "✅ Счёт выставлен — посмотри выше!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Меню", callback_data="m:main")]
                ])
            )
        except Exception as e:
            logger.error(f"Stars invoice error: {e}")
            await q.edit_message_text(
                "❌ Ошибка при выставлении счёта.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="m:deposit")]
                ])
            )

    elif method == "crypto":
        await q.edit_message_text(
            "💎 *Пополнение через CryptoBot*\n\n"
            "Выбери криптовалюту:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 USDT (TRC-20)", callback_data="crypto:usdt")],
                [InlineKeyboardButton("₿ Bitcoin (BTC)", callback_data="crypto:btc")],
                [InlineKeyboardButton("🔘 TON", callback_data="crypto:ton")],
                [InlineKeyboardButton("🔙 Назад", callback_data="m:deposit")]
            ])
        )

async def _crypto_pay(q, context, parts):
    currency = parts[1].upper()
    uid = q.from_user.id
    
    await q.edit_message_text(
        f"💎 *Пополнение через CryptoBot*\n\n"
        f"Валюта: {currency}\n\n"
        f"Введите сумму в USD (минимум 10):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="m:deposit")]
        ])
    )
    context.user_data["crypto_currency"] = currency
    context.user_data["state"] = "crypto_amount"

# ─── ВЫБОР ИГРЫ И СТАВКИ ────────────────────────────────────────────────────

GAME_INFO = {
    "coinflip": ("🪙 Орёл и Решка", "Угадай сторону монеты!\nВыигрыш: ×2"),
    "dice": ("🎲 Кости", "Угадай чётное/нечётное!\nВыигрыш: ×2"),
    "darts": ("🎯 Дартс", "Попади в яблочко!\nВыигрыш: ×2.5"),
    "basketball": ("🏀 Баскетбол", "Забрось мяч в кольцо!\nВыигрыш: ×2.5"),
    "football": ("⚽ Футбол", "Выбери угол и забей гол!\nВыигрыш: ×2.5"),
    "mines": ("💣 Мины", "Открывай клетки — избегай мин!\nЧем дальше — тем выше куш"),
    "tower": ("🗼 Башня", "Поднимайся вверх — выигрыш растёт!\nОстановись вовремя!"),
}

async def _game_select(q, context, game: str):
    if game not in GAME_INFO:
        return
    title, desc = GAME_INFO[game]
    await q.edit_message_text(
        f"{title}\n\n{desc}\n\n{config.TOKEN_EMOJI} *Выбери ставку:*",
        parse_mode="Markdown",
        reply_markup=kb_bet(game)
    )

async def _bet(q, context, game: str, amount: int):
    uid = q.from_user.id
    bal = db.get_balance(uid)

    if bal < amount:
        await q.answer(f"❌ Недостаточно токенов! Баланс: {fmt(bal)}", show_alert=True)
        return

    context.user_data["bet"] = amount
    context.user_data["game"] = game

    if game == "mines":
        await _start_mines(q, context, amount)
        return
    if game == "tower":
        await _start_tower(q, context, amount)
        return

    if game == "coinflip":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🦅 Орёл", callback_data=f"p:coinflip:heads:{amount}"),
             InlineKeyboardButton("🪙 Решка", callback_data=f"p:coinflip:tails:{amount}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:coinflip")],
        ])
    elif game == "dice":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("2⃣ Чётное", callback_data=f"p:dice:even:{amount}"),
             InlineKeyboardButton("1⃣ Нечётное", callback_data=f"p:dice:odd:{amount}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:dice")],
        ])
    elif game == "football":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↖️ Лево", callback_data=f"p:football:left:{amount}"),
             InlineKeyboardButton("⬆️ Центр", callback_data=f"p:football:center:{amount}"),
             InlineKeyboardButton("↗️ Право", callback_data=f"p:football:right:{amount}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:football")],
        ])
    else:
        action_label = {"darts": "🎯 Бросить!", "basketball": "🏀 Бросить!"}
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(action_label.get(game, "▶️ Играть!"), callback_data=f"p:{game}:throw:{amount}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:{game}")],
        ])

    await q.edit_message_text(
        f"{GAME_INFO[game][0]}\n\n💰 Ставка: *{fmt(amount)}*\n\nВыбери:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ─── ИГРЫ (упрощенно) ────────────────────────────────────────────────────────

async def _play(q, context, parts):
    game = parts[1]
    choice = parts[2]
    amount = int(parts[3])
    uid = q.from_user.id
    bal = db.get_balance(uid)

    if bal < amount:
        await q.answer("❌ Недостаточно токенов!", show_alert=True)
        return

    won = win_check()
    mult = 2.0 if game in ["coinflip", "dice"] else 2.5
    payout = amount * mult

    if won:
        db.update_balance(uid, payout - amount)
        db.add_transaction(uid, "win", payout - amount, f"{game} win")
        db.update_game_stats(uid, True, payout, amount)
        msg = f"🎉 *ПОБЕДА!* +{fmt(payout - amount)}\n💼 Баланс: {fmt(db.get_balance(uid))}"
    else:
        db.update_balance(uid, -amount)
        db.add_transaction(uid, "loss", -amount, f"{game} loss")
        db.update_game_stats(uid, False, 0, amount)
        msg = f"😞 *Проигрыш!* -{fmt(amount)}\n💼 Баланс: {fmt(db.get_balance(uid))}"

    await q.edit_message_text(
        f"{GAME_INFO[game][0]}\n\n{msg}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ещё раз", callback_data=f"g:{game}")],
            [InlineKeyboardButton("🎮 Все игры", callback_data="m:games")],
            [InlineKeyboardButton("🏠 Меню", callback_data="m:main")],
        ])
    )

# ─── МИНЫ ────────────────────────────────────────────────────────────────────

MINES_GRID = 9
MINES_COUNT = 3
MINES_MULTS = [1.5, 2.2, 3.5, 5.5, 9.0, 15.0]

async def _start_mines(q, context, bet: int):
    uid = q.from_user.id
    bal = db.get_balance(uid)
    if bal < bet:
        await q.answer("❌ Недостаточно токенов!", show_alert=True)
        return

    mines = set(random.sample(range(MINES_GRID), MINES_COUNT))
    db.update_balance(uid, -bet)
    context.user_data["mines"] = {
        "bet": bet,
        "mines": list(mines),
        "revealed": [],
        "active": True,
    }

    await q.edit_message_text(
        f"💣 *Мины* — {MINES_COUNT} мины\n\n💰 Ставка: *{fmt(bet)}*",
        parse_mode="Markdown",
        reply_markup=_mines_kb([], bet, 0, [])
    )

def _mines_kb(revealed, bet, safe_count, mines, bust_cell=None):
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx = r * 3 + c
            if idx == bust_cell:
                row.append(InlineKeyboardButton("💥", callback_data="mines:_dead"))
            elif idx in mines and bust_cell is not None:
                row.append(InlineKeyboardButton("💣", callback_data="mines:_dead"))
            elif idx in revealed:
                row.append(InlineKeyboardButton("💚", callback_data="mines:_safe"))
            else:
                row.append(InlineKeyboardButton("⬜", callback_data=f"mines:pick:{idx}"))
        rows.append(row)

    if bust_cell is None and safe_count > 0:
        mult = MINES_MULTS[min(safe_count - 1, len(MINES_MULTS) - 1)]
        payout = int(bet * mult)
        rows.append([InlineKeyboardButton(f"💰 Забрать {payout} {config.TOKEN_EMOJI}", callback_data=f"mines:cashout:{safe_count}")])
    return InlineKeyboardMarkup(rows)

async def _mines(q, context, parts):
    action = parts[1]
    uid = q.from_user.id

    state = context.user_data.get("mines", {})
    if not state.get("active"):
        await q.answer("⚠️ Начни новую игру", show_alert=True)
        return

    bet = state["bet"]
    mines = state["mines"]
    revealed = state["revealed"]

    if action == "pick":
        cell = int(parts[2])
        if cell in revealed:
            await q.answer("Уже открыто!", show_alert=False)
            return

        if cell in mines:
            context.user_data["mines"] = {"active": False}
            db.add_transaction(uid, "loss", -bet, "Mines boom")
            db.update_game_stats(uid, False, 0, bet)
            await q.edit_message_text(
                f"💣 *Мины — БОООМ!* 💥\n\nСтавка: -{fmt(bet)}\n💼 Баланс: {fmt(db.get_balance(uid))}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Играть снова", callback_data="g:mines")],
                    [InlineKeyboardButton("🏠 Меню", callback_data="m:main")],
                ])
            )
        else:
            revealed.append(cell)
            state["revealed"] = revealed
            safe_count = len(revealed)
            mult = MINES_MULTS[min(safe_count - 1, len(MINES_MULTS) - 1)]
            payout = int(bet * mult)

            max_safe = MINES_GRID - MINES_COUNT
            if safe_count >= max_safe:
                db.update_balance(uid, payout)
                db.add_transaction(uid, "win", payout - bet, "Mines full clear")
                db.update_game_stats(uid, True, payout, bet)
                context.user_data["mines"] = {"active": False}
                await q.edit_message_text(
                    f"💣 *Мины — Все клетки открыты!* 🏆\n\n💰 Выигрыш: *{fmt(payout)}*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Играть снова", callback_data="g:mines")]
                    ])
                )
            else:
                await q.edit_message_text(
                    f"💣 *Мины*\n\n💰 Ставка: *{fmt(bet)}*\nОткрыто: {safe_count} | Множитель: ×{mult}\nПотенциальный выигрыш: *{fmt(payout)}*",
                    parse_mode="Markdown",
                    reply_markup=_mines_kb(revealed, bet, safe_count, [])
                )

    elif action == "cashout":
        safe_count = int(parts[2])
        mult = MINES_MULTS[min(safe_count - 1, len(MINES_MULTS) - 1)]
        payout = int(bet * mult)
        db.update_balance(uid, payout)
        db.add_transaction(uid, "win", payout - bet, f"Mines cashout {safe_count}")
        db.update_game_stats(uid, True, payout, bet)
        context.user_data["mines"] = {"active": False}
        await q.edit_message_text(
            f"💣 *Мины — Выигрыш!*\n\n💰 Забрал: *{fmt(payout)}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Играть снова", callback_data="g:mines")],
                [InlineKeyboardButton("🏠 Меню", callback_data="m:main")],
            ])
        )

# ─── БАШНЯ ───────────────────────────────────────────────────────────────────

TOWER_FLOORS = 10
TOWER_MULTS = [1.5, 2.0, 3.0, 4.5, 6.5, 9.5, 14.0, 21.0, 32.0, 50.0]
TOWER_SURVIVE = 0.55

async def _start_tower(q, context, bet: int):
    uid = q.from_user.id
    bal = db.get_balance(uid)
    if bal < bet:
        await q.answer("❌ Недостаточно токенов!", show_alert=True)
        return

    db.update_balance(uid, -bet)
    context.user_data["tower"] = {"bet": bet, "floor": 0, "active": True}
    await q.edit_message_text(_tower_text(bet, 0), parse_mode="Markdown", reply_markup=_tower_kb(bet, 0))

def _tower_text(bet, floor):
    lines = ["🗼 *Башня*\n"]
    for i in range(TOWER_FLOORS, -1, -1):
        mult = TOWER_MULTS[i - 1] if i > 0 else 1.0
        if i == floor:
            mark = "👤 ◀ ТЫ ЗДЕСЬ"
        elif i < floor:
            mark = "✅"
        else:
            mark = f"×{mult}"
        lines.append(f"{'🔟' if i==10 else str(i)+'  '} {mark}")
    lines.append(f"\n💰 Ставка: *{bet} {config.TOKEN_EMOJI}*")
    if floor > 0:
        pot = int(bet * TOWER_MULTS[floor - 1])
        lines.append(f"🎯 Можно забрать: *{pot} {config.TOKEN_EMOJI}*")
    return "\n".join(lines)

def _tower_kb(bet, floor):
    rows = []
    if floor > 0:
        pot = int(bet * TOWER_MULTS[floor - 1])
        rows.append([InlineKeyboardButton(f"💰 Забрать {pot} {config.TOKEN_EMOJI}", callback_data=f"tower:cashout:{bet}:{floor}")])
    if floor < TOWER_FLOORS:
        rows.append([InlineKeyboardButton("⬆️ Подняться выше", callback_data=f"tower:climb:{bet}:{floor}")])
    rows.append([InlineKeyboardButton("🎮 Все игры", callback_data="m:games")])
    return InlineKeyboardMarkup(rows)

async def _tower(q, context, parts):
    action = parts[1]
    bet = int(parts[2])
    floor = int(parts[3])
    uid = q.from_user.id

    state = context.user_data.get("tower", {})
    if not state.get("active"):
        await q.answer("⚠️ Начни новую игру", show_alert=True)
        return

    if action == "cashout":
        payout = int(bet * TOWER_MULTS[floor - 1]) if floor > 0 else bet
        db.update_balance(uid, payout)
        db.add_transaction(uid, "win", payout - bet, f"Tower cashout floor {floor}")
        db.update_game_stats(uid, True, payout, bet)
        context.user_data["tower"] = {"active": False}
        await q.edit_message_text(
            f"🗼 *Башня — Выигрыш!*\n\n💰 Забрал: *{fmt(payout)}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Играть снова", callback_data="g:tower")],
                [InlineKeyboardButton("🏠 Меню", callback_data="m:main")],
            ])
        )
    elif action == "climb":
        next_floor = floor + 1
        exploded = random.random() > TOWER_SURVIVE

        if exploded:
            db.add_transaction(uid, "loss", -bet, f"Tower explode floor {next_floor}")
            db.update_game_stats(uid, False, 0, bet)
            context.user_data["tower"] = {"active": False}
            await q.edit_message_text(
                f"🗼 *Башня — ВЗРЫВ!* 💥\n\nСтавка: -{fmt(bet)}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Играть снова", callback_data="g:tower")],
                    [InlineKeyboardButton("🏠 Меню", callback_data="m:main")],
                ])
            )
        else:
            context.user_data["tower"]["floor"] = next_floor
            if next_floor == TOWER_FLOORS:
                payout = int(bet * TOWER_MULTS[TOWER_FLOORS - 1])
                db.update_balance(uid, payout)
                db.add_transaction(uid, "win", payout - bet, "Tower top!")
                db.update_game_stats(uid, True, payout, bet)
                context.user_data["tower"] = {"active": False}
                await q.edit_message_text(
                    f"🗼 *БАШНЯ ПОКОРЕНА!* 🏆\n\n💰 Выигрыш: *{fmt(payout)}*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Играть снова", callback_data="g:tower")]
                    ])
                )
            else:
                await q.edit_message_text(_tower_text(bet, next_floor), parse_mode="Markdown", reply_markup=_tower_kb(bet, next_floor))

# ─── ПЛАТЕЖИ ─────────────────────────────────────────────────────────────────

async def precheckout(update: Update, context: CallbackContext):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: CallbackContext):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user = update.effective_user

    if payload.startswith("stars:"):
        _, uid_s, tokens_s = payload.split(":")
        uid = int(uid_s)
        tokens = int(tokens_s)
        db.update_balance(uid, tokens)
        db.add_transaction(uid, "deposit", tokens, f"Stars ×{payment.total_amount}")

        await update.message.reply_text(
            f"✅ *Оплата прошла!*\n\nНачислено: *{fmt(tokens)}*",
            parse_mode="Markdown",
            reply_markup=kb_main()
        )

# ─── ОБРАБОТКА СООБЩЕНИЙ ─────────────────────────────────────────────────────

async def message_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    text = update.message.text.strip()
    state = context.user_data.get("state")

    ensure_registered(user)

    if state == "crypto_amount":
        try:
            amount = float(text)
            if amount < 10:
                await update.message.reply_text("❌ Минимальная сумма: 10 USD")
                return
            
            currency = context.user_data.get("crypto_currency", "USDT")
            invoice_url = create_cryptobot_invoice(user.id, amount, currency)
            
            if invoice_url:
                await update.message.reply_text(
                    f"💎 *Счет на оплату*\n\n"
                    f"Сумма: ${amount} {currency}\n\n"
                    f"[Оплатить через CryptoBot]({invoice_url})\n\n"
                    f"После оплаты токены начислятся автоматически!",
                    parse_mode="Markdown",
                    reply_markup=kb_main()
                )
                context.user_data["state"] = None
            else:
                await update.message.reply_text(
                    "❌ Ошибка создания счета. Попробуйте позже.",
                    reply_markup=kb_main()
                )
        except ValueError:
            await update.message.reply_text("❌ Введите число (сумму в USD)")

    elif state == "withdraw":
        parts = text.split(None, 1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Формат: `сумма реквизиты`", parse_mode="Markdown")
            return

        try:
            amount = float(parts[0])
            details = parts[1]
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы")
            return

        bal = db.get_balance(user.id)
        if amount < config.MIN_WITHDRAWAL:
            await update.message.reply_text(f"❌ Минимум: {fmt(config.MIN_WITHDRAWAL)}")
            return
        if bal < amount:
            await update.message.reply_text(f"❌ Недостаточно токенов. Баланс: {fmt(bal)}")
            return

        db.update_balance(user.id, -amount)
        dep_id = db.add_withdrawal(user.id, amount, details)
        context.user_data["state"] = None

        await update.message.reply_text(
            f"✅ *Заявка на вывод принята!*\n\nСумма: {fmt(amount)}",
            parse_mode="Markdown",
            reply_markup=kb_main()
        )
        
        send_message_to_admin(f"💸 Запрос на вывод #{dep_id}\n👤 {user.first_name}\n💎 {fmt(amount)}\n📝 {details}")

    else:
        await update.message.reply_text("🎰 *VIP Casino*\n\nНажми /start", parse_mode="Markdown", reply_markup=kb_main())

# ─── АДМИН КОМАНДЫ ──────────────────────────────────────────────────────────

async def cmd_addbalance(update: Update, context: CallbackContext):
    if update.effective_user.id != config.ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /addbalance <user_id> <amount>")
        return
    try:
        uid = int(args[0])
        amount = float(args[1])
        db.update_balance(uid, amount)
        db.add_transaction(uid, "admin", amount, "Ручное начисление")
        await update.message.reply_text(f"✅ Начислено {fmt(amount)} пользователю {uid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_broadcast(update: Update, context: CallbackContext):
    if update.effective_user.id != config.ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return
    text = " ".join(context.args)
    users = db.get_top_users(9999)
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(u["user_id"], text)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} пользователям")

async def _admin_cb(q, context, parts):
    if q.from_user.id != config.ADMIN_ID:
        await q.answer("❌ Нет доступа", show_alert=True)
        return

    action = parts[1]
    dep_id = int(parts[2])

    if action == "approve":
        dep = db.approve_deposit(dep_id)
        if dep:
            await q.edit_message_text(q.message.text + "\n\n✅ ОДОБРЕНО", parse_mode="Markdown")
    elif action == "reject":
        dep = db.reject_deposit(dep_id)
        if dep:
            await q.edit_message_text(q.message.text + "\n\n❌ ОТКЛОНЕНО", parse_mode="Markdown")

# ─── ЗАПУСК ──────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    logger.info("База данных инициализирована")

    # Запускаем webhook для CryptoBot
    if config.CRYPTOBOT_API_KEY:
        start_webhook()
        logger.info("CryptoBot webhook запущен")

    updater = Updater(token=config.8603411643:AAEFOuhoBvnmh90h4MK9PsqQnot5uQGkmTY, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("addbalance", cmd_addbalance))
    dp.add_handler(CommandHandler("broadcast", cmd_broadcast))
    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(PreCheckoutQueryHandler(precheckout))
    dp.add_handler(MessageHandler(Filters.successful_payment, successful_payment))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, message_handler))

    logger.info("Бот запускается...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
