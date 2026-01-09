import telebot
import os
import time
import urllib.request
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telebot import types

# --- KONFIGURATSIYA ---
TOKEN = "8417577678:AAH6RXAvwsaEuhKSCq6AsC83tG5QBtd0aJk"
SOURCE_CHANNEL = "@TOSHKENTANGRENTAKSI"
DESTINATION_CHANNEL = "@Uski_kur"

bot = telebot.TeleBot(TOKEN)

# Foydalanuvchi holatlarini saqlash (Taksi zakaz qilish uchun)
user_states = {}

# --- HELPER FUNCTIONS ---
def get_sender_info(message):
    user = message.from_user
    if not user:
        return "📢 <b>Kanal xabari</b>\n"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Noma'lum"
    info = f"👤 <b>Foydalanuvchi:</b> {name}\n"
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
        else:
            bot.send_message(DESTINATION_CHANNEL, full_header + f"📎 <b>Xabar turi:</b> {message.content_type}")
        print(f"✅ Ko'chirildi: {current_chat}")
    except Exception as e:
        print(f"❌ Forward xatosi: {e}")

# --- TAXI BOOKING FLOW ---
@bot.message_handler(func=lambda m: m.text == "🚖 Taksi Chaqirish")
def taxi_start(message):
    user_id = message.from_user.id
    user_states[user_id] = {'step': 'WAIT_NAME', 'data': {}}
    bot.send_message(user_id, "🚖 <b>Taksi zakaz qilish boshlandi.</b>\n\nIsmingizni kiriting:", parse_mode='HTML', reply_markup=types.ReplyKeyboardRemove())

def handle_taxi_steps(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state: return False

    step = state['step']
    
    if step == 'WAIT_NAME':
        state['data']['name'] = message.text
        state['step'] = 'WAIT_PHONE'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📞 Telefon yuborish", request_contact=True))
        bot.send_message(user_id, "Telefon raqamingizni yuboring:", reply_markup=markup)
        return True

    elif step == 'WAIT_PHONE':
        state['data']['phone'] = message.contact.phone_number if message.content_type == 'contact' else message.text
        state['step'] = 'WAIT_DEST'
        bot.send_message(user_id, "Qayerga borasiz?", reply_markup=types.ReplyKeyboardRemove())
        return True

    elif step == 'WAIT_DEST':
        state['data']['dest'] = message.text
        state['step'] = 'WAIT_LOC'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📍 Lokatsiyani yuborish", request_location=True))
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
                f"🆔 <b>ID:</b> {user_id}"
            )
            bot.send_message(DESTINATION_CHANNEL, order_text, parse_mode='HTML')
            bot.send_location(DESTINATION_CHANNEL, message.location.latitude, message.location.longitude)
            bot.send_message(user_id, "✅ <b>Zakazingiz qabul qilindi!</b>", parse_mode='HTML', reply_markup=get_main_keyboard())
            del user_states[user_id]
            return True
    return False

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🚖 Taksi Chaqirish"))
    return markup

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(message.chat.id, "✅ <b>Bot ishlamoqda!</b>", parse_mode='HTML', reply_markup=get_main_keyboard())

@bot.channel_post_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice'])
def channel_msg(message):
    forward_logic(message)

@bot.message_handler(content_types=['text', 'contact', 'location'])
def group_msg(message):
    if not handle_taxi_steps(message):
        forward_logic(message)

# --- RENDER SERVER & KEEP AWAKE ---
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
    def log_message(self, format, *args): pass

def keep_awake():
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if not url: return
    while True:
        try:
            time.sleep(600)
            urllib.request.urlopen(url).read()
            print(f"⏰ Ping OK: {time.ctime()}")
        except: pass

if __name__ == "__main__":
    if os.environ.get('PORT'):
        Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), HealthCheck).serve_forever(), daemon=True).start()
    if os.environ.get('RENDER_EXTERNAL_URL'):
        Thread(target=keep_awake, daemon=True).start()
    print("🤖 Bot tayyor...")
    bot.infinity_polling()
