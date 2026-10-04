import logging
import random
import string
import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters,
)

# ==========================================
# ⚙ CONFIGURATION SECTION
# ==========================================
BOT_TOKEN = "8532758056:AAHzJXTiYv_GwngsBHa8T5c6_R08RTKJAT8"
ADMIN_ID = 8838495084
SUPPORT_USER = "@RAHUL_0G"

CHANNEL_1_URL = "https://t.me/qrworkofficial"
CHANNEL_2_URL = "https://t.me/+oLHeqPSRljU1YjA9"
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATABASE SETUP (SQLite Persistent Storage) ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            lang TEXT DEFAULT NULL,
            state TEXT DEFAULT NULL,
            withdraw_amount REAL DEFAULT 0.0,
            verified INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prod_name TEXT,
            price REAL,
            data TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY,
            amount REAL,
            used_by TEXT DEFAULT ''
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prod_id TEXT,
            item_data TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banned (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Database Helper Functions
def get_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance, lang, state, withdraw_amount, verified, last_bonus FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'balance': row[0], 
            'lang': row[1], 
            'state': row[2], 
            'withdraw_amount': row[3], 
            'verified': bool(row[4]),
            'last_bonus': row[5]
        }
    return None

def save_user(user_id, data):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, balance, lang, state, withdraw_amount, verified, last_bonus)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, 
        data['balance'], 
        data.get('lang'), 
        data.get('state'), 
        data.get('withdraw_amount', 0.0), 
        int(data.get('verified', False)),
        data.get('last_bonus', 0)
    ))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM banned WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

# --- PREMIUM EMOJI HELPERS ---
def e(eid, fallback):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'

E_STAR = e("6267118537752450044", "✨")
E_FIRE = e("5429349728892522445", "🔥")
E_DIAM = e("5427328491513224187", "💎")
E_CART = e("5260632384029621402", "🛒")
E_BAG  = e("5258301973429519965", "🛍")
E_ROCK = e("6267008582294705964", "🚀")
E_CASH = e("6264537399846507987", "💸")
E_TICK = e("6147565374289220368", "✅")
E_CROS = e("5208748315805499400", "❌")
E_WALL = e("6267172559851099903", "💳")
E_USER = e("6266864696595323855", "👤")
E_GLOB = e("5262817744994208381", "🌐")
E_CHAT = e("5875465628285931233", "💬")
E_GIFT = e("5224607267797606837", "🎁")
E_CROW = e("5229064374403998351", "👑")
E_BELL = e("6266969287638913443", "🔔")
E_PIN  = e("5433818199982378380", "📌")

# Product Stock Information Dictionary
stock_meta = {
    'netflix': {'name': '🎬 Netflix Premium UHD', 'price': 100},
    'tg3m': {'name': '💎 Telegram Premium (3M)', 'price': 300},
    'tg1y': {'name': '👑 Telegram Premium (1Y)', 'price': 600},
    'amazon': {'name': '📦 Amazon Prime Video', 'price': 0, 'contact_admin': True},
    'adobe': {'name': '⚡ Adobe Creative Cloud 12M', 'price': 25},
    'yt': {'name': '📺 YouTube Family Premium', 'price': 180}
}

def get_stock_count(prod_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM stock WHERE prod_id = ?', (prod_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

LANG = {
    'en': {'wel': "Welcome to our Premium Store!", 'bal': "Balance", 'prod': "Available Products", 'hist': "Order History", 'no_hist': "No purchases yet."},
    'fr': {'wel': "Bienvenue dans notre boutique premium!", 'bal': "Solde", 'prod': "Produits disponibles", 'hist': "Historique des commandes", 'no_hist': "Aucun achat pour le moment."},
    'es': {'wel': "¡Bienvenido a nuestra tienda premium!", 'bal': "Saldo", 'prod': "Productos disponibles", 'hist': "Historial de pedidos", 'no_hist': "Aún no hay compras."},
    'ru': {'wel': "Добро пожаловать в наш магазин!", 'bal': "Баланс", 'prod': "Доступные товары", 'hist': "История заказов", 'no_hist': "Покупок пока нет."}
}

# --- KEYBOARDS ---
def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton("🇫🇷 French", callback_data="lang_fr")],
        [InlineKeyboardButton("🇪🇸 Spanish", callback_data="lang_es"), InlineKeyboardButton("🇷🇺 Russian", callback_data="lang_ru")]
    ])

def subscription_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel 1", url=CHANNEL_1_URL)],
        [InlineKeyboardButton("📢 Join Channel 2", url=CHANNEL_2_URL)],
        [InlineKeyboardButton("✅ I Have Joined", callback_data="check_sub")]
    ])

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🚀 Start Hub"],
        ["🛍️ Products", "💳 Top-up Wallet"],
        ["🎁 Redeem Coupon", "🎁 Daily Bonus"],
        ["💸 Withdraw Balance", "👤 My Profile"],
        ["📜 Orders History", "💬 Live Support"],
        ["🌐 Change Language"]
    ], resize_keyboard=True)
  # --- START HANDLER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        return

    user_data = get_user(user_id)
    if not user_data:
        user_data = {'balance': 0.0, 'lang': None, 'state': None, 'withdraw_amount': 0.0, 'verified': False, 'last_bonus': 0}
        save_user(user_id, user_data)

    clear_space = "\n" * 15

    # Force Language Selection first if not selected
    if user_data['lang'] is None:
        await update.message.reply_text(f"{clear_space}{E_GLOB} <b>Select your preferred language:</b>", reply_markup=lang_keyboard(), parse_mode="HTML")
        return

    # Force Join after Language is selected
    if not user_data['verified']:
        await update.message.reply_text(f"{clear_space}{E_BELL} <b>Please join our official channels to continue:</b>", reply_markup=subscription_keyboard(), parse_mode="HTML")
        return

    user_lang = user_data['lang']
    msg = f"{clear_space}<b>{LANG[user_lang]['wel']}</b> {E_ROCK}\n\nTop up your wallet {E_WALL} and grab your digital products instantly {E_FIRE}."
    await update.message.reply_text(msg, reply_markup=main_keyboard(), parse_mode="HTML")

# ==========================================
# 👑 ADMIN PANEL COMMANDS
# ==========================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM banned')
    total_banned = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM orders')
    total_orders = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM coupons')
    total_coupons = cursor.fetchone()[0]
    conn.close()
    
    msg = f"""
{E_CROW} <b>ADMIN CONTROL PANEL</b> {E_STAR}
───────────────────────────
{E_USER} <b>Total Users:</b> <code>{total_users}</code>
{E_CROS} <b>Banned Users:</b> <code>{total_banned}</code>
{E_GIFT} <b>Total Orders:</b> <code>{total_orders}</code>
🎫 <b>Active Coupons:</b> <code>{total_coupons}</code>

{E_PIN} <b>Available Admin Commands:</b>
• <code>/createcoupon [count] [amount]</code> - Generate coupons
• <code>/singleuser [uid] [msg]</code> - Send message to single user
• <code>/alluser [text/media]</code> - Broadcast text, photo or video to all users
• <code>/addstockfile [prod_id]</code> - Reply to text file to upload stock
• <code>/stockinfo</code> - Check current stock counts
• <code>/addbal [uid] [amt]</code> / <code>/deductbal [uid] [amt]</code> - Balance control
• <code>/block [uid] /unblock [uid]</code> - Ban/Unban user
"""
    await update.message.reply_text(msg, parse_mode="HTML")

async def add_stock_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text(f"{E_CROS} Please reply to a text file with <code>/addstockfile product_id</code>", parse_mode="HTML")
        return
    
    try:
        args = context.args
        if not args:
            await update.message.reply_text(f"{E_CROS} Please specify product ID! Example: <code>/addstockfile netflix</code>", parse_mode="HTML")
            return
        
        prod_id = args[0].lower()
        if prod_id not in stock_meta or stock_meta[prod_id].get('contact_admin'):
            await update.message.reply_text(f"{E_CROS} Invalid product ID or product is in Contact Admin mode.", parse_mode="HTML")
            return

        doc = update.message.reply_to_message.document
        file = await context.bot.get_file(doc.file_id)
        file_bytes = await file.download_as_bytearray()
        file_content = file_bytes.decode('utf-8', errors='ignore')
        
        lines = [line.strip() for line in file_content.splitlines() if line.strip()]
        if not lines:
            await update.message.reply_text(f"{E_CROS} The uploaded file is empty!", parse_mode="HTML")
            return

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        for line in lines:
            cursor.execute('INSERT INTO stock (prod_id, item_data) VALUES (?, ?)', (prod_id, line))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"{E_TICK} <b>Successfully added {len(lines)} item(s) to {stock_meta[prod_id]['name']}!</b> {E_FIRE}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"{E_CROS} Error processing file: {e}", parse_mode="HTML")

async def single_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(f"{E_CROS} <b>Usage:</b> <code>/singleuser [user_id] [message text]</code>", parse_mode="HTML")
            return
            
        target_uid = int(args[0])
        msg_text = " ".join(args[1:])

        formatted_msg = f"{E_BELL} <b>Message from Admin:</b>\n\n{msg_text}"
        await context.bot.send_message(chat_id=target_uid, text=formatted_msg, parse_mode="HTML")
        await update.message.reply_text(f"{E_TICK} Message successfully sent to user <code>{target_uid}</code>.", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text(f"{E_CROS} Invalid User ID format! Please provide a numeric user ID.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"{E_CROS} Failed to send message: {e}", parse_mode="HTML")

async def create_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = context.args
        count = int(args[0]) if len(args) > 0 else 1
        amount = float(args[1]) if len(args) > 1 else 50.0

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        generated = []
        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            cursor.execute('INSERT OR IGNORE INTO coupons (code, amount, used_by) VALUES (?, ?, ?)', (code, amount, ""))
            generated.append(code)
        conn.commit()
        conn.close()

        msg = f"{E_TICK} <b>Successfully Created {count} Coupon(s)!</b> {E_GIFT}\n" \
              f"{E_CASH} <b>Value per coupon:</b> ₹{amount}\n\n"
        for idx, c in enumerate(generated, 1):
            msg += f"{idx}. <code>{c}</code>\n"

        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(f"{E_CROS} <b>Usage:</b> <code>/createcoupon [count] [amount]</code>", parse_mode="HTML")

async def list_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code, amount, used_by FROM coupons')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No active coupons available right now.", parse_mode="HTML")
        return
    
    msg = f"🎫 <b>Active Coupons List:</b>\n\n"
    for code, amt, used_by in rows:
        used_count = len([u for u in used_by.split(',') if u])
        msg += f"• Code: <code>{code}</code> | ₹{amt} | Used: {used_count} user(s)\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def product_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = f"{E_BAG} <b>All Product IDs & Names:</b>\n\n"
    for k, v in stock_meta.items():
        msg += f"• ID: <code>{k}</code> ➔ Name: <b>{v['name']}</b>\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        if get_user(target_id):
            clear_space = "\n" * 25
            await context.bot.send_message(chat_id=target_id, text=f"{clear_space}{E_TICK} <b>Admin has refreshed your chat screen!</b> {E_ROCK}", parse_mode="HTML")
            await update.message.reply_text(f"{E_TICK} Chat screen cleared for user <code>{target_id}</code>.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"{E_CROS} User ID not found in database.", parse_mode="HTML")
    except Exception:
        await update.message.reply_text(f"{E_CROS} <b>Usage:</b> /clear user_id", parse_mode="HTML")

async def alluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    all_uids = [row[0] for row in cursor.fetchall()]
    conn.close()

    sent, failed = 0, 0
    reply_msg = update.message.reply_to_message

    for uid in all_uids:
        try:
            if reply_msg:
                if reply_msg.photo:
                    await context.bot.send_photo(chat_id=uid, photo=reply_msg.photo[-1].file_id, caption=(reply_msg.caption or ""))
                elif reply_msg.video:
                    await context.bot.send_video(chat_id=uid, video=reply_msg.video.file_id, caption=(reply_msg.caption or ""))
                elif reply_msg.text:
                    await context.bot.send_message(chat_id=uid, text=f"{E_BELL} <b>Admin Announcement</b> {E_STAR}\n\n{reply_msg.text}", parse_mode="HTML")
            else:
                try:
                    broadcast_text = update.message.text.split(' ', 1)[1]
                except IndexError:
                    await update.message.reply_text(f"{E_CROS} <b>Usage:</b> Reply to a message/photo/video with <code>/alluser</code> or use <code>/alluser [text]</code>", parse_mode="HTML")
                    return
                await context.bot.send_message(chat_id=uid, text=f"{E_BELL} <b>Admin Announcement</b> {E_STAR}\n\n{broadcast_text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"{E_TICK} <b>Broadcast Complete!</b>\nSent: {sent} | Failed: {failed}", parse_mode="HTML")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO banned (user_id) VALUES (?)', (target_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"{E_TICK} User <code>{target_id}</code> has been banned!", parse_mode="HTML")
    except Exception:
        await update.message.reply_text(f"{E_CROS} <b>Usage:</b> /block user_id", parse_mode="HTML")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM banned WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"{E_TICK} User <code>{target_id}</code> has been unbanned!", parse_mode="HTML")
    except Exception:
        await update.message.reply_text(f"{E_CROS} <b>Usage:</b> /unblock user_id", parse_mode="HTML")

async def add_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
        u_data = get_user(uid)
        if u_data:
            u_data['balance'] += amt
            save_user(uid, u_data)
            await update.message.reply_text(f"{E_TICK} ₹{amt} added to User <code>{uid}</code>.", parse_mode="HTML")
            await context.bot.send_message(uid, f"{E_GIFT} <b>Admin added ₹{amt} to your wallet!</b> {E_FIRE}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"{E_CROS} User ID not found.", parse_mode="HTML")
    except Exception:
        await update.message.reply_text(f"{E_CROS} <b>Usage:</b> /addbal user_id amount", parse_mode="HTML")

async def deduct_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
        u_data = get_user(uid)
        if u_data:
            u_data['balance'] = max(0.0, u_data['balance'] - amt)
            save_user(uid, u_data)
            await update.message.reply_text(f"{E_TICK} ₹{amt} deducted from User <code>{uid}</code>.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"{E_CROS} User not found.", parse_mode="HTML")
    except Exception:
        await update.message.reply_text(f"{E_CROS} <b>Usage:</b> /deductbal user_id amount", parse_mode="HTML")

async def stock_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = f"{E_BAG} <b>Current Stock Status:</b>\n\n"
    for k, v in stock_meta.items():
        if not v.get('contact_admin'):
            count = get_stock_count(k)
            msg += f"• <b>{v['name']}</b>: <b>{count}</b> available\n"
        else:
            msg += f"• <b>{v['name']}</b>: <i>Contact Admin Mode</i>\n"
    await update.message.reply_text(msg, parse_mode="HTML")
      # --- MENU HANDLER ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if is_banned(user_id):
        return
        
    user_data = get_user(user_id)
    if not user_data:
        user_data = {'balance': 0.0, 'lang': 'en', 'state': None, 'withdraw_amount': 0.0, 'verified': False, 'last_bonus': 0}
        save_user(user_id, user_data)

    if user_data['lang'] is None:
        await update.message.reply_text("Please type /start to select language.")
        return

    if not user_data['verified']:
        await update.message.reply_text(f"{E_BELL} <b>Please join our official channels first:</b>", reply_markup=subscription_keyboard(), parse_mode="HTML")
        return

    # Handle Coupon State
    if user_data.get('state') == 'waiting_for_coupon':
        user_data['state'] = None
        save_user(user_id, user_data)
        code = text.strip().upper()
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT amount, used_by FROM coupons WHERE code = ?', (code,))
        coupon_row = cursor.fetchone()
        
        if coupon_row:
            amt, used_by = coupon_row[0], coupon_row[1]
            used_list = [u for u in used_by.split(',') if u]
            if str(user_id) in used_list:
                conn.close()
                await update.message.reply_text(f"{E_CROS} <b>You have already used this coupon code!</b>", parse_mode="HTML", reply_markup=main_keyboard())
            else:
                used_list.append(str(user_id))
                new_used_by = ",".join(used_list)
                cursor.execute('UPDATE coupons SET used_by = ? WHERE code = ?', (new_used_by, code))
                conn.commit()
                conn.close()

                user_data['balance'] += amt
                save_user(user_id, user_data)
                await update.message.reply_text(f"{E_TICK} <b>Coupon Successfully Redeemed!</b> {E_FIRE}\n{E_CASH} <b>₹{amt}</b> added to wallet.\n{E_WALL} New Balance: ₹{user_data['balance']}", parse_mode="HTML", reply_markup=main_keyboard())
        else:
            conn.close()
            await update.message.reply_text(f"{E_CROS} <b>Invalid or Expired Coupon Code!</b>", parse_mode="HTML", reply_markup=main_keyboard())
        return

    # Handle Withdrawal Amount State
    if user_data.get('state') == 'waiting_for_withdraw_amount':
        try:
            amount = float(text.strip())
            bal = user_data['balance']
            if amount <= 0:
                await update.message.reply_text(f"{E_CROS} Please enter a valid amount greater than 0.", parse_mode="HTML", reply_markup=main_keyboard())
                user_data['state'] = None
                save_user(user_id, user_data)
                return
            if amount > bal:
                await update.message.reply_text(f"{E_CROS} <b>Insufficient Balance!</b> Current balance is ₹{bal:.2f}", parse_mode="HTML", reply_markup=main_keyboard())
                user_data['state'] = None
                save_user(user_id, user_data)
                return
            
            user_data['withdraw_amount'] = amount
            user_data['state'] = 'waiting_for_withdraw_details'
            save_user(user_id, user_data)
            await update.message.reply_text(f"💳 <b>Enter your UPI ID or Bank Details (Account Number & IFSC) for payout:</b>\n\n<i>(Type /start to cancel)</i>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text(f"{E_CROS} Please enter a valid numerical amount.", parse_mode="HTML", reply_markup=main_keyboard())
            user_data['state'] = None
            save_user(user_id, user_data)
        return

    # Handle Withdrawal Details State
    if user_data.get('state') == 'waiting_for_withdraw_details':
        details = text.strip()
        amount = user_data['withdraw_amount']
        
        user_data['balance'] -= amount
        user_data['state'] = None
        user_data['withdraw_amount'] = 0.0
        save_user(user_id, user_data)

        await update.message.reply_text(f"{E_TICK} <b>Withdrawal Request Submitted!</b>\n{E_CASH} Amount: ₹{amount}\n💳 Details: <code>{details}</code>\n\n<i>Admin will process your payment soon.</i>", parse_mode="HTML", reply_markup=main_keyboard())

        admin_msg = f"💸 <b>NEW WITHDRAWAL REQUEST</b> {E_STAR}\n\n" \
                    f"{E_USER} <b>User ID:</b> <code>{user_id}</code>\n" \
                    f"{E_CASH} <b>Amount:</b> ₹{amount}\n" \
                    f"💳 <b>Details:</b> <code>{details}</code>"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="HTML")
        except Exception:
            pass
        return

    user_lang = user_data['lang']

    if "Products" in text:
        keyboard = []
        for k, v in stock_meta.items():
            if v.get('contact_admin'):
                btn_text = f"{v['name']} (Contact Admin)"
            else:
                count = get_stock_count(k)
                btn_text = f"{v['name']} - ₹{v['price']} (📦 {count})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_{k}")])
            
        await update.message.reply_text(f"{E_BAG} <b>{LANG[user_lang]['prod']}:</b>\nSelect an item below {E_CART}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    elif "Top-up" in text:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Chat with Admin to Top-up", url=f"https://t.me/{SUPPORT_USER.replace('@', '')}")]])
        msg = f"{E_WALL} <b>Wallet Top-Up</b>\n───────────────────\n{E_ROCK} <b>To add balance, please contact our admin:</b>\n\n{E_CHAT} <b>Admin:</b> {SUPPORT_USER}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>"
        await update.message.reply_text(msg, reply_markup=kb, parse_mode="HTML")

    elif "Redeem Coupon" in text:
        user_data['state'] = 'waiting_for_coupon'
        save_user(user_id, user_data)
        await update.message.reply_text(f"🎁 <b>Send your coupon code below in the chat:</b>\n\n<i>(Type /start to cancel)</i>\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")

    elif "Daily Bonus" in text:
        current_time = int(time.time())
        last_claimed = user_data.get('last_bonus', 0)
        cooldown = 86400  # Exactly 24 hours

        if current_time - last_claimed < cooldown:
            remaining_seconds = cooldown - (current_time - last_claimed)
            remaining_hours = int(remaining_seconds / 3600)
            remaining_minutes = int((remaining_seconds % 3600) / 60)
            await update.message.reply_text(f"{E_CROS} <b>You have already claimed your Daily Bonus!</b>\nCome back after {remaining_hours}h {remaining_minutes}m to claim again.\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")
        else:
            user_data['balance'] += 3.0  # Exactly ₹3.00
            user_data['last_bonus'] = current_time
            save_user(user_id, user_data)
            await update.message.reply_text(f"{E_TICK} <b>Daily Bonus Claimed Successfully!</b> {E_FIRE}\n{E_CASH} <b>₹3.00</b> added to your wallet.\n{E_WALL} New Balance: ₹{user_data['balance']:.2f}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML", reply_markup=main_keyboard())

    elif "Withdraw Balance" in text:
        bal = user_data['balance']
        if bal <= 0:
            await update.message.reply_text(f"{E_CROS} You don't have sufficient balance to withdraw. Current Balance: ₹0.00\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")
            return
        user_data['state'] = 'waiting_for_withdraw_amount'
        save_user(user_id, user_data)
        await update.message.reply_text(f"💸 <b>Real Payout Withdrawal</b>\n\n{E_WALL} Your Balance: ₹{bal:.2f}\n\n<b>Please enter the amount you want to withdraw:</b>\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")

    elif "Profile" in text:
        bal = user_data['balance']
        msg = f"{E_USER} <b>My Profile</b>\n\n{E_PIN} <b>ID:</b> <code>{user_id}</code>\n{E_CASH} <b>{LANG[user_lang]['bal']}:</b> ₹{bal:.2f} {E_DIAM}"
        await update.message.reply_text(msg, parse_mode="HTML")

    elif "Orders" in text:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT prod_name, price, data FROM orders WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text(f"{E_CROS} {LANG[user_lang]['no_hist']}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")
        else:
            msg = f"{E_GIFT} <b>{LANG[user_lang]['hist']}</b> {E_STAR}\n\n"
            for i, (p_name, p_price, p_data) in enumerate(rows, 1):
                msg += f"<b>{i}. {p_name}</b> - ₹{p_price:.2f}\n{E_PIN} Data: <code>{p_data}</code>\n\n"
            msg += f"👤 <b>Your ID:</b> <code>{user_id}</code>"
            await update.message.reply_text(msg, parse_mode="HTML")

    elif "Support" in text:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Open Admin Profile", url=f"https://t.me/{SUPPORT_USER.replace('@', '')}")]])
        await update.message.reply_text(f"{E_CHAT} <b>Need help?</b> {E_FIRE}\nContact support admin directly by clicking below {E_CROW}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", reply_markup=kb, parse_mode="HTML")

    elif "Language" in text:
        await update.message.reply_text(f"{E_GLOB} <b>Select Language:</b>\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", reply_markup=lang_keyboard(), parse_mode="HTML")

# --- INLINE BUTTONS & CHANNEL CHECK ---
async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    user_data = get_user(user_id)
    if not user_data:
        user_data = {'balance': 0.0, 'lang': 'en', 'state': None, 'withdraw_amount': 0.0, 'verified': False, 'last_bonus': 0}
        save_user(user_id, user_data)

    if data.startswith("lang_"):
        sel = data.split("_")[1]
        user_data['lang'] = sel
        user_data['verified'] = False  # Reset verification so force join appears after changing language
        save_user(user_id, user_data)
        await query.message.delete()
        await context.bot.send_message(user_id, f"{E_BELL} <b>Please join our official channels to continue:</b>", reply_markup=subscription_keyboard(), parse_mode="HTML")

    elif data == "check_sub":
        user_data['verified'] = True
        save_user(user_id, user_data)
        await query.message.delete()
        user_lang = user_data['lang']
        msg = f"<b>{LANG[user_lang]['wel']}</b> {E_ROCK}\n\nTop up your wallet {E_WALL} and grab your digital products instantly {E_FIRE}."
        await context.bot.send_message(user_id, msg, reply_markup=main_keyboard(), parse_mode="HTML")

    elif data.startswith("view_"):
        k = data.split("_")[1]
        prod = stock_meta[k]
        if prod.get('contact_admin'):
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Order via Admin Profile", url=f"https://t.me/{SUPPORT_USER.replace('@', '')}")]])
            cap = f"{E_CROW} <b>{prod['name']}</b> {E_STAR}\n\n{E_CHAT} To order this product, click below to message the admin: {SUPPORT_USER}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>"
            await query.message.reply_text(cap, reply_markup=kb, parse_mode="HTML")
            return
        
        count = get_stock_count(k)
        cap = f"{E_GIFT} <b>{prod['name']}</b>\n{E_CASH} <b>Price:</b> ₹{prod['price']}\n{E_BAG} <b>Stock:</b> {count} pcs\n\n{E_PIN} Select quantity to purchase: {E_FIRE}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>"
        kb = [[InlineKeyboardButton("🛒 Buy 1 Item", callback_data=f"buy_{k}_1")]]
        await query.message.reply_text(cap, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_"):
        _, k, qty = data.split("_")
        prod = stock_meta[k]
        cost = prod['price'] * int(qty)
        bal = user_data['balance']
        count = get_stock_count(k)

        if count < int(qty):
            await query.message.reply_text(f"{E_CROS} <b>Product out of stock!</b> {E_BELL}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")
        elif bal < cost:
            await query.message.reply_text(f"{E_CROS} <b>Insufficient Balance!</b> {E_WALL}\nRequired: ₹{cost:.2f} | Balance: ₹{bal:.2f} {E_DIAM}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")
        else:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id, item_data FROM stock WHERE prod_id = ? LIMIT 1', (k,))
            item_row = cursor.fetchone()
            
            if not item_row:
                conn.close()
                await query.message.reply_text(f"{E_CROS} <b>Product out of stock!</b> {E_BELL}\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")
                return
            
            item_id, delivered = item_row[0], item_row[1]
            cursor.execute('DELETE FROM stock WHERE id = ?', (item_id,))
            cursor.execute('INSERT INTO orders (user_id, prod_name, price, data) VALUES (?, ?, ?, ?)', (user_id, prod['name'], cost, delivered))
            conn.commit()
            conn.close()

            user_data['balance'] -= cost
            save_user(user_id, user_data)
            await query.message.reply_text(f"{E_TICK} <b>Purchase Successful!</b> {E_FIRE}\n\n{E_GIFT} <b>Item:</b> {prod['name']}\n{E_PIN} <b>Data:</b> <code>{delivered}</code>\n\n{E_ROCK} Thanks for shopping!\n\n👤 <b>Your ID:</b> <code>{user_id}</code>", parse_mode="HTML")

# --- MAIN RUNNER ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("singleuser", single_user_message))
    app.add_handler(CommandHandler("createcoupon", create_coupon))
    app.add_handler(CommandHandler("coupons", list_coupons))
    app.add_handler(CommandHandler("id", product_ids))
    app.add_handler(CommandHandler("clear", clear_chat))
    app.add_handler(CommandHandler("alluser", alluser))
    app.add_handler(CommandHandler("addstockfile", add_stock_file))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("addbal", add_bal))
    app.add_handler(CommandHandler("deductbal", deduct_bal))
    app.add_handler(CommandHandler("stockinfo", stock_info))
    
    app.add_handler(CallbackQueryHandler(handle_inline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    print("🚀 Bot is running successfully with /singleuser command...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
                                                             
