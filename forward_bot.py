import telebot
import os
import time
import urllib.request
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telebot import types

# --- KONFIGURATSIYA ---
TOKEN = "8417577678:AAH6RXAvwsaEuhKSCq6AsC83tG5QBtd0aJk"
SOURCE_CHANNEL = "@TOSHKENTANGRENTAKSI"
DESTINATION_CHANNEL = "@Uski_kur"  # Zakazlar va forwardlar shu yerga tushadi

bot = telebot.TeleBot(TOKEN)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Foydalanuvchi holatlarini saqlash
user_states = {}

# --- KEYBOARDS ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🚖 Taksi Chaqirish"))
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ Bekor qilish"))
    return markup

# --- HELPER FUNCTIONS ---
def get_sender_info(message):
    """Xabar yuborgan shaxs haqida ma'lumot tayyorlaydi (profil linki bilan)"""
    user = message.from_user
    if not user:
        return "📢 <b>Kanal xabari</b>\n"
    
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Noma'lum"
    # Profilga havola: <a href="tg://user?id=ID">Ism</a>
    profile_link = f'<a href="tg://user?id={user.id}">{name}</a>'
    
    info = f"👤 <b>Foydalanuvchi:</b> {profile_link}\n"
    if user.username:
        info += f"🔗 <b>Username:</b> @{user.username}\n"
    info += f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
    return info

# --- FORWARD LOGIC ---
def forward_logic(message):
    try:
        current_chat = f"@{message.chat.username}" if message.chat.username else str(message.chat.id)
        if current_chat.lower() != SOURCE_CHANNEL.lower():
            return

        header = get_sender_info(message)
        separator = "─" * 15 + "\n"
        full_header = header + separator

        if message.content_type == 'text':
            bot.send_message(DESTINATION_CHANNEL, full_header + message.text, parse_mode='HTML')
        elif message.content_type == 'photo':
            bot.send_photo(DESTINATION_CHANNEL, message.photo[-1].file_id, caption=full_header + (message.caption or ""), parse_mode='HTML')
        elif message.content_type == 'video':
            bot.send_video(DESTINATION_CHANNEL, message.video.file_id, caption=full_header + (message.caption or ""), parse_mode='HTML')
        elif message.content_type == 'voice':
            bot.send_voice(DESTINATION_CHANNEL, message.voice.file_id, caption=full_header)
        elif message.content_type == 'audio':
            bot.send_audio(DESTINATION_CHANNEL, message.audio.file_id, caption=full_header + (message.caption or ""), parse_mode='HTML')
        elif message.content_type == 'document':
            bot.send_document(DESTINATION_CHANNEL, message.document.file_id, caption=full_header + (message.caption or ""), parse_mode='HTML')
        
        logger.info(f"✅ Xabar ko'chirildi: {current_chat}")

        # --- Xabarni o'chirish logikasi ---
        # Bot bu kanalda Admin bo'lishi va 'Delete messages' ruxsati bo'lishi shart
        try:
            bot.delete_message(message.chat.id, message.message_id)
            logger.info(f"🗑 Xabar manba kanaldan o'chirildi: {message.message_id}")
        except Exception as del_e:
            logger.warning(f"⚠️ Xabarni o'chirishda xatolik (Ruxsat yoki boshqa muammo): {del_e}")

    except Exception as e:
        logger.error(f"❌ Forward xatosi: {e}")

# --- TAXI BOOKING FLOW ---
@bot.message_handler(func=lambda m: m.text == "🚖 Taksi Chaqirish")
def taxi_start(message):
    user_id = message.from_user.id
    user_states[user_id] = {'step': 'WAIT_NAME', 'data': {}}
    bot.send_message(user_id, "🚖 <b>Taksi zakaz qilish boshlandi.</b>\n\nIsmingizni kiriting:", parse_mode='HTML', reply_markup=get_cancel_keyboard())

@bot.message_handler(func=lambda m: m.text == "❌ Bekor qilish")
def cancel_booking(message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    bot.send_message(user_id, "❌ Zakaz bekor qilindi.", reply_markup=get_main_keyboard())

def handle_taxi_steps(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state: return False

    step = state['step']
    
    try:
        if step == 'WAIT_NAME':
            state['data']['name'] = message.text
            state['step'] = 'WAIT_PHONE'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(types.KeyboardButton("📞 Telefon yuborish", request_contact=True))
            markup.add(types.KeyboardButton("❌ Bekor qilish"))
            bot.send_message(user_id, "Raxmat. Endi telefon raqamingizni yuboring:", reply_markup=markup)
            return True

        elif step == 'WAIT_PHONE':
            if message.content_type == 'contact':
                state['data']['phone'] = message.contact.phone_number
            else:
                state['data']['phone'] = message.text
            
            state['step'] = 'WAIT_DEST'
            bot.send_message(user_id, "Qayerga borasiz? (Manzilni yozing):", reply_markup=get_cancel_keyboard())
            return True

        elif step == 'WAIT_DEST':
            state['data']['dest'] = message.text
            state['step'] = 'WAIT_LOC'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(types.KeyboardButton("📍 Lokatsiyani yuborish", request_location=True))
            markup.add(types.KeyboardButton("❌ Bekor qilish"))
            bot.send_message(user_id, "Lokatsiyangizni yuboring (tugmani bosing):", reply_markup=markup)
            return True

        elif step == 'WAIT_LOC':
            if message.content_type == 'location':
                data = state['data']
                order_text = (
                    f"🚖 <b>YANGI TAKSI ZAKAZI!</b>\n\n"
                    f"👤 <b>Ism:</b> {data['name']}\n"
                    f"📞 <b>Tel:</b> {data['phone']}\n"
                    f"📍 <b>Manzil:</b> {data['dest']}\n"
                    f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"🔗 <b>Username:</b> @{message.from_user.username or 'yoq'}"
                )
                
                # Guruhga yuborish
                bot.send_message(DESTINATION_CHANNEL, order_text, parse_mode='HTML')
                bot.send_location(DESTINATION_CHANNEL, message.location.latitude, message.location.longitude)
                
                # Foydalanuvchiga tasdiqlash
                bot.send_message(user_id, "✅ <b>Zakazingiz qabul qilindi!</b>\nTez orada haydovchilar bog'lanadi.", parse_mode='HTML', reply_markup=get_main_keyboard())
                
                logger.info(f"✅ Yangi zakaz: {user_id}")
                del user_states[user_id]
                return True
            else:
                bot.send_message(user_id, "Iltimos, lokatsiyani yuborish tugmasini bosing yoki bekor qiling.", reply_markup=get_cancel_keyboard())
                return True
    except Exception as e:
        logger.error(f"Booking flow error: {e}")
        bot.send_message(user_id, "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.", reply_markup=get_main_keyboard())
        if user_id in user_states: del user_states[user_id]
        return True
        
    return False

# --- HANDLERLAR ---
@bot.message_handler(commands=['start'])
def welcome(message):
    user_id = message.from_user.id
    if user_id in user_states: del user_states[user_id]
    bot.send_message(message.chat.id, "✅ <b>Bot ishlamoqda!</b>\n\nTaksi chaqirish uchun tugmani bosing.", parse_mode='HTML', reply_markup=get_main_keyboard())

@bot.channel_post_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice'])
def channel_msg(message):
    forward_logic(message)

@bot.message_handler(content_types=['text', 'contact', 'location'])
def handle_all_messages(message):
    # Taksi booking jarayonini tekshirish
    if handle_taxi_steps(message):
        return
    
    # Kanal forward logikasi (agar SOURCE_CHANNEL dan kelsa)
    forward_logic(message)

# --- RENDER SERVER & KEEP AWAKE ---
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
    def log_message(self, format, *args): pass

def keep_awake():
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if not url:
        logger.warning("⚠️ RENDER_EXTERNAL_URL topilmadi.")
        return
    while True:
        try:
            time.sleep(600)
            urllib.request.urlopen(url).read()
            logger.info(f"⏰ Self-ping OK: {time.ctime()}")
        except Exception as e:
            logger.error(f"❌ Self-ping error: {e}")

if __name__ == "__main__":
    if os.environ.get('PORT'):
        port = int(os.environ.get('PORT', 10000))
        Thread(target=lambda: HTTPServer(('0.0.0.0', port), HealthCheck).serve_forever(), daemon=True).start()
    
    if os.environ.get('RENDER_EXTERNAL_URL'):
        Thread(target=keep_awake, daemon=True).start()
        
    logger.info("🤖 Bot ishga tushdi...")
    bot.infinity_polling()
