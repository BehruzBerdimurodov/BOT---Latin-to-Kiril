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
    for a in ["'","ʻ","`","´","ˈ","ʿ","῾","‛","ʼ","'","ʹ","ˊ"]:
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
    """Kirildan lotinga o'girish - xatolar tuzatildi"""
    
    def fix_E(text):
        """E harfi uchun maxsus qoidalar"""
        # Э → E
        text = text.replace("Э", "E").replace("э", "e")
        
        # So'z boshida Е → Ye
        text = re.sub(r"\bЕ", "Ye", text)
        text = re.sub(r"\bе", "ye", text)
        
        # Unli harflardan keyin Е → ye
        vowels = "АаЕеЁёИиОоУуЭэЮюЯяЎўҚқҒғҲҳ"
        text = re.sub(rf"([{vowels}])Е", r"\1ye", text)
        text = re.sub(rf"([{vowels}])е", r"\1ye", text)
        
        # Qolgan Е → e
        text = text.replace("Е", "e").replace("е", "e")
        return text
    
    # Avval E harfini qayta ishlash
    text = fix_E(text)
    
    # Murakkab kombinatsiyalar (uzundan qisqaga qarab)
    mapping = [
        # 3 harfli kombinatsiyalar
        ('қӯў',"qo'"),('Қӯў',"Qo'"),
        ('нгҳ','ngh'),('Нгҳ','Ngh'),
        
        # 2 harfli kombinatsiyalar
        ('қў',"qo'"),('Қў',"Qo'"),
        ('қӯ',"qo'"),('Қӯ',"Qo'"),
        
        # Ўнлилар ва товушлар
        ('ё','yo'),('Ё','Yo'),
        ('ю','yu'),('Ю','Yu'),
        ('я','ya'),('Я','Ya'),
        ('ш','sh'),('Ш','Sh'),
        ('ч','ch'),('Ч','Ch'),
        ('нг','ng'),('Нг','Ng'),('НГ','NG'),
        
        # O' va G'
        ('ў',"o'"),('Ў',"O'"),
        ('ғ',"g'"),('Ғ',"G'"),
        
        # Maxsus harflar
        ('қ','q'), ('Қ','Q'),
        ('ҳ','h'), ('Ҳ','H'),
        
        # Rus harflari (agar matnda bo'lsa)
        ('ж','j'), ('Ж','J'),  # ж → j (o'zbek tilida)
        ('х','x'), ('Х','X'),  # х → x
    ]
    
    for cyr, lat in mapping:
        text = text.replace(cyr, lat)
    
    # Bitta harfli konversiya
    chars = {
        'а':'a','б':'b','в':'v','г':'g','д':'d',
        'ё':'yo','з':'z','и':'i','й':'y','к':'k',
        'л':'l','м':'m','н':'n','о':'o','п':'p',
        'р':'r','с':'s','т':'t','у':'u','ф':'f',
        'ц':'ts','щ':'shch','ъ':"'",'ь':'','ы':'i',
        'э':'e','ю':'yu','я':'ya',
        
        'А':'A','Б':'B','В':'V','Г':'G','Д':'D',
        'Ё':'Yo','З':'Z','И':'I','Й':'Y','К':'K',
        'Л':'L','М':'M','Н':'N','О':'O','П':'P',
        'Р':'R','С':'S','Т':'T','У':'U','Ф':'F',
        'Ц':'Ts','Щ':'Shch','Ъ':"'",'Ь':'','Ы':'I',
        'Э':'E','Ю':'Yu','Я':'Ya'
    }
    
    return ''.join(chars.get(ch, ch) for ch in text)


# ===================== END TRANSLITERATION =====================

def call_gemini(prompt: str) -> str:
    """Gemini AI chaqirish funksiyasi"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.exception("Gemini call failed")
        return f"(Gemini xatosi: {e})"

# Asosiy klaviatura
KEYBOARD = [
    ["📝 Lotin → Kiril", "📝 Kiril → Lotin"],
    ["💬 ChatBot", "🎵 Musiqa tahrirlash"],
    ["📊 Statistika", "📩 Adminga xabar"],
    ["✂️ Ovoz kesuvchi", "🎶 Ovozni Musiqaga aylantirish"]
]
REPLY_MARKUP = ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start buyrug'i - bot ishga tushganda"""
    context.bot_data.setdefault('users', set())
    user_id = update.message.from_user.id
    context.bot_data['users'].add(user_id)
    
    welcome_message = (
        "🎉 <b>Assalomu alaykum!</b>\n\n"
        "🤖 Men ko'p funksiyali Telegram botman!\n\n"
        "📝 <b>Nima qila olaman:</b>\n"
        "• Lotin ⇄ Kiril o'girish\n"
        "• ChatBot - savol-javob\n"
        "• Musiqa tahrirlash (title, author)\n"
        "• Ovoz kesish va qayta ishlash\n"
        "• Statistika va admin bilan aloqa\n\n"
        "👇 Quyidagi tugmalardan birini tanlang:"
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=REPLY_MARKUP,
        parse_mode='HTML'
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam buyrug'i"""
    help_text = (
        "📚 <b>Bot funksiyalari:</b>\n\n"
        "📝 <b>Lotin ⇄ Kiril</b>\n"
        "Matnlarni transliteratsiya qilish\n\n"
        "💬 <b>ChatBot</b>\n"
        "AI bilan suhbatlashing\n\n"
        "🎵 <b>Musiqa tahrirlash</b>\n"
        "MP3 faylning title va authorini o'zgartiring\n\n"
        "✂️ <b>Ovoz kesuvchi</b>\n"
        "Audioni vaqt bo'yicha kesing\n\n"
        "🎶 <b>Musiqaga aylantirish</b>\n"
        "Ovozni MP3 formatga o'tkazing\n\n"
        "📊 <b>Statistika</b>\n"
        "Bot foydalanuvchilari soni\n\n"
        "📩 <b>Adminga xabar</b>\n"
        "Admin bilan bog'laning\n\n"
        "⚙️ <b>Buyruqlar:</b>\n"
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n"
        "/cancel - Amalni bekor qilish\n"
        "/stats - Statistika"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistika buyrug'i"""
    total = len(context.bot_data.get('users', set()))
    await update.message.reply_text(
        f"📊 <b>Bot statistikasi</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total}</b> ta",
        parse_mode='HTML'
    )

async def handle_button_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalar bosish"""
    text = update.message.text.strip()
    uid = update.message.from_user.id
    context.bot_data.setdefault('users', set())
    context.bot_data['users'].add(uid)

    modes = {
        "📝 Lotin → Kiril": ('lat2kir', "✏️ Lotincha matn yuboring:", "📝"),
        "📝 Kiril → Lotin": ('kir2lat', "✏️ Kirilcha matn yuboring:", "📝"),
        "✂️ Ovoz kesuvchi": ('voice_cutter', "🎵 Audio yuboring, keyin vaqt yozing (00:10-00:20):", "✂️"),
        "🎶 Ovozni Musiqaga aylantirish": ('voice_to_music', "🎶 Audio yuboring:", "🎶"),
        "💬 ChatBot": ('chat', "💬 Savolingizni yuboring:", "💬"),
        "🎵 Musiqa tahrirlash": ('music_edit', "🎵 Musiqa faylini yuboring (MP3):", "🎵"),
        "📩 Adminga xabar": ('admin_msg', "📩 Xabar matnini yozing:", "📩"),
    }
    
    if text in modes:
        mode_data = modes[text]
        context.user_data['mode'] = mode_data[0]
        emoji = mode_data[2] if len(mode_data) > 2 else ""
        await update.message.reply_sticker(
            "CAACAgIAAxkBAAEBVCJnYXZkZGVmYWNlAAECAwQFBgcICQoL"  # Sticker ID
        ) if emoji else None
        await update.message.reply_text(mode_data[1])
    elif text == "📊 Statistika":
        total = len(context.bot_data.get('users', set()))
        await update.message.reply_text(
            f"📊 <b>Foydalanuvchilar soni:</b> {total} ta",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text("❗ Tugmani tanlang:", reply_markup=REPLY_MARKUP)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matn xabarlarni qayta ishlash"""
    mode = context.user_data.get('mode')
    text = update.message.text or ""
    uid = update.message.from_user.id

    if not mode:
        await update.message.reply_text("❗ Avval tugmani tanlang:", reply_markup=REPLY_MARKUP)
        return

    if mode == 'lat2kir':
        result = to_cyrillic(text)
        await update.message.reply_text(f"✅ <b>Natija:</b>\n\n{result}", parse_mode='HTML')
    
    elif mode == 'kir2lat':
        result = to_latin(text)
        await update.message.reply_text(f"✅ <b>Natija:</b>\n\n{result}", parse_mode='HTML')
    
    elif mode == 'chat':
        msg = await update.message.reply_text("💬 Javob yozilmoqda...")
        reply = call_gemini(f"Foydalanuvchi: {text}\nYordamchi:")
        await msg.edit_text(f"🤖 <b>Javob:</b>\n\n{reply}", parse_mode='HTML')
    
    elif mode == 'voice_wait_time':
        await process_voice_cut(update, context, text)
    
    elif mode == 'music_wait_title':
        context.user_data['music_title'] = text
        context.user_data['mode'] = 'music_wait_author'
        await update.message.reply_text("👤 Endi <b>Author</b> (Ijrochi) nomini kiriting:", parse_mode='HTML')
    
    elif mode == 'music_wait_author':
        context.user_data['music_author'] = text
        await process_music_edit(update, context)
    
    elif mode == 'admin_msg':
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Javob berish", callback_data=f"reply_{uid}")]])
        await context.bot.send_message(
            ADMIN_ID,
            f"📨 <b>Xabar (ID: {uid})</b>\n\n{text}",
            reply_markup=markup,
            parse_mode='HTML'
        )
        await update.message.reply_text("✅ Xabaringiz adminga yuborildi! 📬")
        context.user_data['mode'] = None
    
    elif mode == 'reply_user' and uid == ADMIN_ID:
        target = context.user_data.get('reply_to_user')
        if target:
            await context.bot.send_message(
                target,
                f"💌 <b>Admin javobi:</b>\n\n{text}",
                parse_mode='HTML'
            )
            await update.message.reply_text("✅ Javob yuborildi! 📤")
            context.user_data['reply_to_user'] = None
            context.user_data['mode'] = None

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio fayllarni qayta ishlash"""
    mode = context.user_data.get('mode')
    audio = update.message.audio or update.message.voice
    
    if not audio:
        await update.message.reply_text("❗ Audio topilmadi.")
        return
    
    if mode == 'music_edit':
        file = await audio.get_file()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
            await file.download_to_drive(path)
        
        context.user_data['music_file'] = path
        context.user_data['mode'] = 'music_wait_title'
        await update.message.reply_text("✅ Musiqa yuklandi! 🎵\n\n📝 Endi <b>Title</b> (Qo'shiq nomi) kiriting:", parse_mode='HTML')
    
    elif mode in ('voice_cutter', 'voice_to_music'):
        await handle_voice(update, context)
    
    else:
        await update.message.reply_text(
            "❗ Avval tegishli tugmani bosing:\n"
            "• 🎵 Musiqa tahrirlash\n"
            "• ✂️ Ovoz kesuvchi\n"
            "• 🎶 Musiqaga aylantirish",
            reply_markup=REPLY_MARKUP
        )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovoz xabarlarini qayta ishlash"""
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
        await update.message.reply_text(
            "✅ Audio yuklandi! ⏰\n\n"
            "Kesish vaqtini kiriting:\n"
            "<b>Format:</b> 00:10-00:20",
            parse_mode='HTML'
        )
    
    elif mode == 'voice_to_music':
        msg = await update.message.reply_text("🎵 Qayta ishlanmoqda...")
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

async def process_music_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqa metadata tahrirlash"""
    music_file = context.user_data.get('music_file')
    title = context.user_data.get('music_title', 'Unknown Title')
    author = context.user_data.get('music_author', 'Unknown Artist')
    
    if not music_file:
        await update.message.reply_text("❗ Avval musiqa faylini yuboring.")
        context.user_data['mode'] = 'music_edit'
        return
    
    msg = await update.message.reply_text("🎵 Metadata o'zgartirilmoqda...")
    
    try:
        # MP3 faylni yaratish va metadata qo'shish
        audio = AudioSegment.from_file(music_file)
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            output_path = f.name
            audio.export(output_path, format="mp3")
        
        # ID3 tag qo'shish
        try:
            audio_file = MP3(output_path, ID3=ID3)
            audio_file.add_tags()
        except:
            audio_file = MP3(output_path)
        
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
                caption=f"✅ <b>Tayyor!</b>\n\n🎵 <b>Title:</b> {title}\n👤 <b>Author:</b> {author}",
                parse_mode='HTML'
            )
        
        os.remove(output_path)
        
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
    
    finally:
        if os.path.exists(music_file):
            os.remove(music_file)
        context.user_data['music_file'] = None
        context.user_data['music_title'] = None
        context.user_data['music_author'] = None
        context.user_data['mode'] = None

async def process_voice_cut(update: Update, context: ContextTypes.DEFAULT_TYPE, time_text: str):
    """Ovozni kesish"""
    voice_file = context.user_data.get('voice_file')
    if not voice_file:
        await update.message.reply_text("❗ Avval audio yuboring.")
        context.user_data['mode'] = 'voice_cutter'
        return
    
    match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", time_text.strip())
    if not match:
        await update.message.reply_text(
            "❗ Format xato!\n\n<b>To'g'ri format:</b> 00:10-00:20",
            parse_mode='HTML'
        )
        return
    
    s_min, s_sec, e_min, e_sec = map(int, match.groups())
    start_ms = (s_min * 60 + s_sec) * 1000
    end_ms = (e_min * 60 + e_sec) * 1000
    
    if start_ms >= end_ms:
        await update.message.reply_text("❗ Boshlanish vaqti tugash vaqtidan kichik bo'lishi kerak!")
        return
    
    msg = await update.message.reply_text("✂️ Kesilmoqda...")
    try:
        audio = AudioSegment.from_file(voice_file)
        if end_ms > len(audio):
            duration = len(audio) // 1000
            await msg.edit_text(
                f"❗ Audio uzunligi: <b>{duration}</b> soniya.\n\n"
                f"Vaqtni qayta kiriting.",
                parse_mode='HTML'
            )
            return
        
        cut_audio = audio[start_ms:end_ms]
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            cut_path = f.name
            cut_audio.export(cut_path, format="mp3")
        
        await msg.delete()
        with open(cut_path, "rb") as audio_file:
            await update.message.reply_audio(audio_file, caption="✅ Audio kesildi! ✂️")
        os.remove(cut_path)
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists(voice_file):
            os.remove(voice_file)
        context.user_data['voice_file'] = None
        context.user_data['mode'] = None

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline tugmalar callback"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("reply_") and query.from_user.id == ADMIN_ID:
        user_id = int(query.data.split("_")[1])
        context.user_data['reply_to_user'] = user_id
        context.user_data['mode'] = 'reply_user'
        await query.message.reply_text(
            f"✏️ Foydalanuvchi <b>{user_id}</b> ga javob yozing:",
            parse_mode='HTML'
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Amalni bekor qilish"""
    voice_file = context.user_data.get('voice_file')
    music_file = context.user_data.get('music_file')
    
    # Vaqtinchalik fayllarni tozalash
    if voice_file and os.path.exists(voice_file):
        os.remove(voice_file)
    if music_file and os.path.exists(music_file):
        os.remove(music_file)
    
    context.user_data.clear()
    await update.message.reply_text(
        "❌ <b>Amal bekor qilindi!</b>\n\n"
        "Bosh menyuga qaytdingiz. 🏠",
        reply_markup=REPLY_MARKUP,
        parse_mode='HTML'
    )

def main():
    """Botni ishga tushirish"""
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Buyruqlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("stats", stats_cmd))
    
    # Tugmalar
    button_filter = filters.TEXT & filters.Regex(
        r"^(📝 Lotin → Kiril|📝 Kiril → Lotin|💬 ChatBot|🎵 Musiqa tahrirlash|📊 Statistika|📩 Adminga xabar|✂️ Ovoz kesuvchi|🎶 Ovozni Musiqaga aylantirish)$"
    )
    app.add_handler(MessageHandler(button_filter, handle_button_choice))
    
    # Audio va ovoz
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # Callback (admin javob)
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Matn (eng oxirida)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    logger.info("🤖 Bot muvaffaqiyatli ishga tushdi!")
    logger.info("📊 Foydalanish uchun /start buyrug'ini yuboring")
    app.run_polling()

if __name__ == "__main__":
    main()
    
