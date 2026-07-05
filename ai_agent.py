"""
🤖 AI АГЕНТ ДЛЯ TELEGRAM
Память | AI-ответы | Заметки | 24/7
"""

import os
import sqlite3
import asyncio
import aiohttp
from datetime import datetime
from typing import List, Dict

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "ТВОЙ_ТОКЕН_ОТ_BOTFATHER")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

DEFAULT_PROVIDER = "groq"
GROQ_MODEL = "llama-3.1-8b-instant"
GEMINI_MODEL = "gemini-1.5-flash"

DB_PATH = "agent_memory.db"

# ═══════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            content TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            text_provider TEXT DEFAULT 'groq',
            personality TEXT DEFAULT 'friendly',
            memory_enabled INTEGER DEFAULT 1
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_PATH)

# ═══════════════════════════════════════════════════════════════
# ПАМЯТЬ
# ═══════════════════════════════════════════════════════════════

def save_message(user_id: int, role: str, content: str):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()
    conn.close()

def get_memory(user_id: int, limit: int = 10) -> List[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT role, content, timestamp FROM messages 
           WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?""",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1], "time": r[2]} for r in reversed(rows)]

def clear_memory(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════

def get_user_settings(user_id: int) -> Dict:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        c.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        conn.commit()
        row = (user_id, 'groq', 'friendly', 1)
    
    conn.close()
    return {
        "user_id": row[0],
        "text_provider": row[1],
        "personality": row[2],
        "memory_enabled": bool(row[3])
    }

def update_settings(user_id: int, **kwargs):
    conn = get_db()
    c = conn.cursor()
    for key, value in kwargs.items():
        c.execute(f"UPDATE user_settings SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════════
# ЗАМЕТКИ
# ═══════════════════════════════════════════════════════════════

def save_note(user_id: int, title: str, content: str):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (user_id, title, content) VALUES (?, ?, ?)",
        (user_id, title, content)
    )
    conn.commit()
    conn.close()

def get_notes(user_id: int) -> List[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, title, content, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "content": r[2], "created": r[3]} for r in rows]

# ═══════════════════════════════════════════════════════════════
# AI ПРОВАЙДЕРЫ
# ═══════════════════════════════════════════════════════════════

async def ask_groq(messages: List[Dict], temperature: float = 0.7) -> str:
    if not GROQ_API_KEY:
        return "❌ GROQ_API_KEY не настроен"
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2048
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                return f"❌ Ошибка Groq: {await resp.text()}"
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

async def ask_gemini(messages: List[Dict], temperature: float = 0.7) -> str:
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY не настроен"
    
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                return f"❌ Ошибка Gemini: {await resp.text()}"
            data = await resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return "❌ Не удалось получить ответ от Gemini"

async def ask_ai(user_id: int, prompt: str, system_prompt: str = None) -> str:
    settings = get_user_settings(user_id)
    provider = settings["text_provider"]
    
    messages = []
    
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else:
        personalities = {
            "friendly": "Ты дружелюбный и полезный ассистент. Отвечай на русском языке.",
            "expert": "Ты эксперт во всех областях. Давай точные, детальные ответы на русском.",
            "creative": "Ты креативный помощник. Используй воображение и нестандартные подходы.",
            "concise": "Ты лаконичный ассистент. Давай короткие, по существу ответы."
        }
        personality = personalities.get(settings["personality"], personalities["friendly"])
        messages.append({"role": "system", "content": personality})
    
    if settings["memory_enabled"]:
        memory = get_memory(user_id, limit=8)
        for msg in memory:
            messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": prompt})
    
    try:
        if provider == "groq":
            response = await ask_groq(messages)
            if response.startswith("❌"):
                response = await ask_gemini(messages)
        else:
            response = await ask_gemini(messages)
            if response.startswith("❌"):
                response = await ask_groq(messages)
    except Exception as e:
        response = f"❌ Ошибка: {str(e)}"
    
    save_message(user_id, "user", prompt)
    save_message(user_id, "assistant", response)
    
    return response

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ TELEGRAM
# ═══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    welcome = """
🤖 **Привет! Я твой AI-агент**

Вот что я умею:

💬 **Разговоры** — с памятью и контекстом
📝 **Заметки** — `/note` и `/notes`
⚙️ **Настройки** — `/settings`
🧹 **Очистить память** — `/clear`

Просто напиши мне что угодно!
"""
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 **Команды:**

`/start` — Начать работу
`/note <текст>` — Сохранить заметку
`/notes` — Список заметок
`/clear` — Очистить память
`/settings` — Настройки
`/provider <groq|gemini>` — Сменить AI-провайдер
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = " ".join(context.args)
    
    if not text:
        await update.message.reply_text("❌ Укажи текст: `/note Купить молоко`")
        return
    
    words = text.split()
    title = " ".join(words[:3]) if len(words) > 3 else text
    save_note(user_id, title, text)
    await update.message.reply_text(f"📝 Сохранено: *{title}*", parse_mode="Markdown")

async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notes = get_notes(user_id)
    
    if not notes:
        await update.message.reply_text("📝 Нет заметок. Используй `/note текст`")
        return
    
    text = "📝 **Твои заметки:**\n\n"
    for note in notes:
        text += f"• **{note['title']}**\n  {note['content'][:100]}{'...' if len(note['content']) > 100 else ''}\n\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_memory(user_id)
    await update.message.reply_text("🧹 Память очищена!")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🤖 Провайдер: " + settings["text_provider"].upper(), callback_data="switch_provider")],
        [InlineKeyboardButton("🎭 Персонаж: " + settings["personality"], callback_data="personality")],
        [InlineKeyboardButton("🧠 Память: " + ("Вкл" if settings["memory_enabled"] else "Выкл"), callback_data="toggle_memory")],
    ]
    
    await update.message.reply_text(
        "⚙️ **Настройки:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def provider_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    provider = context.args[0].lower() if context.args else None
    
    if provider not in ["groq", "gemini"]:
        await update.message.reply_text("❌ Доступны: `groq`, `gemini`")
        return
    
    update_settings(user_id, text_provider=provider)
    await update.message.reply_text(f"✅ Провайдер: **{provider.upper()}**", parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    if query.data == "switch_provider":
        settings = get_user_settings(user_id)
        new_provider = "gemini" if settings["text_provider"] == "groq" else "groq"
        update_settings(user_id, text_provider=new_provider)
        await query.edit_message_text(f"✅ Провайдер: **{new_provider.upper()}**", parse_mode="Markdown")
    
    elif query.data == "toggle_memory":
        settings = get_user_settings(user_id)
        new_state = 0 if settings["memory_enabled"] else 1
        update_settings(user_id, memory_enabled=new_state)
        status = "Вкл" if new_state else "Выкл"
        await query.edit_message_text(f"🧠 Память: **{status}**", parse_mode="Markdown")
    
    elif query.data == "personality":
        personalities = ["friendly", "expert", "creative", "concise"]
        settings = get_user_settings(user_id)
        current = settings["personality"]
        idx = personalities.index(current)
        new_personality = personalities[(idx + 1) % len(personalities)]
        update_settings(user_id, personality=new_personality)
        await query.edit_message_text(f"🎭 Персонаж: **{new_personality}**", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text.startswith('/'):
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = await ask_ai(user_id, text)
    await update.message.reply_text(response, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════════

def main():
    init_db()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("note", note_cmd))
    application.add_handler(CommandHandler("notes", notes_cmd))
    application.add_handler(CommandHandler("clear", clear_cmd))
    application.add_handler(CommandHandler("settings", settings_cmd))
    application.add_handler(CommandHandler("provider", provider_cmd))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 AI-агент запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()