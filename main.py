import asyncio
import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp
import sqlite3

# --- SOZLAMALAR ---
# Tokenni o'z bot tokeningizga almashtiring
BOT_TOKEN = "9186846172:AAFJNsgYF1Cfa8wyFLvKbW0tyMis1kjasjM"
# Admin Telegram ID raqamingizni yozing
ADMIN_ID = 8845897591  # O'z ID raqamingiz bilan almashtiring

# Majburiy obuna kanallari (foydalanuvchi obuna bo'lishi shart bo'lgan kanallar)
REQUIRED_CHANNELS = ["@Mobile_Legends_Uzb_09", "@nodirbek_safarboyevch"]

# Til so'zlari (O'zbek, Rus, Ingliz)
TEXTS = {
    "uz": {
        "welcome": "Salom! Men Instagram, YouTube, TikTok va Pinterest'dan video/musiqa yuklab beruvchi botman 📥\n\nMarhamat, havola (link) yuboring:",
        "choose_lang": "Tilni tanlang / Выберите язык / Choose language:",
        "lang_changed": "Til o'zbek tiliga o'zgartirildi ✅",
        "sub_check": "Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:",
        "sub_button": "Obuna bo'lish ➕",
        "check_sub": "Tekshirish ✅",
        "not_subscribed": "Siz hali barcha kanallarga obuna bo'lmadingiz! Iltimos, obuna bo'lib qaytadan urinib ko'ring.",
        "downloading": "⏳ Yuklab olinmoqda, iltimos kuting...",
        "error": "❌ Xatolik yuz berdi. Havolani tekshirib qaytadan yuboring.",
        "admin_stats": "📊 Bot Statistikasi:\n\n👥 Foydalanuvchilar soni: {users}",
        "broadcast_start": "📢 Reklama uchun matn yoki rasm/video yuboring:",
        "broadcast_done": "✅ Reklama yuborildi: {success} ta, xato: {fail} ta."
    },
    "ru": {
        "welcome": "Привет! Я бот для скачивания видео и музыки из Instagram, YouTube, TikTok и Pinterest 📥\n\nОтправьте мне ссылку:",
        "choose_lang": "Выберите язык / Tilni tanlang / Choose language:",
        "lang_changed": "Язык изменен на русский ✅",
        "sub_check": "Для использования бота подпишитесь на каналы:",
        "sub_button": "Подписаться ➕",
        "check_sub": "Проверить ✅",
        "not_subscribed": "Вы подписались не на все каналы! Подпишитесь и проверьте снова.",
        "downloading": "⏳ Скачивание, пожалуйста подождите...",
        "error": "❌ Произошла ошибка. Проверьте ссылку и попробуйте снова.",
        "admin_stats": "📊 Статистика бота:\n\n👥 Пользователей: {users}",
        "broadcast_start": "📢 Отправьте текст или медиа для рассылки:",
        "broadcast_done": "✅ Рассылка завершена: успешно: {success}, ошибок: {fail}."
    },
    "en": {
        "welcome": "Hello! I am a bot to download videos and music from Instagram, YouTube, TikTok, and Pinterest 📥\n\nSend me a link:",
        "choose_lang": "Choose language / Tilni tanlang / Выберите язык:",
        "lang_changed": "Language changed to English ✅",
        "sub_check": "To use the bot, please subscribe to these channels:",
        "sub_button": "Subscribe ➕",
        "check_sub": "Check ✅",
        "not_subscribed": "You have not subscribed to all channels! Please subscribe and try again.",
        "downloading": "⏳ Downloading, please wait...",
        "error": "❌ An error occurred. Check the link and try again.",
        "admin_stats": "📊 Bot Stats:\n\n👥 Total Users: {users}",
        "broadcast_start": "📢 Send text or media for broadcast:",
        "broadcast_done": "✅ Broadcast finished: success: {success}, failed: {fail}."
    }
}

# --- BAZA BILAN ISHLASH (SQLite) ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'uz'
        )
    """)
    conn.commit()
    conn.close()
def add_user(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_user_lang(user_id: int) -> str:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "uz"

def set_user_lang(user_id: int, lang: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

# --- HOLATLAR (FSM) ---
class BroadcastState(StatesGroup):
    waiting_for_message = State()

router = Router()

# --- OBUNANI TEKSHIRISH FUNKSIYASI ---
async def check_subscription(bot: Bot, user_id: int) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

def get_sub_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    for channel in REQUIRED_CHANNELS:
        builder.row(InlineKeyboardButton(text=TEXTS[lang]["sub_button"], url=f"https://t.me/{channel.replace('@', '')}"))
    builder.row(InlineKeyboardButton(text=TEXTS[lang]["check_sub"], callback_data="check_sub"))
    return builder.as_markup()

# --- START VA TIL BUYruqlari ---
@router.message(Command("start"))
async def cmd_start(message: Message):
    add_user(message.from_user.id)
    lang = get_user_lang(message.from_user.id)
    
    # Obunani tekshirish
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(TEXTS[lang]["sub_check"], reply_markup=get_sub_keyboard(lang))
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
    )
    await message.answer(TEXTS[lang]["welcome"], reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("lang_"))
async def change_language(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    set_user_lang(callback.from_user.id, lang)
    await callback.message.edit_text(TEXTS[lang]["lang_changed"])
    await callback.answer()

@router.callback_query(F.data == "check_sub")
async def verify_subscription(callback: CallbackQuery):
    lang = get_user_lang(callback.from_user.id)
    if await check_subscription(callback.bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer(TEXTS[lang]["welcome"])
    else:
        await callback.answer(TEXTS[lang]["not_subscribed"], show_alert=True)

# --- ADMIN BUYruqlari ---
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    lang = get_user_lang(message.from_user.id)
    await message.answer(TEXTS[lang]["admin_stats"].format(users=len(users)))

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    lang = get_user_lang(message.from_user.id)
    await message.answer(TEXTS[lang]["broadcast_start"])
    await state.set_state(BroadcastState.waiting_for_message)
@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    success = 0
    fail = 0
    
    for user_id in users:
        try:
            await message.send_copy(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
            
    lang = get_user_lang(message.from_user.id)
    await message.answer(TEXTS[lang]["broadcast_done"].format(success=success, fail=fail))
    await state.clear()

# --- MEDIA YUKLASH (yt-dlp) ---
@router.message(F.text.startswith("http"))
async def download_media(message: Message):
    add_user(message.from_user.id)
    lang = get_user_lang(message.from_user.id)
    
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(TEXTS[lang]["sub_check"], reply_markup=get_sub_keyboard(lang))
        return

    status_msg = await message.answer(TEXTS[lang]["downloading"])
    url = message.text.strip()
    
    output_template = f"downloads/{message.from_user.id}.%(ext)s"
    os.makedirs("downloads", exist_ok=True)
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_template,
        'quiet': True,
        'max_filesize': 50 * 1024 * 1024, # 50MB gacha
    }
    
    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return filename

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, download)
        
        if os.path.exists(file_path):
            input_file = FSInputFile(file_path)
            if file_path.endswith(('.mp3', '.m4a', '.wav')):
                await message.answer_audio(input_file)
            else:
                await message.answer_video(input_file)
            os.remove(file_path)
        else:
            await message.answer(TEXTS[lang]["error"])
            
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await message.answer(TEXTS[lang]["error"])
    finally:
        try:
            await status_msg.delete()
        except:
            pass

# --- BOTNI ISHGA TUSHIRISH ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
