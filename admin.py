"""Админ-функции для бота"""

import database as db

def fmt(amount):
    return f"{amount:,.0f} 💎"

async def admin_bonus(update, context, user_id, amount):
    """Выдать бонус пользователю"""
    if update.effective_user.id != context.bot_data.get("admin_id"):
        await update.message.reply_text("❌ Нет доступа")
        return False
    
    db.update_balance(user_id, amount)
    db.add_transaction(user_id, "admin_bonus", amount, f"Бонус от администратора")
    
    await update.message.reply_text(f"✅ Выдано {fmt(amount)} пользователю {user_id}")
    
    try:
        await context.bot.send_message(
            user_id,
            f"🎁 *Вам выдан бонус!*\n\n{fmt(amount)} зачислено на баланс!",
            parse_mode="Markdown"
        )
    except:
        pass
    return True

async def admin_broadcast(update, context, message):
    """Сделать рассылку всем пользователям"""
    if update.effective_user.id != context.bot_data.get("admin_id"):
        await update.message.reply_text("❌ Нет доступа")
        return
    
    users = db.get_all_users()
    sent = 0
    for user in users:
        try:
            await context.bot.send_message(user["user_id"], message)
            sent += 1
        except:
            pass
    
    await update.message.reply_text(f"✅ Отправлено {sent} пользователям")

async def admin_stats(update, context):
    """Показать статистику бота"""
    if update.effective_user.id != context.bot_data.get("admin_id"):
        await update.message.reply_text("❌ Нет доступа")
        return
    
    total_users = db.get_user_count()
    total_balance = db.get_total_balance()
    
    text = f"📊 *Статистика бота*\n\n"
    text += f"👥 Всего пользователей: *{total_users}*\n"
    text += f"💰 Общий баланс: *{fmt(total_balance)}*\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")
