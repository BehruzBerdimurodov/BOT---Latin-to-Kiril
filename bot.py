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
GENAI_API_KEY = os.environ.get("GENAI_API_KEY") or "AIzaSyBbnOkS0QwEt5CDxHdHhlMTdsO4vgwPdMI"
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

# ===================== KIRIL → LOTIN =====================
def to_latin(text):
    """Kirildan lotinga transliteratsiya"""
    
    def fix_E(text):
        text = text.replace("Э", "E").replace("э", "e")
        text = re.sub(r"\bЕ", "Ye", text)
        text = re.sub(r"\bе", "ye", text)
        vowels = "АаЕеЁёИиОоУуЎўЮюЯя" 
        text = re.sub(rf"([{vowels}])Е", r"\1Ye", text)
        text = re.sub(rf"([{vowels}])е", r"\1ye", text)
        text = text.replace("Е", "E").replace("е", "e")
        return text
    
    text = fix_E(text)
    
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
        's':'s','т':'t','у':'u','ф':'f','х':'x',
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
    ["🎛 Remix Voices", "📊 Statistika"],  # <--- YANGI TUGMA QO'SHILDI
    ["📩 Adminga xabar"]
]
MAIN_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

# Remix rejimi uchun maxsus klaviatura
REMIX_KEYBOARD = [
    ["▶️ Remix Start"], 
    ["❌ Bekor qilish"]
]
REMIX_MARKUP = ReplyKeyboardMarkup(REMIX_KEYBOARD, resize_keyboard=True)

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
        "🎛 <b>Remix Voices (Yangi!)</b>\n"
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
        "/convert - MP3 formatga\n"
        "/remix - Ovoz birlashtirish (Remix)\n\n" # <--- YANGI
        
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
    await cancel(update, context) # Tozalab keyin menyuga qaytamiz
    

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistika"""
    total = len(context.bot_data.get('users', set()))
    await update.message.reply_text(
        f"📊 <b>BOT STATISTIKASI</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total}</b> ta\n"
        f"🤖 Bot versiyasi: <b>2.1 Remix</b>\n"
        f"⚡ Status: <b>Faol</b>",
        parse_mode='HTML'
    )

# ===================== MODE COMMANDS =====================
async def lat2kir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'lat2kir'
    await update.message.reply_text(
        "📝 <b>LOTIN → KIRIL</b>\n\n✏️ Lotincha matn yuboring!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

async def kir2lat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'kir2lat'
    await update.message.reply_text(
        "📝 <b>KIRIL → LOTIN</b>\n\n✏️ Kirilcha matn yuboring!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'chat'
    await update.message.reply_text(
        "💬 <b>AI CHATBOT</b>\n\n🤖 Menga savol bering!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'music_edit'
    await update.message.reply_text(
        "🎵 <b>MUSIQA TAHRIRLASH</b>\n\n📁 MP3 faylini yuboring!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

async def cut_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'voice_cutter'
    await update.message.reply_text(
        "✂️ <b>OVOZ KESUVCHI</b>\n\n🎵 Audio fayl yuboring!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

async def convert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'voice_to_music'
    await update.message.reply_text(
        "🎶 <b>MP3 GA AYLANTIRISH</b>\n\n🎤 Audio yoki ovoz xabari yuboring!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

# --- YANGI REMIX MODE ---
async def remix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remix rejimi"""
    context.user_data['mode'] = 'remix_wait_files'
    context.user_data['remix_files'] = [] # Fayllarni yig'ish uchun ro'yxat
    
    await update.message.reply_text(
        "🎛 <b>REMIX VOICES</b>\n\n"
        "1️⃣ Menga bir nechta ovozli xabar yoki audio yuboring.\n"
        "2️⃣ Yuborib bo'lgach <b>'▶️ Remix Start'</b> tugmasini bosing.\n"
        "3️⃣ Men ularni bitta qilib birlashtirib beraman!\n\n"
        "👇 <i>Ovozlarni yuborishni boshlang!</i>",
        reply_markup=REMIX_MARKUP,
        parse_mode='HTML'
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'admin_msg'
    await update.message.reply_text(
        "📩 <b>ADMINGA XABAR</b>\n\n✉️ Xabar matnini yozing!",
        reply_markup=CANCEL_MARKUP, parse_mode='HTML'
    )

# ===================== BUTTON HANDLER =====================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    button_map = {
        "📝 Lotin → Kiril": lat2kir_cmd,
        "📝 Kiril → Lotin": kir2lat_cmd,
        "💬 ChatBot": chat_cmd,
        "🎵 Musiqa tahrirlash": music_cmd,
        "✂️ Ovoz kesuvchi": cut_cmd,
        "🎶 MP3 ga aylantirish": convert_cmd,
        "🎛 Remix Voices": remix_cmd, # <--- XARITAGA QO'SHILDI
        "📊 Statistika": stats_cmd,
        "📩 Adminga xabar": admin_cmd,
        "❌ Bekor qilish": cancel,
    }
    
    # Remix start tugmasini alohida tekshiramiz
    if text == "▶️ Remix Start":
        await process_remix_start(update, context)
        return

    if text in button_map:
        await button_map[text](update, context)
    else:
        await update.message.reply_text(
            "❓ Noma'lum tugma. /help buyrug'ini kiriting.",
            reply_markup=MAIN_MARKUP
        )

# ===================== TEXT HANDLER =====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    text = update.message.text or ""
    uid = update.message.from_user.id
    
    if text == "❌ Bekor qilish":
        await cancel(update, context)
        return
    
    if not mode:
        await update.message.reply_text("❗ Bo'limni tanlang!", reply_markup=MAIN_MARKUP)
        return
    
    if mode == 'lat2kir':
        await update.message.reply_text(to_cyrillic(text), parse_mode='HTML')
    elif mode == 'kir2lat':
        await update.message.reply_text(to_latin(text), parse_mode='HTML')
    elif mode == 'chat':
        msg = await update.message.reply_text("💬 ...")
        reply = call_gemini(f"{text}")
        await msg.edit_text(reply, parse_mode='Markdown')
    
    elif mode == 'voice_wait_time':
        await process_voice_cut(update, context, text)
        
    elif mode == 'music_wait_title':
        context.user_data['music_title'] = text
        context.user_data['mode'] = 'music_wait_author'
        await update.message.reply_text(f"✅ Title: {text}\n👤 Authorni kiriting:")
        
    elif mode == 'music_wait_author':
        context.user_data['music_author'] = text
        await process_music_edit(update, context)
        
    elif mode == 'admin_msg':
        # Admin logikasi (o'zgarishsiz)
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Javob", callback_data=f"reply_{uid}")]])
        await context.bot.send_message(ADMIN_ID, f"📨 ID: {uid}\nMsg: {text}", reply_markup=markup)
        await update.message.reply_text("✅ Yuborildi!", reply_markup=MAIN_MARKUP)
        context.user_data.clear()
        
    elif mode == 'reply_user' and uid == ADMIN_ID:
        target = context.user_data.get('reply_to_user')
        if target:
            await context.bot.send_message(target, f"💌 <b>JAVOB:</b>\n{text}", parse_mode='HTML')
            await update.message.reply_text("✅ Javob ketdi!", reply_markup=MAIN_MARKUP)
            context.user_data.clear()

# ===================== AUDIO HANDLERS =====================
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    audio = update.message.audio
    
    if not audio: return
    
    # --- REMIX LOGIKASI (AUDIO UCHUN) ---
    if mode == 'remix_wait_files':
        file = await audio.get_file()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
            await file.download_to_drive(path)
            
        # Ro'yxatga qo'shamiz
        files_list = context.user_data.get('remix_files', [])
        files_list.append(path)
        context.user_data['remix_files'] = files_list
        
        await update.message.reply_text(
            f"✅ <b>Audio qo'shildi!</b>\n"
            f"📥 Jami fayllar: <b>{len(files_list)}</b> ta\n\n"
            f"Yana yuboring yoki <b>'▶️ Remix Start'</b> ni bosing.",
            parse_mode='HTML',
            reply_markup=REMIX_MARKUP
        )
        return
    # -------------------------------------

    if mode == 'music_edit':
        msg = await update.message.reply_text("📥 Yuklanmoqda...")
        file = await audio.get_file()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
            await file.download_to_drive(path)
        context.user_data['music_file'] = path
        context.user_data['mode'] = 'music_wait_title'
        await msg.edit_text("✅ Yuklandi! Title kiriting:")
        
    elif mode in ('voice_cutter', 'voice_to_music'):
        await handle_voice(update, context) # Audio bo'lsa ham voice funksiyasiga o'tkazamiz

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    voice = update.message.voice or update.message.audio
    
    if not voice: return
    
    msg = await update.message.reply_text("📥 Yuklanmoqda...")
    file = await voice.get_file()
    
    # --- REMIX LOGIKASI (VOICE UCHUN) ---
    if mode == 'remix_wait_files':
        # Ogg yoki Mp3 bo'lishi mumkin, pydub o'zi hal qiladi, lekin tempga olamiz
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            path = f.name
            await file.download_to_drive(path)
            
        files_list = context.user_data.get('remix_files', [])
        files_list.append(path)
        context.user_data['remix_files'] = files_list
        
        await msg.edit_text(
            f"✅ <b>Ovoz qo'shildi!</b>\n"
            f"📥 Jami fayllar: <b>{len(files_list)}</b> ta\n\n"
            f"Yana yuboring yoki <b>'▶️ Remix Start'</b> ni bosing.",
            parse_mode='HTML'
        )
        return
    # -------------------------------------

    # Boshqa rejimlar uchun
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
        await file.download_to_drive(path)

    if mode == 'voice_cutter':
        context.user_data['voice_file'] = path
        context.user_data['mode'] = 'voice_wait_time'
        audio_seg = AudioSegment.from_file(path)
        dur = len(audio_seg)//1000
        await msg.edit_text(f"✅ Yuklandi! Uzunlik: {dur//60:02d}:{dur%60:02d}\nKesish vaqtini kiriting (00:00-00:10):")
        
    elif mode == 'voice_to_music':
        await msg.edit_text("🔄 MP3 ga o'girilmoqda...")
        audio_seg = AudioSegment.from_file(path)
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f2:
            out_path = f2.name
            audio_seg.export(out_path, format="mp3", bitrate="192k")
        
        await msg.delete()
        with open(out_path, "rb") as af:
            await update.message.reply_audio(af, caption="✅ MP3 Tayyor!")
        os.remove(out_path)
        os.remove(path)
        
    else:
        await msg.edit_text("❗ Avval bo'limni tanlang!", reply_markup=MAIN_MARKUP)
        os.remove(path)

# ===================== PROCESS FUNCTIONS =====================

# --- YANGI REMIX PROCESS FUNCTION ---
async def process_remix_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yig'ilgan fayllarni birlashtirish"""
    files = context.user_data.get('remix_files', [])
    
    if not files:
        await update.message.reply_text("❌ Hali hech qanday ovoz yubormadingiz!", reply_markup=REMIX_MARKUP)
        return

    msg = await update.message.reply_text("🔄 <b>Remix tayyorlanmoqda...</b>\n\nIltimos kuting...", parse_mode='HTML')

    try:
        combined_audio = AudioSegment.empty()
        
        # Barcha fayllarni ochib, ketma-ket ulaymiz
        for file_path in files:
            try:
                sound = AudioSegment.from_file(file_path)
                combined_audio += sound # Concatenation (Ulash)
            except Exception as e:
                logger.error(f"Faylni o'qishda xato: {e}")
        
        # Natijani saqlash
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            output_path = f.name
            combined_audio.export(output_path, format="mp3", bitrate="192k")
            
        await msg.delete()
        
        # Foydalanuvchiga yuborish
        with open(output_path, "rb") as audio_file:
            await update.message.reply_audio(
                audio_file,
                caption=f"🎛 <b>Remix Tayyor!</b>\n\n"
                        f"🔗 Birlashtirilgan fayllar: {len(files)} ta\n"
                        f"🤖 <i>Bot: @{context.bot.username}</i>",
                parse_mode='HTML',
                reply_markup=MAIN_MARKUP # Ish tugadi, asosiy menyuga qaytamiz
            )
            
        # Tozalash
        os.remove(output_path)
        for fp in files:
            if os.path.exists(fp):
                os.remove(fp)
        
        context.user_data.clear()

    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")
        logger.exception("Remix error")
# -------------------------------------

async def process_voice_cut(update: Update, context: ContextTypes.DEFAULT_TYPE, time_text: str):
    voice_file = context.user_data.get('voice_file')
    if not voice_file: return
    
    match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", time_text.strip())
    if not match:
        await update.message.reply_text("❌ Format xato! Masalan: 00:10-00:30")
        return
        
    s_m, s_s, e_m, e_s = map(int, match.groups())
    start_ms = (s_m * 60 + s_s) * 1000
    end_ms = (e_m * 60 + e_s) * 1000
    
    if start_ms >= end_ms:
        await update.message.reply_text("❌ Vaqt noto'g'ri!")
        return

    msg = await update.message.reply_text("✂️ Kesilmoqda...")
    try:
        audio = AudioSegment.from_file(voice_file)
        cut = audio[start_ms:end_ms]
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            c_path = f.name
            cut.export(c_path, format="mp3")
            
        await msg.delete()
        with open(c_path, "rb") as af:
            await update.message.reply_audio(af, caption="✅ Kesildi!")
        os.remove(c_path)
    except Exception as e:
        await msg.edit_text(f"Xato: {e}")
    finally:
        os.remove(voice_file)
        context.user_data.clear()

async def process_music_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m_file = context.user_data.get('music_file')
    title = context.user_data.get('music_title')
    author = context.user_data.get('music_author')
    
    msg = await update.message.reply_text("🎵 O'zgartirilmoqda...")
    try:
        audio = AudioSegment.from_file(m_file)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            out = f.name
            audio.export(out, format="mp3")
            
        mp3 = MP3(out, ID3=ID3)
        try: mp3.add_tags()
        except: pass
        mp3.tags.add(TIT2(encoding=3, text=title))
        mp3.tags.add(TPE1(encoding=3, text=author))
        mp3.save()
        
        await msg.delete()
        with open(out, "rb") as af:
            await update.message.reply_audio(af, caption="✅ Metadata o'zgardi!")
        os.remove(out)
    except Exception as e:
        await msg.edit_text(f"Xato: {e}")
    finally:
        os.remove(m_file)
        context.user_data.clear()

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("reply_") and query.from_user.id == ADMIN_ID:
        uid = int(query.data.split("_")[1])
        context.user_data['reply_to_user'] = uid
        context.user_data['mode'] = 'reply_user'
        await query.message.reply_text(f"✏️ User {uid} ga javob yozing:")

# ===================== CANCEL =====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tozalash va bekor qilish"""
    # Eski fayllarni o'chirish
    for key in ['voice_file', 'music_file']:
        f = context.user_data.get(key)
        if f and os.path.exists(f): os.remove(f)
        
    # Remix fayllarini tozalash
    remix_files = context.user_data.get('remix_files', [])
    for f in remix_files:
        if f and os.path.exists(f): os.remove(f)

    context.user_data.clear()
    await update.message.reply_text(
        "🏠 <b>Bosh menyu</b>", 
        reply_markup=MAIN_MARKUP, 
        parse_mode='HTML'
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ===================== MAIN =====================
def main():
    logger.info("🤖 Bot ishga tushmoqda...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    
    # Mode komandalari
    for cmd in ["lat2kir","kir2lat","chat","music","cut","convert","admin"]:
        app.add_handler(CommandHandler(cmd, globals()[f"{cmd}_cmd"]))
    app.add_handler(CommandHandler("remix", remix_cmd)) # Remix buyrug'i
    
    # Tugmalar
    app.add_handler(MessageHandler(filters.Regex(r"^(📝|💬|🎵|✂️|🎶|📊|📩|🎛|❌|▶️)"), handle_buttons))
    
    # Media
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_error_handler(error_handler)
    
    logger.info("✅ Bot tayyor!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
