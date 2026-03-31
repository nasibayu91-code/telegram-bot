"""
VIP Casino Bot — главный файл
Игры: Орёл/Решка, Кости, Дартс, Баскетбол, Футбол, Мины, Башня
Платежи: Telegram Stars, USD (вручную)
"""
import cryptobot
import asyncio
import logging
import random
import sys

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, PreCheckoutQueryHandler,
    filters, ContextTypes
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


# ─── УТИЛИТЫ ─────────────────────────────────────────────────────────────────

def fmt(amount: float) -> str:
    return f"{amount:,.0f} {config.TOKEN_EMOJI}"


def win_check() -> bool:
    """Победа с вероятностью WIN_RATE (30%)."""
    return random.random() < config.WIN_RATE


def ensure_registered(user):
    db.register_user(user.id, user.username or "", user.first_name or "")


# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────

def kb_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎮 Игры",       callback_data="m:games"),
            InlineKeyboardButton("💼 Баланс",     callback_data="m:balance"),
        ],
        [
            InlineKeyboardButton("➕ Пополнить",  callback_data="m:deposit"),
            InlineKeyboardButton("➖ Вывести",    callback_data="m:withdraw"),
        ],
        [
            InlineKeyboardButton("🏆 Топ игроков", callback_data="m:top"),
            InlineKeyboardButton("📊 Статистика",  callback_data="m:stats"),
        ],
        [
            InlineKeyboardButton("👥 Реферал",    callback_data="m:referral"),
        ],
    ])


def kb_games():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🪙 Орёл/Решка",  callback_data="g:coinflip"),
            InlineKeyboardButton("🎲 Кости",       callback_data="g:dice"),
        ],
        [
            InlineKeyboardButton("🎯 Дартс",       callback_data="g:darts"),
            InlineKeyboardButton("🏀 Баскетбол",   callback_data="g:basketball"),
        ],
        [
            InlineKeyboardButton("⚽ Футбол",      callback_data="g:football"),
            InlineKeyboardButton("💣 Мины",        callback_data="g:mines"),
        ],
        [
            InlineKeyboardButton("🗼 Башня",       callback_data="g:tower"),
        ],
        [InlineKeyboardButton("🔙 Главное меню",  callback_data="m:main")],
    ])


def kb_bet(game: str):
    amounts = [1, 5, 10, 25, 50, 100, 250, 500, 1000]
    rows = []
    row  = []
    for amt in amounts:
        row.append(InlineKeyboardButton(
            f"{amt}{config.TOKEN_EMOJI}", callback_data=f"b:{game}:{amt}"
        ))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m:games")])
    return InlineKeyboardMarkup(rows)


def kb_back_games():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Ещё раз",     callback_data="m:games")],
        [InlineKeyboardButton("🎮 Все игры",    callback_data="m:games")],
        [InlineKeyboardButton("🏠 Меню",        callback_data="m:main")],
    ])


# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # реферал?
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

        # Реферальные бонусы
        if ref_id and db.get_user(ref_id):
            db.update_balance(user.id,   config.REFERRAL_BONUS_INVITED)
            db.update_balance(ref_id,    config.REFERRAL_BONUS_REFERRER)
            db.add_transaction(user.id,  "bonus", config.REFERRAL_BONUS_INVITED,  "Реферальный бонус")
            db.add_transaction(ref_id,   "bonus", config.REFERRAL_BONUS_REFERRER, "Реферальный бонус")
            text += f"\n➕ Реферальный бонус: +{fmt(config.REFERRAL_BONUS_INVITED)}"
            try:
                await context.bot.send_message(
                    ref_id,
                    f"👥 По твоей ссылке зарегистрировался новый игрок!\n"
                    f"💰 Бонус: +{fmt(config.REFERRAL_BONUS_REFERRER)}"
                )
            except Exception:
                pass
    else:
        bal = db.get_balance(user.id)
        text = (
            f"🎰 *VIP Casino*\n\n"
            f"С возвращением, *{user.first_name}*!\n"
            f"💼 Баланс: *{fmt(bal)}*"
        )

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb_main())


# ─── ГЛАВНЫЙ CALLBACK ────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ensure_registered(q.from_user)

    parts  = q.data.split(":")
    action = parts[0]

    if   action == "m":  await _menu(q, context, parts[1])
    elif action == "g":  await _game_select(q, context, parts[1])
    elif action == "b":  await _bet(q, context, parts[1], int(parts[2]))
    elif action == "p":  await _play(q, context, parts)
    elif action == "dep": await _deposit(q, context, parts)
    elif action == "tower": await _tower(q, context, parts)
    elif action == "mines": await _mines(q, context, parts)
    elif action == "adm":   await _admin_cb(q, context, parts)


# ─── МЕНЮ ────────────────────────────────────────────────────────────────────

async def _menu(q, context, section: str):
    uid = q.from_user.id

    if section == "main":
        bal  = db.get_balance(uid)
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
                [InlineKeyboardButton("➖ Вывести",   callback_data="m:withdraw")],
                [InlineKeyboardButton("🔙 Назад",     callback_data="m:main")],
            ])
        )

    elif section == "deposit":
        await q.edit_message_text(
            "💳 *Пополнение баланса*\n\nВыбери способ оплаты:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Telegram Stars",  callback_data="dep:stars")],
                [InlineKeyboardButton("💵 USD (вручную)",   callback_data="dep:usd")],
                [InlineKeyboardButton("🔙 Назад",           callback_data="m:main")],
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
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        lines  = ["🏆 *Топ 10 игроков*\n"]
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
        user_row  = db.get_user(uid)
        gs        = db.get_game_stats(uid)
        text = (
            f"📊 *Твоя статистика*\n\n"
            f"💼 Баланс: *{fmt(user_row['balance'])}*\n"
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


# ─── ВЫБОР ИГРЫ ──────────────────────────────────────────────────────────────

GAME_INFO = {
    "coinflip":   ("🪙 Орёл и Решка",  "Угадай сторону монеты!\nВыигрыш: ×2"),
    "dice":       ("🎲 Кости",          "Угадай чётное/нечётное!\nВыигрыш: ×2"),
    "darts":      ("🎯 Дартс",          "Попади в яблочко!\nВыигрыш: ×2.5"),
    "basketball": ("🏀 Баскетбол",      "Забрось мяч в кольцо!\nВыигрыш: ×2.5"),
    "football":   ("⚽ Футбол",         "Выбери угол и забей гол!\nВыигрыш: ×2.5"),
    "mines":      ("💣 Мины",           "Открывай клетки — избегай мин!\nЧем дальше — тем выше куш"),
    "tower":      ("🗼 Башня",          "Поднимайся вверх — выигрыш растёт!\nОстановись вовремя!"),
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


# ─── СТАВКА ──────────────────────────────────────────────────────────────────

async def _bet(q, context, game: str, amount: int):
    uid = q.from_user.id
    bal = db.get_balance(uid)

    if bal < amount:
        await q.answer(f"❌ Недостаточно токенов! Баланс: {fmt(bal)}", show_alert=True)
        return

    context.user_data["bet"]  = amount
    context.user_data["game"] = game

    title, _ = GAME_INFO.get(game, ("Игра", ""))

    # Специальные экраны для сложных игр
    if game == "mines":
        await _start_mines(q, context, amount)
        return
    if game == "tower":
        await _start_tower(q, context, amount)
        return

    # Простые игры: выбор стороны / действия
    if game == "coinflip":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🦅 Орёл",  callback_data=f"p:coinflip:heads:{amount}"),
                InlineKeyboardButton("🪙 Решка", callback_data=f"p:coinflip:tails:{amount}"),
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:coinflip")],
        ])
    elif game == "dice":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("2⃣ Чётное",    callback_data=f"p:dice:even:{amount}"),
                InlineKeyboardButton("1⃣ Нечётное",  callback_data=f"p:dice:odd:{amount}"),
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:dice")],
        ])
    elif game == "football":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("↖️ Лево",   callback_data=f"p:football:left:{amount}"),
                InlineKeyboardButton("⬆️ Центр",  callback_data=f"p:football:center:{amount}"),
                InlineKeyboardButton("↗️ Право",  callback_data=f"p:football:right:{amount}"),
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:football")],
        ])
    else:  # darts, basketball
        action_label = {"darts": "🎯 Бросить!", "basketball": "🏀 Бросить!"}
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                action_label.get(game, "▶️ Играть!"),
                callback_data=f"p:{game}:throw:{amount}"
            )],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"g:{game}")],
        ])

    await q.edit_message_text(
        f"{title}\n\n💰 Ставка: *{fmt(amount)}*\n\nВыбери:",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ─── ИГРА (простые) ──────────────────────────────────────────────────────────

async def _play(q, context, parts):
    # parts: [p, game, choice, amount]
    game   = parts[1]
    choice = parts[2]
    amount = int(parts[3])
    uid    = q.from_user.id
    bal    = db.get_balance(uid)

    if bal < amount:
        await q.answer("❌ Недостаточно токенов!", show_alert=True)
        return

    won = win_check()

    # ── Орёл/Решка ──
    if game == "coinflip":
        result = choice if won else ("tails" if choice == "heads" else "heads")
        names  = {"heads": "🦅 Орёл", "tails": "🪙 Решка"}
        mult   = 2.0
        payout = amount * mult

        if won:
            db.update_balance(uid, payout - amount)
            db.add_transaction(uid, "win", payout - amount, "Coinflip win")
            db.update_game_stats(uid, True, payout, amount)
            msg = (
                f"🪙 *Орёл и Решка*\n\n"
                f"Ты: {names[choice]} | Выпало: {names[result]}\n\n"
                f"🎉 *ПОБЕДА!* +{fmt(payout - amount)}\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}"
            )
        else:
            db.update_balance(uid, -amount)
            db.add_transaction(uid, "loss", -amount, "Coinflip loss")
            db.update_game_stats(uid, False, 0, amount)
            msg = (
                f"🪙 *Орёл и Решка*\n\n"
                f"Ты: {names[choice]} | Выпало: {names[result]}\n\n"
                f"😞 *Проигрыш!* -{fmt(amount)}\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}"
            )

    # ── Кости ──
    elif game == "dice":
        dice_val = random.randint(1, 6)
        if won:
            evens = [2, 4, 6]; odds = [1, 3, 5]
            dice_val = random.choice(evens if choice == "even" else odds)
        is_even     = dice_val % 2 == 0
        player_even = choice == "even"
        d_emoji     = ["","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣"]
        mult        = 2.0
        payout      = amount * mult

        if player_even == is_even:
            db.update_balance(uid, payout - amount)
            db.add_transaction(uid, "win", payout - amount, "Dice win")
            db.update_game_stats(uid, True, payout, amount)
            msg = (
                f"🎲 *Кости*\n\nВыпало: {d_emoji[dice_val]} ({dice_val})\n\n"
                f"🎉 *ПОБЕДА!* +{fmt(payout - amount)}\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}"
            )
        else:
            db.update_balance(uid, -amount)
            db.add_transaction(uid, "loss", -amount, "Dice loss")
            db.update_game_stats(uid, False, 0, amount)
            msg = (
                f"🎲 *Кости*\n\nВыпало: {d_emoji[dice_val]} ({dice_val})\n\n"
                f"😞 *Проигрыш!* -{fmt(amount)}\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}"
            )

    # ── Дартс / Баскетбол / Футбол ──
    elif game in ("darts", "basketball", "football"):
        mult   = 2.5
        payout = amount * mult
        emojis = {"darts": "🎯", "basketball": "🏀", "football": "⚽"}
        win_tx = {
            "darts":      "В яблочко! 🎯",
            "basketball": "МЯЧ В КОЛЬЦЕ! 🏀",
            "football":   "ГООООЛ! ⚽",
        }
        lose_tx = {
            "darts":      "Мимо! 🙈",
            "basketball": "Не попал! 😞",
            "football":   "Вратарь поймал! 🧤",
        }
        emoji = emojis[game]

        if won:
            db.update_balance(uid, payout - amount)
            db.add_transaction(uid, "win", payout - amount, f"{game} win")
            db.update_game_stats(uid, True, payout, amount)
            msg = (
                f"{emoji} *{GAME_INFO[game][0]}*\n\n"
                f"🎉 *{win_tx[game]}*\n"
                f"+{fmt(payout - amount)}\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}"
            )
        else:
            db.update_balance(uid, -amount)
            db.add_transaction(uid, "loss", -amount, f"{game} loss")
            db.update_game_stats(uid, False, 0, amount)
            msg = (
                f"{emoji} *{GAME_INFO[game][0]}*\n\n"
                f"😞 *{lose_tx[game]}*\n"
                f"-{fmt(amount)}\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}"
            )
    else:
        return

    await q.edit_message_text(
        msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ещё раз",   callback_data=f"g:{game}")],
            [InlineKeyboardButton("🎮 Все игры",  callback_data="m:games")],
            [InlineKeyboardButton("🏠 Меню",      callback_data="m:main")],
        ])
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  🗼  БАШНЯ
# ═══════════════════════════════════════════════════════════════════════════════

TOWER_FLOORS = 10
TOWER_MULTS  = [1.5, 2.0, 3.0, 4.5, 6.5, 9.5, 14.0, 21.0, 32.0, 50.0]
TOWER_SURVIVE = 0.55  # 55% выжить на каждом этаже


async def _start_tower(q, context, bet: int):
    uid = q.from_user.id
    bal = db.get_balance(uid)
    if bal < bet:
        await q.answer("❌ Недостаточно токенов!", show_alert=True)
        return

    db.update_balance(uid, -bet)
    context.user_data["tower"] = {"bet": bet, "floor": 0, "active": True}

    await q.edit_message_text(
        _tower_text(bet, 0),
        parse_mode="Markdown",
        reply_markup=_tower_kb(bet, 0)
    )


def _tower_text(bet: int, floor: int) -> str:
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


def _tower_kb(bet: int, floor: int) -> InlineKeyboardMarkup:
    rows = []
    if floor > 0:
        pot = int(bet * TOWER_MULTS[floor - 1])
        rows.append([InlineKeyboardButton(
            f"💰 Забрать {pot} {config.TOKEN_EMOJI}",
            callback_data=f"tower:cashout:{bet}:{floor}"
        )])
    if floor < TOWER_FLOORS:
        rows.append([InlineKeyboardButton(
            "⬆️ Подняться выше",
            callback_data=f"tower:climb:{bet}:{floor}"
        )])
    rows.append([InlineKeyboardButton("🎮 Все игры", callback_data="m:games")])
    return InlineKeyboardMarkup(rows)


async def _tower(q, context, parts):
    action = parts[1]
    bet    = int(parts[2])
    floor  = int(parts[3])
    uid    = q.from_user.id

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
            f"🗼 *Башня — Выигрыш!*\n\n"
            f"Этаж: {floor} / {TOWER_FLOORS}\n"
            f"💰 Забрал: *{fmt(payout)}*\n\n"
            f"💼 Баланс: {fmt(db.get_balance(uid))}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Играть снова", callback_data="g:tower")],
                [InlineKeyboardButton("🏠 Меню",         callback_data="m:main")],
            ])
        )

    elif action == "climb":
        next_floor = floor + 1
        exploded   = random.random() > TOWER_SURVIVE  # ~45% взрыв

        if exploded:
            db.add_transaction(uid, "loss", -bet, f"Tower explode floor {next_floor}")
            db.update_game_stats(uid, False, 0, bet)
            context.user_data["tower"] = {"active": False}
            await q.edit_message_text(
                f"🗼 *Башня — ВЗРЫВ!* 💥\n\n"
                f"Ловушка на этаже {next_floor}!\n"
                f"Ставка: -{fmt(bet)}\n\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Играть снова", callback_data="g:tower")],
                    [InlineKeyboardButton("🏠 Меню",         callback_data="m:main")],
                ])
            )
        else:
            context.user_data["tower"]["floor"] = next_floor
            if next_floor == TOWER_FLOORS:
                # Вершина!
                payout = int(bet * TOWER_MULTS[TOWER_FLOORS - 1])
                db.update_balance(uid, payout)
                db.add_transaction(uid, "win", payout - bet, "Tower top!")
                db.update_game_stats(uid, True, payout, bet)
                context.user_data["tower"] = {"active": False}
                await q.edit_message_text(
                    f"🗼 *БАШНЯ ПОКОРЕНА!* 🏆\n\n"
                    f"Ты прошёл все {TOWER_FLOORS} этажей!\n"
                    f"💰 Выигрыш: *{fmt(payout)}*\n\n"
                    f"💼 Баланс: {fmt(db.get_balance(uid))}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Играть снова", callback_data="g:tower")]
                    ])
                )
            else:
                await q.edit_message_text(
                    _tower_text(bet, next_floor),
                    parse_mode="Markdown",
                    reply_markup=_tower_kb(bet, next_floor)
                )


# ═══════════════════════════════════════════════════════════════════════════════
#  💣  МИНЫ
# ═══════════════════════════════════════════════════════════════════════════════

MINES_GRID  = 9   # 3×3
MINES_COUNT = 3   # 3 мины
MINES_MULTS = [1.5, 2.2, 3.5, 5.5, 9.0, 15.0]  # по количеству открытых


async def _start_mines(q, context, bet: int):
    uid = q.from_user.id
    bal = db.get_balance(uid)
    if bal < bet:
        await q.answer("❌ Недостаточно токенов!", show_alert=True)
        return

    mines = set(random.sample(range(MINES_GRID), MINES_COUNT))
    db.update_balance(uid, -bet)
    context.user_data["mines"] = {
        "bet":      bet,
        "mines":    list(mines),
        "revealed": [],
        "active":   True,
    }

    await q.edit_message_text(
        f"💣 *Мины* — {MINES_COUNT} мины на {MINES_GRID} клетках\n\n"
        f"💰 Ставка: *{fmt(bet)}*\n"
        f"Открыто: 0  |  Множитель: ×1.0",
        parse_mode="Markdown",
        reply_markup=_mines_kb([], bet, 0, [])
    )


def _mines_kb(revealed: list, bet: int, safe_count: int,
              mines: list, bust_cell: int = None) -> InlineKeyboardMarkup:
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
        mult    = MINES_MULTS[min(safe_count - 1, len(MINES_MULTS) - 1)]
        payout  = int(bet * mult)
        rows.append([InlineKeyboardButton(
            f"💰 Забрать {payout} {config.TOKEN_EMOJI}",
            callback_data=f"mines:cashout:{safe_count}"
        )])
    return InlineKeyboardMarkup(rows)


async def _mines(q, context, parts):
    action = parts[1]
    uid    = q.from_user.id

    if action in ("_dead", "_safe"):
        return  # no-op, just ignore taps on already-revealed cells

    state = context.user_data.get("mines", {})
    if not state.get("active"):
        await q.answer("⚠️ Начни новую игру", show_alert=True)
        return

    bet      = state["bet"]
    mines    = state["mines"]
    revealed = state["revealed"]

    if action == "pick":
        cell = int(parts[2])
        if cell in revealed:
            await q.answer("Уже открыто!", show_alert=False)
            return

        if cell in mines:
            # Взрыв!
            context.user_data["mines"] = {"active": False}
            db.add_transaction(uid, "loss", -bet, "Mines boom")
            db.update_game_stats(uid, False, 0, bet)
            await q.edit_message_text(
                f"💣 *Мины — БОООМ!* 💥\n\n"
                f"Ты нашёл мину на клетке {cell + 1}!\n"
                f"Ставка: -{fmt(bet)}\n\n"
                f"💼 Баланс: {fmt(db.get_balance(uid))}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Играть снова", callback_data="g:mines")],
                    [InlineKeyboardButton("🏠 Меню",         callback_data="m:main")],
                ])
            )
        else:
            revealed.append(cell)
            state["revealed"] = revealed
            safe_count = len(revealed)
            mult   = MINES_MULTS[min(safe_count - 1, len(MINES_MULTS) - 1)]
            payout = int(bet * mult)

            max_safe = MINES_GRID - MINES_COUNT
            if safe_count >= max_safe:
                # Все безопасные клетки открыты — авто-кешаут
                db.update_balance(uid, payout)
                db.add_transaction(uid, "win", payout - bet, "Mines full clear")
                db.update_game_stats(uid, True, payout, bet)
                context.user_data["mines"] = {"active": False}
                await q.edit_message_text(
                    f"💣 *Мины — Все клетки открыты!* 🏆\n\n"
                    f"💰 Выигрыш: *{fmt(payout)}*\n\n"
                    f"💼 Баланс: {fmt(db.get_balance(uid))}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Играть снова", callback_data="g:mines")]
                    ])
                )
            else:
                await q.edit_message_text(
                    f"💣 *Мины*\n\n"
                    f"💰 Ставка: *{fmt(bet)}*\n"
                    f"Открыто: {safe_count}  |  Множитель: ×{mult}\n"
                    f"Потенциальный выигрыш: *{fmt(payout)}*",
                    parse_mode="Markdown",
                    reply_markup=_mines_kb(revealed, bet, safe_count, [])
                )

    elif action == "cashout":
        safe_count = int(parts[2])
        mult   = MINES_MULTS[min(safe_count - 1, len(MINES_MULTS) - 1)]
        payout = int(bet * mult)
        db.update_balance(uid, payout)
        db.add_transaction(uid, "win", payout - bet, f"Mines cashout {safe_count}")
        db.update_game_stats(uid, True, payout, bet)
        context.user_data["mines"] = {"active": False}
        await q.edit_message_text(
            f"💣 *Мины — Выигрыш!*\n\n"
            f"✅ Открыто безопасных: {safe_count}\n"
            f"💰 Забрал: *{fmt(payout)}*\n\n"
            f"💼 Баланс: {fmt(db.get_balance(uid))}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Играть снова", callback_data="g:mines")],
                [InlineKeyboardButton("🏠 Меню",         callback_data="m:main")],
            ])
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  💳  ПОПОЛНЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

STARS_OPTIONS = [
    (10,   100),
    (50,   500),
    (100, 1000),
    (500, 5000),
]


async def _deposit(q, context, parts):
    method = parts[1]
    uid    = q.from_user.id

    if method == "stars":
        buttons = [[InlineKeyboardButton(
            f"⭐ {s} Stars = {t} {config.TOKEN_EMOJI}",
            callback_data=f"dep:stars_buy:{s}:{t}"
        )] for s, t in STARS_OPTIONS]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="m:deposit")])
        await q.edit_message_text(
            "⭐ *Пополнение через Telegram Stars*\n\nВыбери пакет:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif method == "stars_buy":
        stars  = int(parts[2])
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
                "❌ Ошибка при выставлении счёта. Попробуй позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="m:deposit")]
                ])
            )

    elif method == "usd":
    await q.edit_message_text(
        "💵 *Пополнение через CryptoBot*\n\n"
        "Выберите криптовалюту:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 USDT (TRC-20)", callback_data="crypto:usdt")],
            [InlineKeyboardButton("₿ Bitcoin", callback_data="crypto:btc")],
            [InlineKeyboardButton("🔘 TON", callback_data="crypto:ton")],
            [InlineKeyboardButton("🔙 Назад", callback_data="m:deposit")]
        ])
    )


# ─── Stars Pre-checkout & Successful Payment ─────────────────────────────────

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user    = update.effective_user

    if payload.startswith("stars:"):
        _, uid_s, tokens_s = payload.split(":")
        uid    = int(uid_s)
        tokens = int(tokens_s)
        db.update_balance(uid, tokens)
        db.add_transaction(uid, "deposit", tokens, f"Stars ×{payment.total_amount}")

        # уведомить админа
        try:
            await context.bot.send_message(
                config.ADMIN_ID,
                f"⭐ *Новый депозит (Stars)*\n\n"
                f"👤 {user.first_name} (@{user.username}) [{uid}]\n"
                f"⭐ Stars: {payment.total_amount}\n"
                f"💎 Начислено: {tokens} токенов",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ *Оплата прошла!*\n\n"
            f"Начислено: *{fmt(tokens)}*\n"
            f"💼 Баланс: {fmt(db.get_balance(uid))}",
            parse_mode="Markdown",
            reply_markup=kb_main()
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  ✉️  ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# ═══════════════════════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    text  = update.message.text.strip()
    state = context.user_data.get("state")

    ensure_registered(user)

    # ── Запрос суммы для USD депозита ──
    if state == "deposit_usd":
        try:
            usd = float(text)
            if usd < 1:
                await update.message.reply_text("❌ Минимум 1 USD")
                return
            tokens = int(usd * config.USD_TO_TOKENS)
            context.user_data["pending_usd"]   = {"usd": usd, "tokens": tokens}
            context.user_data["state"]         = "deposit_usd_proof"
            await update.message.reply_text(
                f"💵 *Сумма: ${usd} = {tokens} {config.TOKEN_EMOJI}*\n\n"
                f"Реквизиты для оплаты:\n"
                f"`{config.PAYMENT_DETAILS}`\n\n"
                f"После оплаты пришли *скриншот или txid* как следующее сообщение:",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ Введи число, например `5`", parse_mode="Markdown")

    # ── Чек/скриншот для USD депозита ──
    elif state == "deposit_usd_proof":
        pending = context.user_data.get("pending_usd")
        if not pending:
            context.user_data["state"] = None
            return

        dep_id = db.add_deposit(user.id, pending["tokens"], "USD", text)
        context.user_data["state"]       = None
        context.user_data["pending_usd"] = None

        # Уведомить админа
        try:
            await context.bot.send_message(
                config.ADMIN_ID,
                f"💰 *Новый депозит (USD)* — ID #{dep_id}\n\n"
                f"👤 {user.first_name} (@{user.username}) [{user.id}]\n"
                f"💵 ${pending['usd']} → {pending['tokens']} {config.TOKEN_EMOJI}\n"
                f"📝 Чек: {text}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Одобрить",  callback_data=f"adm:approve:{dep_id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"adm:reject:{dep_id}"),
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

        await update.message.reply_text(
            f"✅ *Заявка отправлена!*\n\n"
            f"Сумма: {pending['tokens']} {config.TOKEN_EMOJI}\n"
            f"Статус: ожидает проверки\n\n"
            f"Администратор проверит в течение 24 часов.",
            parse_mode="Markdown",
            reply_markup=kb_main()
        )

    # ── Запрос на вывод ──
    elif state == "withdraw":
        parts = text.split(None, 1)
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Формат: `сумма реквизиты`\n\nПример: `100 @username`",
                parse_mode="Markdown"
            )
            return

        try:
            amount  = float(parts[0])
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

        try:
            await context.bot.send_message(
                config.ADMIN_ID,
                f"💸 *Запрос на вывод* — ID #{dep_id}\n\n"
                f"👤 {user.first_name} (@{user.username}) [{user.id}]\n"
                f"💎 {fmt(amount)}\n"
                f"📝 Реквизиты: {details}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Выплачено",   callback_data=f"adm:paid:{dep_id}"),
                        InlineKeyboardButton("❌ Отклонить",   callback_data=f"adm:reject_w:{dep_id}"),
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

        await update.message.reply_text(
            f"✅ *Заявка на вывод принята!*\n\n"
            f"Сумма: {fmt(amount)}\n"
            f"Реквизиты: {details}\n\n"
            f"Выплата в течение 24 часов.",
            parse_mode="Markdown",
            reply_markup=kb_main()
        )

    else:
        # Неизвестное сообщение
        await update.message.reply_text(
            "🎰 *VIP Casino*\n\nНажми /start",
            parse_mode="Markdown",
            reply_markup=kb_main()
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  🔐  ADMIN CALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

async def _admin_cb(q, context, parts):
    if q.from_user.id != config.ADMIN_ID:
        await q.answer("❌ Нет доступа", show_alert=True)
        return

    action = parts[1]
    dep_id = int(parts[2])

    if action == "approve":
        dep = db.approve_deposit(dep_id)
        if dep:
            await q.edit_message_text(
                q.message.text + f"\n\n✅ ОДОБРЕНО — {dep['amount']} токенов начислено",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    dep["user_id"],
                    f"✅ *Депозит одобрен!*\n\n"
                    f"Начислено: *{fmt(dep['amount'])}*\n"
                    f"💼 Баланс: {fmt(db.get_balance(dep['user_id']))}",
                    parse_mode="Markdown",
                    reply_markup=kb_main()
                )
            except Exception:
                pass
        else:
            await q.answer("Уже обработано или не найдено", show_alert=True)

    elif action == "reject":
        dep = db.reject_deposit(dep_id)
        if dep:
            await q.edit_message_text(
                q.message.text + "\n\n❌ ОТКЛОНЕНО",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    dep["user_id"],
                    "❌ *Депозит отклонён.*\nОбратитесь в поддержку если это ошибка.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await q.answer("Не найдено", show_alert=True)

    elif action == "paid":
        dep = db.approve_withdrawal(dep_id)
        if dep:
            await q.edit_message_text(
                q.message.text + "\n\n✅ ВЫПЛАЧЕНО",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    dep["user_id"],
                    f"✅ *Вывод выполнен!*\n\n"
                    f"Сумма: {fmt(dep['amount'])} отправлена.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    elif action == "reject_w":
        dep = db.reject_withdrawal(dep_id)
        if dep:
            await q.edit_message_text(
                q.message.text + "\n\n❌ ОТКЛОНЕНО — токены возвращены",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    dep["user_id"],
                    f"❌ *Вывод отклонён.*\n\n"
                    f"Сумма {fmt(dep['amount'])} возвращена на баланс.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
#  🔧  ADMIN КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /addbalance <user_id> <amount>")
        return
    try:
        uid    = int(args[0])
        amount = float(args[1])
        db.update_balance(uid, amount)
        db.add_transaction(uid, "admin", amount, "Ручное начисление")
        await update.message.reply_text(f"✅ Начислено {fmt(amount)} пользователю {uid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return
    text = " ".join(context.args)
    users = db.get_top_users(9999)
    sent  = 0
    for u in users:
        try:
            await context.bot.send_message(u["user_id"], text)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} пользователям")


# ═══════════════════════════════════════════════════════════════════════════════
#  🚀  ЗАПУСК
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    db.init_db()
    logger.info("База данных инициализирована")

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("addbalance",   cmd_addbalance))
    app.add_handler(CommandHandler("broadcast",    cmd_broadcast))

    # Callback & inline
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Платежи
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # Текстовые сообщения
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, message_handler
    ))

    logger.info("Бот запускается...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
updater.start_polling()
# Запускаем webhook для CryptoBot
cryptobot.start_webhook()
