import os
import logging
import re
import tempfile
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from pydub import AudioSegment
import google.generativeai as genai

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "727974350:AAFM3LfQ18Bur6oDacjRNnnoLYRKkUjEoXM"

GENAI_API_KEY = os.environ.get("GENAI_API_KEY") or "AIzaSyAy5qfTSrOLS5DwcrLWnJJDvX_UJCLFGbU"

ADMIN_ID = int(os.environ.get("ADMIN_ID") or 468374402)

# --- Configure Gemini ---
genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== TRANSLITERATION MODULE =====================

# --- 1. Diakritiklarni normallashtirish (Lotin uchun) ---
latin_normalize = {
    # A
    'á':'a','à':'a','ä':'a','â':'a','ã':'a','ā':'a','ă':'a','å':'a',
    'Á':'A','À':'A','Ä':'A','Â':'A','Ã':'A','Ā':'A','Ă':'A','Å':'A',

    # O — hammasi O'
    'ó':"o'",'ò':"o'",'ö':"o'",'õ':"o'",'ō':"o'",'ô':"o'",'ø':"o'",
    'ȫ':"o'",'ȯ':"o'",'ȱ':"o'",'ǒ':"o'",

    'Ó':"O'",'Ò':"O'",'Ö':"O'",'Õ':"O'",'Ō':"O'",'Ô':"O'",'Ø':"O'",
    'Ȫ':"O'",'Ȯ':"O'",'Ȱ':"O'",'Ǒ':"O'",

    # E
    'é':'e','è':'e','ë':'e','ê':'e','ē':'e','ĕ':'e','ė':'e',
    'É':'E','È':'E','Ë':'E','Ê':'E','Ē':'E','Ĕ':'E','Ė':'E',

    # I
    'í':'i','ì':'i','ï':'i','î':'i','ī':'i',
    'Í':'I','Ì':'I','Ï':'I','Î':'I','Ī':'I',

    # U
    'ú':'u','ù':'u','ü':'u','û':'u','ũ':'u','ū':'u','ů':'u',
    'Ú':'U','Ù':'U','Ü':'U','Û':'U','Ũ':'U','Ū':'U','Ů':'U',

    # G'
    'ğ':"g'",'ǧ':"g'",'ģ':"g'",
    'Ğ':"G'",'Ǧ':"G'",'Ģ':"G'",

    # N'
    'ñ':"n'",'ņ':"n'",'ň':"n'", 
    'Ñ':"N'",'Ņ':"N'",'Ň':"N'",
}


def normalize_latin(text):
    return ''.join(latin_normalize.get(ch, ch) for ch in text)

def normalize_apostrophe(text):
    for a in ["’","ʻ","`","´","ˈ","ʿ","῾","‛","ʼ","‘","ʹ","ˊ"]:
        text = text.replace(a, "'")
    return text


# ===================== LOTIN → KIRIL =====================
def to_cyrillic(text):
    text = normalize_latin(normalize_apostrophe(text))

    # Murakkablar
    pairs = [
        ("o'", "ў"), ("O'", "Ў"),
        ("g'", "ғ"), ("G'", "Ғ"),
        ("sh", "ш"), ("Sh", "Ш"), ("SH", "Ш"),
        ("ch", "ч"), ("Ch", "Ч"), ("CH", "Ч"),
        ("ng", "нг"), ("Ng", "Нг"), ("NG", "НГ"),
        ("yo", "ё"), ("Yo", "Ё"), ("YO", "Ё"),
        ("yu", "ю"), ("Yu", "Ю"), ("YU", "Ю"),
        ("ya", "я"), ("Ya", "Я"), ("YA", "Я"),

        # YE maxsus
        ("ye", "е"), ("Ye", "Е"), ("YE", "Е"),
    ]
    for lat, cyr in pairs:
        text = text.replace(lat, cyr)

    # So‘z boshida E → Э
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

    def fix_E(text):
        text = text.replace("Э", "E").replace("э", "e")
        text = re.sub(r"\bЕ", "Ye", text)
        text = re.sub(r"\bе", "ye", text)
        vowels = "АаЕеЁёИиОоУуЭэЮюЯяЎўҚқҒғҲҳ"
        text = re.sub(rf"([{vowels}])Е", r"\1Ye", text)
        text = re.sub(rf"([{vowels}])е", r"\1ye", text)
        text = text.replace("Е", "e").replace("е", "e")
        return text

    text = fix_E(text)

    mapping = [
        ('қӯ',"qo'"),('Қӯ',"Qo'"),  
        ('ё','yo'),('Ё','Yo'),
        ('ю','yu'),('Ю','Yu'),
        ('я','ya'),('Я','Ya'),
        ('ш','sh'),('Ш','Sh'),
        ('ч','ch'),('Ч','Ch'),
        ('нг','ng'),('Нг','Ng'),('НГ','NG'),
   
        # Bu qatorni tuzatdik
        ('қў',"qo'"),('Қў',"Qo'"),  # avval noto'g'ri ishlardi
   
        ('ў',"o'"),('Ў',"O'"),
        ('ғ',"g'"),('Ғ',"G'"),
        ('қ','q'), ('Қ','Q'),
        ('ҳ','h'), ('Ҳ','H'),
    ]

    for cyr, lat in mapping:
        text = text.replace(cyr, lat)

    chars = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','ж':'j',
        'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m',
        'н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
        'у':'u','ф':'f','х':'x','ц':'s','ъ':"'",'ь':'',
        'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Ж':'J',
        'З':'Z','И':'I','Й':'Y','К':'K','Л':'L','М':'M',
        'Н':'N','О':'O','П':'P','Р':'R','С':'S','Т':'T',
        'У':'U','Ф':'F','Х':'X','Ц':'S','Ъ':"'",'Ь':'',
    }

    return ''.join(chars.get(ch, ch) for ch in text)


# ===================== END TRANSLITERATION =====================

def call_gemini(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.exception("Gemini call failed")
        return f"(Gemini xatosi: {e})"

KEYBOARD = [
    ["Lotin → Kiril", "Kiril → Lotin"],
    ["ChatBot", "Post maker"],
    ["Statistika", "Adminga xabar"],
    ["Ovoz kesuvchi", "Ovozni Musiqaga aylantirish"]
]
REPLY_MARKUP = ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data.setdefault('users', set())
    context.bot_data['users'].add(update.message.from_user.id)
    await update.message.reply_text("🎉 Salom! Quyidagi tugmalardan birini tanlang:", reply_markup=REPLY_MARKUP)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Lotin → Kiril / Kiril → Lotin\n"
        "💬 ChatBot - savol-javob\n"
        "🖋 Post maker - post yaratish\n"
        "📊 Statistika\n"
        "📩 Adminga xabar\n"
        "🎵 Ovoz kesuvchi / Musiqaga aylantirish"
    )

async def handle_button_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.message.from_user.id
    context.bot_data.setdefault('users', set())
    context.bot_data['users'].add(uid)

    modes = {
        "Lotin → Kiril": ('lat2kir', "✏️ Lotincha matn yuboring:"),
        "Kiril → Lotin": ('kir2lat', "✏️ Kirilcha matn yuboring:"),
        "Ovoz kesuvchi": ('voice_cutter', "🎵 Audio yuboring, keyin vaqt yozing (00:10-00:20):"),
        "Ovozni Musiqaga aylantirish": ('voice_to_music', "🎶 Audio yuboring:"),
        "ChatBot": ('chat', "💬 Savolingizni yuboring:"),
        "Post maker": ('post', "🖋 Post mavzusini yuboring:"),
        "Adminga xabar": ('admin_msg', "📩 Xabar matnini yozing:"),
    }
    
    if text in modes:
        context.user_data['mode'] = modes[text][0]
        await update.message.reply_text(modes[text][1])
    elif text == "Statistika":
        total = len(context.bot_data.get('users', set()))
        await update.message.reply_text(f"📊 Foydalanuvchilar: {total}")
    else:
        await update.message.reply_text("❗ Tugmani tanlang:", reply_markup=REPLY_MARKUP)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    text = update.message.text or ""
    uid = update.message.from_user.id

    if not mode:
        await update.message.reply_text("❗ Avval tugmani tanlang:", reply_markup=REPLY_MARKUP)
        return

    if mode == 'lat2kir':
        result = to_cyrillic(text)
        await update.message.reply_text(result)
    
    elif mode == 'kir2lat':
        result = to_latin(text)
        await update.message.reply_text(result)
    
    elif mode == 'chat':
        msg = await update.message.reply_text("💬 Javob yozilmoqda...")
        reply = call_gemini(f"Foydalanuvchi: {text}\nYordamchi:")
        await msg.edit_text(reply)
    
    elif mode == 'post':
        msg = await update.message.reply_text("🖋 Post yaratilmoqda...")
        post = call_gemini(
            f"'{text}' mavzusida professional va qiziqarli post yozing. "
            "Postda 'men shuni qildim, u qildim' kabi misollar bo'lmasin. "
            "Faqat post matni bo'lsin. "
        )
        await msg.edit_text(post)
    
    elif mode == 'voice_wait_time':
        await process_voice_cut(update, context, text)
    
    elif mode == 'admin_msg':
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Javob berish", callback_data=f"reply_{uid}")]])
        await context.bot.send_message(ADMIN_ID, f"📨 Xabar (ID: {uid}):\n\n{text}", reply_markup=markup)
        await update.message.reply_text("✅ Xabaringiz adminga yuborildi!")
        context.user_data['mode'] = None
    
    elif mode == 'reply_user' and uid == ADMIN_ID:
        target = context.user_data.get('reply_to_user')
        if target:
            await context.bot.send_message(target, f"💌 Admin javobi:\n\n{text}")
            await update.message.reply_text("✅ Javob yuborildi!")
            context.user_data['reply_to_user'] = None
            context.user_data['mode'] = None

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    voice = update.message.voice or update.message.audio
    
    if not voice:
        await update.message.reply_text("❗ Audio topilmadi.")
        return
    
    if mode not in ('voice_cutter', 'voice_to_music'):
        await update.message.reply_text("❗ Avval 'Ovoz kesuvchi' yoki 'Musiqaga aylantirish' tugmasini bosing.")
        return

    file = await voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
        await file.download_to_drive(path)

    if mode == 'voice_cutter':
        context.user_data['voice_file'] = path
        context.user_data['mode'] = 'voice_wait_time'
        await update.message.reply_text("✅ Audio yuklandi!\nEndi kesish vaqtini yozing (masalan: 00:10-00:20):")
    
    elif mode == 'voice_to_music':
        msg = await update.message.reply_text("🎵 Ishlanmoqda...")
        try:
            audio = AudioSegment.from_file(path)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f2:
                out_path = f2.name
                audio.export(out_path, format="mp3")
            await msg.delete()
            with open(out_path, "rb") as audio_file:
                await update.message.reply_audio(audio_file, caption="🎶 Tayyor! ✅")
            os.remove(out_path)
        except Exception as e:
            await msg.edit_text(f"❌ Xatolik: {e}")
        finally:
            os.remove(path)
            context.user_data['mode'] = None

async def process_voice_cut(update: Update, context: ContextTypes.DEFAULT_TYPE, time_text: str):
    voice_file = context.user_data.get('voice_file')
    if not voice_file:
        await update.message.reply_text("❗ Avval audio yuboring.")
        context.user_data['mode'] = 'voice_cutter'
        return
    
    match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", time_text.strip())
    if not match:
        await update.message.reply_text("❗ Format xato! Misol: 00:10-00:20")
        return
    
    s_min, s_sec, e_min, e_sec = map(int, match.groups())
    start_ms = (s_min * 60 + s_sec) * 1000
    end_ms = (e_min * 60 + e_sec) * 1000
    
    if start_ms >= end_ms:
        await update.message.reply_text("❗ Boshlanish vaqti tugash vaqtidan katta bo'lmasligi kerak!")
        return
    
    msg = await update.message.reply_text("🎵 Kesilmoqda...")
    try:
        audio = AudioSegment.from_file(voice_file)
        if end_ms > len(audio):
            await msg.edit_text(f"❗ Audio uzunligi: {len(audio)//1000} soniya. Vaqtni qayta kiriting.")
            return
        
        cut_audio = audio[start_ms:end_ms]
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            cut_path = f.name
            cut_audio.export(cut_path, format="mp3")
        
        await msg.delete()
        with open(cut_path, "rb") as audio_file:
            await update.message.reply_audio(audio_file, caption="✅ Audio kesildi!")
        os.remove(cut_path)
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists(voice_file):
            os.remove(voice_file)
        context.user_data['voice_file'] = None
        context.user_data['mode'] = None

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("reply_") and query.from_user.id == ADMIN_ID:
        user_id = int(query.data.split("_")[1])
        context.user_data['reply_to_user'] = user_id
        context.user_data['mode'] = 'reply_user'
        await query.message.reply_text(f"✏️ Foydalanuvchi {user_id} ga javob yozing:")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Eski fayllarni tozalash
    voice_file = context.user_data.get('voice_file')
    if voice_file and os.path.exists(voice_file):
        os.remove(voice_file)
    context.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=REPLY_MARKUP)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handlerlar tartibi muhim!
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Tugmalar
    button_filter = filters.TEXT & filters.Regex(
        r"^(Lotin → Kiril|Kiril → Lotin|ChatBot|Post maker|Statistika|Adminga xabar|Ovoz kesuvchi|Ovozni Musiqaga aylantirish)$"
    )
    app.add_handler(MessageHandler(button_filter, handle_button_choice))
    
    # Audio
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    
    # Callback (admin javob)
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Matn (eng oxirida)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    logger.info("Bot ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
