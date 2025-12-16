import os
import logging
import re
import tempfile
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from pydub import AudioSegment
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1
import google.generativeai as genai

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "727974350:AAFM3LfQ18Bur6oDacjRNnnoLYRKkUjEoXM"
GENAI_API_KEY = os.environ.get("GENAI_API_KEY") or "AIzaSyAy5qfTSrOLS5DwcrLWnJJDvX_UJCLFGbU"
ADMIN_ID = int(os.environ.get("ADMIN_ID") or 468374402)

# --- Configure Gemini ---
genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== TRANSLITERATION MODULE =====================

# --- Diakritiklarni normallashtirish ---
latin_normalize = {
    'á':'a','à':'a','ä':'a','â':'a','ã':'a','ā':'a','ă':'a','å':'a',
    'Á':'A','À':'A','Ä':'A','Â':'A','Ã':'A','Ā':'A','Ă':'A','Å':'A',
    'ó':"o'",'ò':"o'",'ö':"o'",'õ':"o'",'ō':"o'",'ô':"o'",'ø':"o'",
    'Ó':"O'",'Ò':"O'",'Ö':"O'",'Õ':"O'",'Ō':"O'",'Ô':"O'",'Ø':"O'",
    'é':'e','è':'e','ë':'e','ê':'e','ē':'e','ĕ':'e','ė':'e',
    'É':'E','È':'E','Ë':'E','Ê':'E','Ē':'E','Ĕ':'E','Ė':'E',
    'í':'i','ì':'i','ï':'i','î':'i','ī':'i',
    'Í':'I','Ì':'I','Ï':'I','Î':'I','Ī':'I',
    'ú':'u','ù':'u','ü':'u','û':'u','ũ':'u','ū':'u','ů':'u',
    'Ú':'U','Ù':'U','Ü':'U','Û':'U','Ũ':'U','Ū':'U','Ů':'U',
    'ğ':"g'",'Ğ':"G'",'ñ':"n'",'Ñ':"N'",
}

def normalize_latin(text):
    return ''.join(latin_normalize.get(ch, ch) for ch in text)

def normalize_apostrophe(text):
    for a in ["'","ʻ","`","´","ˈ","ʿ","'","ʼ"]:
        text = text.replace(a, "'")
    return text

# ===================== LOTIN → KIRIL =====================
def to_cyrillic(text):
    """Lotindan kirilga transliteratsiya"""
    text = normalize_latin(normalize_apostrophe(text))
    
    pairs = [
        ("o'", "ў"), ("O'", "Ў"),
        ("g'", "ғ"), ("G'", "Ғ"),
        ("sh", "ш"), ("Sh", "Ш"), ("SH", "Ш"),
        ("ch", "ч"), ("Ch", "Ч"), ("CH", "Ч"),
        ("ng", "нг"), ("Ng", "Нг"), ("NG", "НГ"),
        ("yo", "ё"), ("Yo", "Ё"), ("YO", "Ё"),
        ("yu", "ю"), ("Yu", "Ю"), ("YU", "Ю"),
        ("ya", "я"), ("Ya", "Я"), ("YA", "Я"),
        ("ye", "е"), ("Ye", "Е"), ("YE", "Е"),
    ]
    
    for lat, cyr in pairs:
        text = text.replace(lat, cyr)
    
    # So'z boshida E → Э
    text = re.sub(r"\bE", "Э", text)
    text = re.sub(r"\be", "э", text)
    
    mapping = {
        'a':'а','b':'б','d':'д','e':'е','f':'ф','g':'г','h':'ҳ','i':'и','j':'ж',
        'k':'к','l':'л','m':'м','n':'н','o':'о','p':'п','q':'қ','r':'р',
        's':'с','t':'т','u':'у','v':'в','x':'х','y':'й','z':'з',
        'A':'А','B':'Б','D':'Д','E':'Е','F':'Ф','G':'Г','H':'Ҳ','I':'И','J':'Ж',
        'K':'К','L':'Л','M':'М','N':'Н','O':'О','P':'П','Q':'Қ','R':'Р',
        'S':'С','T':'Т','U':'У','V':'В','X':'Х','Y':'Й','Z':'З',
        "'":"ъ"
    }
    
    return ''.join(mapping.get(ch, ch) for ch in text)

# ===================== KIRIL → LOTIN (TUZATILGAN) =====================
def to_latin(text):
    """Kirildan lotinga transliteratsiya - barcha xatolar tuzatildi"""
    
    def fix_E(text):
        # 1. "Э" harfi har doim "E" bo'ladi (zamonaviy o'zbek lotin alifbosi)
        text = text.replace("Э", "E").replace("э", "e")

        # 2. So'z boshidagi "Е" -> "Ye" (Masalan: Еr -> Yer, Еtti -> Yetti)
        text = re.sub(r"\bЕ", "Ye", text)
        text = re.sub(r"\bе", "ye", text)

        # 3. Unlidan keyin kelgan "Е" -> "Ye" (Masalan: Muayyan, ssenariye)
        # DIQQAT: Bu yerda Q, G', H kabi undoshlar bo'lmasligi kerak!
        vowels = "АаЕеЁёИиОоУуЎўЮюЯя" 
        text = re.sub(rf"([{vowels}])Е", r"\1Ye", text)
        text = re.sub(rf"([{vowels}])е", r"\1ye", text)
        
        # 4. Qolgan holatlarda (undoshlardan keyin) "Е" -> "E"
        # (Masalan: Hеch -> Hech, Darvoqе -> Darvoqe, Voqеa -> Voqea)
        text = text.replace("Е", "E").replace("е", "e")
        
        return text
    
    text = fix_E(text)
    
    # Murakkab kombinatsiyalar
    mapping = [
        ('қў',"qo'"),('Қў',"Qo'"),
        ('ё','yo'),('Ё','Yo'),
        ('ю','yu'),('Ю','Yu'),
        ('я','ya'),('Я','Ya'),
        ('ш','sh'),('Ш','Sh'),
        ('ч','ch'),('Ч','Ch'),
        ('нг','ng'),('Нг','Ng'),('НГ','NG'),
        ('ў',"o'"),('Ў',"O'"),
        ('ғ',"g'"),('Ғ',"G'"),
        ('қ','q'), ('Қ','Q'),
        ('ҳ','h'), ('Ҳ','H'),
        ('ж','j'), ('Ж','J'),
    ]
    
    for cyr, lat in mapping:
        text = text.replace(cyr, lat)
    
    chars = {
        'а':'a','б':'b','в':'v','г':'g','д':'d',
        'з':'z','и':'i','й':'y','к':'k','л':'l',
        'м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'x',
        'ц':'ts','щ':'shch','ъ':"'",'ь':'','ы':'i',
        'e':'e', 
        
        'А':'A','Б':'B','В':'V','Г':'G','Д':'D',
        'З':'Z','И':'I','Й':'Y','К':'K','Л':'L',
        'М':'M','Н':'N','О':'O','П':'P','Р':'R',
        'С':'S','Т':'T','У':'U','Ф':'F','Х':'X',
        'Ц':'Ts','Щ':'Shch','Ъ':"'",'Ь':'','Ы':'I',
        'E':'E'
    }
    
    return ''.join(chars.get(ch, ch) for ch in text)

# ===================== AI FUNCTION =====================
def call_gemini(prompt: str) -> str:
    """Gemini AI bilan ishlash"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.exception("Gemini xatosi")
        return f"❌ Kechirasiz, xatolik yuz berdi: {str(e)}"

# ===================== KEYBOARDS =====================
MAIN_KEYBOARD = [
    ["📝 Lotin → Kiril", "📝 Kiril → Lotin"],
    ["💬 ChatBot", "🎵 Musiqa tahrirlash"],
    ["✂️ Ovoz kesuvchi", "🎶 MP3 ga aylantirish"],
    ["📊 Statistika", "📩 Adminga xabar"]
]
MAIN_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

CANCEL_KEYBOARD = [["❌ Bekor qilish"]]
CANCEL_MARKUP = ReplyKeyboardMarkup(CANCEL_KEYBOARD, resize_keyboard=True)

# ===================== START & HELP =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ishga tushganda"""
    user = update.effective_user
    context.bot_data.setdefault('users', set())
    context.bot_data['users'].add(user.id)
    
    # Mode reset
    context.user_data.clear()
    
    welcome = (
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        "🤖 Men ko'p funksiyali yordamchi botman!\n\n"
        "🎯 <b>Imkoniyatlar:</b>\n"
        "📝 Lotin ⇄ Kiril transliteratsiya\n"
        "💬 AI ChatBot (Gemini)\n"
        "🎵 Musiqa metadata tahrirlash\n"
        "✂️ Audio kesish va qayta ishlash\n"
        "📊 Statistika va admin aloqasi\n\n"
        "💡 <b>Maslahat:</b> Tugmalarni bosing yoki /help buyrug'ini kiriting!"
    )
    
    await update.message.reply_text(
        welcome,
        reply_markup=MAIN_MARKUP,
        parse_mode='HTML'
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam va buyruqlar"""
    help_text = (
        "📚 <b>YORDAM VA BUYRUQLAR</b>\n\n"
        "🎯 <b>Asosiy buyruqlar:</b>\n"
        "/start - Botni qayta boshlash\n"
        "/help - Yordam ko'rsatish\n"
        "/cancel - Jarayonni bekor qilish\n"
        "/menu - Asosiy menyu\n\n"
        
        "📝 <b>Transliteratsiya:</b>\n"
        "/lat2kir - Lotin → Kiril\n"
        "/kir2lat - Kiril → Lotin\n\n"
        
        "🎵 <b>Audio funksiyalar:</b>\n"
        "/music - Musiqa tahrirlash\n"
        "/cut - Ovoz kesish\n"
        "/convert - MP3 formatga\n\n"
        
        "💬 <b>Boshqa:</b>\n"
        "/chat - AI bilan suhbat\n"
        "/stats - Statistika\n"
        "/admin - Adminga xabar\n\n"
        
        "💡 <b>Maslahat:</b>\n"
        "Har bir funksiyani ishlatish uchun tegishli tugmani bosing yoki buyruqni yozing!"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy menyuga qaytish"""
    context.user_data.clear()
    await update.message.reply_text(
        "🏠 <b>Asosiy menyu</b>\n\nKerakli bo'limni tanlang:",
        reply_markup=MAIN_MARKUP,
        parse_mode='HTML'
    )

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistika"""
    total = len(context.bot_data.get('users', set()))
    await update.message.reply_text(
        f"📊 <b>BOT STATISTIKASI</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total}</b> ta\n"
        f"🤖 Bot versiyasi: <b>2.0</b>\n"
        f"⚡ Status: <b>Faol</b>",
        parse_mode='HTML'
    )

# ===================== MODE COMMANDS =====================
async def lat2kir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lotin → Kiril mode"""
    context.user_data['mode'] = 'lat2kir'
    await update.message.reply_text(
        "📝 <b>LOTIN → KIRIL</b>\n\n"
        "✏️ Lotincha matn yuboring, men uni kirilga o'giraman!\n\n"
        "📌 <i>Misol: Salom dunyo → Салом дунё</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

async def kir2lat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiril → Lotin mode"""
    context.user_data['mode'] = 'kir2lat'
    await update.message.reply_text(
        "📝 <b>KIRIL → LOTIN</b>\n\n"
        "✏️ Kirilcha matn yuboring, men uni lotinga o'giraman!\n\n"
        "📌 <i>Misol: Салом дунё → Salom dunyo</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ChatBot mode"""
    context.user_data['mode'] = 'chat'
    await update.message.reply_text(
        "💬 <b>AI CHATBOT</b>\n\n"
        "🤖 Menga savol bering, men javob beraman!\n\n"
        "📌 <i>Masalan: \"Python dasturlash haqida gapirib ber\"</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqa tahrirlash mode"""
    context.user_data['mode'] = 'music_edit'
    await update.message.reply_text(
        "🎵 <b>MUSIQA TAHRIRLASH</b>\n\n"
        "📁 MP3 faylini yuboring!\n\n"
        "Men uning <b>Title</b> (Qo'shiq nomi) va <b>Author</b> (Ijrochi)ni o'zgartiraman.\n\n"
        "💡 <i>Fayl yuklangandan keyin ko'rsatma beraman!</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

async def cut_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovoz kesish mode"""
    context.user_data['mode'] = 'voice_cutter'
    await update.message.reply_text(
        "✂️ <b>OVOZ KESUVCHI</b>\n\n"
        "🎵 Audio fayl yuboring!\n\n"
        "Keyin vaqtni kiriting:\n"
        "📌 <b>Format:</b> 00:10-00:30\n\n"
        "💡 <i>(10-soniyadan 30-soniyagacha kesadi)</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

async def convert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MP3 ga aylantirish mode"""
    context.user_data['mode'] = 'voice_to_music'
    await update.message.reply_text(
        "🎶 <b>MP3 GA AYLANTIRISH</b>\n\n"
        "🎤 Audio yoki ovoz xabari yuboring!\n\n"
        "Men uni <b>MP3 formatga</b> aylantirib beraman.\n\n"
        "⚡ <i>Tez va sifatli!</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminga xabar mode"""
    context.user_data['mode'] = 'admin_msg'
    await update.message.reply_text(
        "📩 <b>ADMINGA XABAR</b>\n\n"
        "✉️ Xabar matnini yozing!\n\n"
        "Admin ko'rib, javob beradi.\n\n"
        "💡 <i>Iltimos, savol yoki taklifingizni aniq yozing.</i>",
        reply_markup=CANCEL_MARKUP,
        parse_mode='HTML'
    )

# ===================== BUTTON HANDLER =====================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalarni boshqarish"""
    text = update.message.text.strip()
    
    button_map = {
        "📝 Lotin → Kiril": lat2kir_cmd,
        "📝 Kiril → Lotin": kir2lat_cmd,
        "💬 ChatBot": chat_cmd,
        "🎵 Musiqa tahrirlash": music_cmd,
        "✂️ Ovoz kesuvchi": cut_cmd,
        "🎶 MP3 ga aylantirish": convert_cmd,
        "📊 Statistika": stats_cmd,
        "📩 Adminga xabar": admin_cmd,
        "❌ Bekor qilish": cancel,
    }
    
    if text in button_map:
        await button_map[text](update, context)
    else:
        await update.message.reply_text(
            "❓ Noma'lum tugma. /help buyrug'ini kiriting.",
            reply_markup=MAIN_MARKUP
        )

# ===================== TEXT HANDLER =====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matn xabarlarni qayta ishlash"""
    mode = context.user_data.get('mode')
    text = update.message.text or ""
    uid = update.message.from_user.id
    
    # Agar bekor qilish bo'lsa
    if text == "❌ Bekor qilish":
        await cancel(update, context)
        return
    
    if not mode:
        await update.message.reply_text(
            "❗ Iltimos, avval bo'limni tanlang!\n\n"
            "Tugmalardan birini bosing yoki /help buyrug'ini kiriting.",
            reply_markup=MAIN_MARKUP
        )
        return
    
   # Lotin → Kiril
    if mode == 'lat2kir':
        result = to_cyrillic(text)
        await update.message.reply_text(
            f"{result}"
            parse_mode='HTML')

# Kiril → Lotin
    elif mode == 'kir2lat':
        result = to_latin(text)
        await update.message.reply_text(
            f"{result}",
            parse_mode='HTML')

    
    # ChatBot
    elif mode == 'chat':
        msg = await update.message.reply_text("💬 Javob tayyorlanmoqda...")
        reply = call_gemini(f"Foydalanuvchi so'rovi: {text}\n\nJavob bering:")
        await msg.edit_text(
            f"🤖 <b>JAVOB:</b>\n\n{reply}\n\n"
            f"💬 <i>Yana savol bering yoki /menu bilan chiqing</i>",
            parse_mode='HTML'
        )
    
    # Ovoz kesish vaqti
    elif mode == 'voice_wait_time':
        await process_voice_cut(update, context, text)
    
    # Musiqa title
    elif mode == 'music_wait_title':
        context.user_data['music_title'] = text
        context.user_data['mode'] = 'music_wait_author'
        await update.message.reply_text(
            f"✅ Title qabul qilindi: <b>{text}</b>\n\n"
            f"👤 Endi <b>Author</b> (Ijrochi) nomini kiriting:",
            parse_mode='HTML'
        )
    
    # Musiqa author
    elif mode == 'music_wait_author':
        context.user_data['music_author'] = text
        await process_music_edit(update, context)
    
    # Adminga xabar
    elif mode == 'admin_msg':
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✉️ Javob berish", callback_data=f"reply_{uid}")
        ]])
        await context.bot.send_message(
            ADMIN_ID,
            f"📨 <b>YANGI XABAR</b>\n\n"
            f"👤 Foydalanuvchi ID: <code>{uid}</code>\n"
            f"📝 Xabar:\n\n{text}",
            reply_markup=markup,
            parse_mode='HTML'
        )
        await update.message.reply_text(
            "✅ <b>Xabaringiz yuborildi!</b>\n\n"
            "📬 Admin ko'rib chiqadi va javob beradi.",
            reply_markup=MAIN_MARKUP,
            parse_mode='HTML'
        )
        context.user_data.clear()
    
    # Admin javobi
    elif mode == 'reply_user' and uid == ADMIN_ID:
        target = context.user_data.get('reply_to_user')
        if target:
            await context.bot.send_message(
                target,
                f"💌 <b>ADMIN JAVOBI:</b>\n\n{text}",
                parse_mode='HTML'
            )
            await update.message.reply_text(
                "✅ Javob yuborildi!",
                reply_markup=MAIN_MARKUP
            )
            context.user_data.clear()

# ===================== AUDIO HANDLERS =====================
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio fayllarni qayta ishlash"""
    mode = context.user_data.get('mode')
    audio = update.message.audio
    
    if not audio:
        await update.message.reply_text("❌ Audio fayl topilmadi!")
        return
    
    if mode == 'music_edit':
        msg = await update.message.reply_text("📥 Fayl yuklanmoqda...")
        try:
            file = await audio.get_file()
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                path = f.name
                await file.download_to_drive(path)
            
            context.user_data['music_file'] = path
            context.user_data['mode'] = 'music_wait_title'
            
            await msg.edit_text(
                "✅ <b>Musiqa yuklandi!</b> 🎵\n\n"
                "📝 Endi <b>Title</b> (Qo'shiq nomi) kiriting:\n\n"
                "💡 <i>Masalan: \"Muhabbat qo'shig'i\"</i>",
                parse_mode='HTML'
            )
        except Exception as e:
            await msg.edit_text(f"❌ Xatolik: {e}")
            context.user_data.clear()
    
    elif mode in ('voice_cutter', 'voice_to_music'):
        await handle_voice(update, context)
    
    else:
        await update.message.reply_text(
            "❗ Iltimos, avval tegishli bo'limni tanlang:\n"
            "• /music - Musiqa tahrirlash\n"
            "• /cut - Ovoz kesish\n"
            "• /convert - MP3 ga aylantirish",
            reply_markup=MAIN_MARKUP
        )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovoz xabarlarini qayta ishlash"""
    mode = context.user_data.get('mode')
    voice = update.message.voice or update.message.audio
    
    if not voice:
        await update.message.reply_text("❌ Audio topilmadi!")
        return
    
    if mode not in ('voice_cutter', 'voice_to_music'):
        await update.message.reply_text(
            "❗ Iltimos, avval bo'limni tanlang:\n"
            "• /cut - Ovoz kesish\n"
            "• /convert - MP3 ga aylantirish",
            reply_markup=MAIN_MARKUP
        )
        return
    
    msg = await update.message.reply_text("📥 Audio yuklanmoqda...")
    
    try:
        file = await voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
            await file.download_to_drive(path)
        
        if mode == 'voice_cutter':
            context.user_data['voice_file'] = path
            context.user_data['mode'] = 'voice_wait_time'
            
            audio = AudioSegment.from_file(path)
            duration = len(audio) // 1000
            minutes = duration // 60
            seconds = duration % 60
            
            await msg.edit_text(
                f"✅ <b>Audio yuklandi!</b> ⏱\n\n"
                f"📊 Uzunlik: <b>{minutes:02d}:{seconds:02d}</b>\n\n"
                f"✂️ Kesish vaqtini kiriting:\n"
                f"📌 <b>Format:</b> 00:10-00:30\n\n"
                f"💡 <i>00:00 dan {minutes:02d}:{seconds:02d} gacha</i>",
                parse_mode='HTML'
            )
        
        elif mode == 'voice_to_music':
            await msg.edit_text("🔄 Qayta ishlanmoqda...")
            audio = AudioSegment.from_file(path)
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f2:
                out_path = f2.name
                audio.export(out_path, format="mp3", bitrate="192k")
            
            await msg.delete()
            with open(out_path, "rb") as audio_file:
                await update.message.reply_audio(
                    audio_file,
                    caption="✅ <b>Tayyor!</b> 🎶\n\n<i>Yana audio yuboring yoki /menu bilan chiqing</i>",
                    parse_mode='HTML'
                )
            
            os.remove(out_path)
            os.remove(path)
            
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
        logger.exception("Audio processing error")
        context.user_data.clear()

# ===================== PROCESS FUNCTIONS =====================
async def process_voice_cut(update: Update, context: ContextTypes.DEFAULT_TYPE, time_text: str):
    """Ovozni kesish jarayoni"""
    voice_file = context.user_data.get('voice_file')
    
    if not voice_file or not os.path.exists(voice_file):
        await update.message.reply_text(
            "❌ Audio fayl topilmadi!\n\n"
            "Iltimos, qaytadan /cut buyrug'ini kiriting.",
            reply_markup=MAIN_MARKUP
        )
        context.user_data.clear()
        return
    
    # Vaqt formatini tekshirish
    match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", time_text.strip())
    if not match:
        await update.message.reply_text(
            "❌ <b>Format xato!</b>\n\n"
            "📌 To'g'ri format: <code>00:10-00:30</code>\n\n"
            "💡 Yana urinib ko'ring:",
            parse_mode='HTML'
        )
        return
    
    s_min, s_sec, e_min, e_sec = map(int, match.groups())
    start_ms = (s_min * 60 + s_sec) * 1000
    end_ms = (e_min * 60 + e_sec) * 1000
    
    if start_ms >= end_ms:
        await update.message.reply_text(
            "❌ <b>Xato!</b>\n\n"
            "Boshlanish vaqti tugash vaqtidan kichik bo'lishi kerak!\n\n"
            "💡 Qayta kiriting:",
            parse_mode='HTML'
        )
        return
    
    msg = await update.message.reply_text("✂️ Kesilmoqda...")
    
    try:
        audio = AudioSegment.from_file(voice_file)
        
        if end_ms > len(audio):
            duration = len(audio) // 1000
            minutes = duration // 60
            seconds = duration % 60
            await msg.edit_text(
                f"❌ <b>Vaqt xato!</b>\n\n"
                f"📊 Audio uzunligi: <b>{minutes:02d}:{seconds:02d}</b>\n\n"
                f"💡 Vaqtni qayta kiriting:",
                parse_mode='HTML'
            )
            return
        
        # Kesish
        cut_audio = audio[start_ms:end_ms]
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            cut_path = f.name
            cut_audio.export(cut_path, format="mp3", bitrate="192k")
        
        await msg.delete()
        
        duration = len(cut_audio) // 1000
        with open(cut_path, "rb") as audio_file:
            await update.message.reply_audio(
                audio_file,
                caption=f"✅ <b>Audio kesildi!</b> ✂️\n\n"
                        f"⏱ Uzunlik: <b>{duration} soniya</b>\n\n"
                        f"<i>Yana kesish uchun audio yuboring yoki /menu</i>",
                parse_mode='HTML'
            )
        
        os.remove(cut_path)
        
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")
        logger.exception("Voice cut error")
    
    finally:
        if os.path.exists(voice_file):
            os.remove(voice_file)
        context.user_data.pop('voice_file', None)

async def process_music_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqa metadata tahrirlash"""
    music_file = context.user_data.get('music_file')
    title = context.user_data.get('music_title', 'Unknown')
    author = context.user_data.get('music_author', 'Unknown')
    
    if not music_file or not os.path.exists(music_file):
        await update.message.reply_text(
            "❌ Musiqa fayli topilmadi!\n\n"
            "Iltimos, qaytadan /music buyrug'ini kiriting.",
            reply_markup=MAIN_MARKUP
        )
        context.user_data.clear()
        return
    
    msg = await update.message.reply_text("🎵 Metadata o'zgartirilmoqda...")
    
    try:
        # Audio faylni o'qish
        audio = AudioSegment.from_file(music_file)
        
        # Yangi fayl yaratish
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            output_path = f.name
            audio.export(output_path, format="mp3", bitrate="192k")
        
        # ID3 tags qo'shish
        try:
            audio_file = MP3(output_path, ID3=ID3)
            try:
                audio_file.add_tags()
            except:
                pass
        except:
            audio_file = MP3(output_path)
        
        # Metadata yozish
        audio_file.tags.add(TIT2(encoding=3, text=title))
        audio_file.tags.add(TPE1(encoding=3, text=author))
        audio_file.save()
        
        await msg.delete()
        
        # Faylni yuborish
        with open(output_path, "rb") as f:
            await update.message.reply_audio(
                f,
                title=title,
                performer=author,
                caption=f"✅ <b>Tayyor!</b> 🎵\n\n"
                        f"📝 <b>Title:</b> {title}\n"
                        f"👤 <b>Author:</b> {author}\n\n"
                        f"<i>Yana tahrirlash uchun /music</i>",
                parse_mode='HTML'
            )
        
        os.remove(output_path)
        
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")
        logger.exception("Music edit error")
    
    finally:
        if os.path.exists(music_file):
            os.remove(music_file)
        context.user_data.clear()

# ===================== CALLBACK HANDLER =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline tugmalar callback"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("reply_") and query.from_user.id == ADMIN_ID:
        user_id = int(query.data.split("_")[1])
        context.user_data['reply_to_user'] = user_id
        context.user_data['mode'] = 'reply_user'
        
        await query.message.reply_text(
            f"✏️ <b>Foydalanuvchi {user_id} ga javob:</b>\n\n"
            f"Javob matnini yozing:",
            parse_mode='HTML'
        )

# ===================== CANCEL =====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Amalni bekor qilish"""
    # Fayllarni tozalash
    voice_file = context.user_data.get('voice_file')
    music_file = context.user_data.get('music_file')
    
    if voice_file and os.path.exists(voice_file):
        os.remove(voice_file)
    if music_file and os.path.exists(music_file):
        os.remove(music_file)
    
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ <b>Amal bekor qilindi!</b>\n\n"
        "🏠 Bosh menyuga qaytdingiz.",
        reply_markup=MAIN_MARKUP,
        parse_mode='HTML'
    )

# ===================== ERROR HANDLER =====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global xatolarni tutish"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ <b>Xatolik yuz berdi!</b>\n\n"
            "Iltimos, qaytadan urinib ko'ring yoki /start buyrug'ini kiriting.",
            parse_mode='HTML',
            reply_markup=MAIN_MARKUP
        )

# ===================== MAIN =====================
def main():
    """Botni ishga tushirish"""
    logger.info("🤖 Bot ishga tushmoqda...")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # ===== BUYRUQLAR =====
    # Asosiy
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    
    # Funksional
    app.add_handler(CommandHandler("lat2kir", lat2kir_cmd))
    app.add_handler(CommandHandler("kir2lat", kir2lat_cmd))
    app.add_handler(CommandHandler("chat", chat_cmd))
    app.add_handler(CommandHandler("music", music_cmd))
    app.add_handler(CommandHandler("cut", cut_cmd))
    app.add_handler(CommandHandler("convert", convert_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    
    # ===== TUGMALAR =====
    button_filter = filters.TEXT & filters.Regex(
        r"^(📝 Lotin → Kiril|📝 Kiril → Lotin|💬 ChatBot|🎵 Musiqa tahrirlash|"
        r"✂️ Ovoz kesuvchi|🎶 MP3 ga aylantirish|📊 Statistika|📩 Adminga xabar|❌ Bekor qilish)$"
    )
    app.add_handler(MessageHandler(button_filter, handle_buttons))
    
    # ===== MEDIA =====
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # ===== CALLBACK =====
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # ===== MATN =====
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    # ===== ERROR HANDLER =====
    app.add_error_handler(error_handler)
    
    logger.info("✅ Bot muvaffaqiyatli ishga tushdi!")
    logger.info("📱 Telegram botingiz tayyor!")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
