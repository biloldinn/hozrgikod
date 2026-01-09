import telebot
from telebot import types
import database
import time

# --- Configuration ---
API_TOKEN = '8417577678:AAH6RXAvwsaEuhKSCq6AsC83tG5QBtd0aJk'
ADMIN_ID = 6762465157

# Payment
PAYMENT_CARD = "9860356634199596"
PAYMENT_NAME = "Biloliddin Turgunboyev"
PAYMENT_AMOUNT = "15 000 so'm"

bot = telebot.TeleBot(API_TOKEN)

# Simple State System for Taxi Order and Channel Setup
user_data = {} 

def is_subscribed(user_id):
    if user_id == ADMIN_ID:
        return True
    return database.check_subscription(user_id)

# --- Start & Menu ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    
    database.add_user(user_id, username, full_name)
    
    if is_subscribed(user_id):
        show_main_menu(user_id)
    else:
        send_payment_info(user_id)

def show_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_taxi = types.KeyboardButton("🚖 Taksi Chaqirish")
    btn_channels = types.KeyboardButton("📡 Kanallarni Sozlash")
    btn_cabinet = types.KeyboardButton("👤 Kabinet")
    markup.add(btn_taxi, btn_channels)
    markup.add(btn_cabinet)
    
    bot.send_message(user_id, "Asosiy menyu:", reply_markup=markup)

def send_payment_info(user_id):
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Chek yuborish", callback_data="send_receipt")
    markup.add(btn)
    
    msg = (f"🚧 **Botdan foydalanish pullik!**\n\n"
           f"💰 Narxi: {PAYMENT_AMOUNT} (20 kun)\n"
           f"💳 Karta: `{PAYMENT_CARD}`\n"
           f"👤 Egasi: {PAYMENT_NAME}\n\n"
           "To'lov qilgach, chekni rasm qilib yuboring.")
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=markup)

# --- Payment Handling ---
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    # Skip if user is in a state (taxi ordering, etc)
    if user_data.get(user_id):
        return
        
    if is_subscribed(user_id):
        return
    
    # Payment receipt logic
    file_id = message.photo[-1].file_id
    payment_id = database.add_payment_request(user_id, file_id)
    bot.send_message(user_id, "Chek qabul qilindi. Admin tasdiqlashini kuting... ⏳")
    
    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_approve_{payment_id}_{user_id}")
    btn_reject = types.InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_reject_{payment_id}_{user_id}")
    markup.add(btn_approve, btn_reject)
    
    caption = f"📩 Yangi to'lov!\nUser: {message.from_user.full_name}\nID: {user_id}"
    bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def payment_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    data = call.data.split('_')
    action = data[1]
    payment_id = int(data[2])
    target_user_id = int(data[3])
    
    if action == 'approve':
        database.update_payment_status(payment_id, 'approved')
        database.update_subscription(target_user_id, days=20)
        bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, 
                                caption=call.message.caption + "\n✅ TASDIQLANDI")
        bot.send_message(target_user_id, "✅ To'lov tasdiqlandi! Botdan foydalanishingiz mumkin.")
        show_main_menu(target_user_id)
    elif action == 'reject':
        database.update_payment_status(payment_id, 'rejected')
        bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, 
                                caption=call.message.caption + "\n❌ RAD ETILDI")
        bot.send_message(target_user_id, "❌ To'lov rad etildi.")

# --- Channel Setup ---
@bot.message_handler(func=lambda message: message.text == "📡 Kanallarni Sozlash")
def setup_channels_menu(message):
    user_id = message.from_user.id
    if not is_subscribed(user_id):
        send_payment_info(user_id)
        return
    
    user_data[user_id] = {'step': 'source_channel'}
    msg = ("📡 **Kanallarni Sozlash**\n\n"
           "Qaysi kanaldan ma'lumot olmoqchisiz?\n"
           "Kanal username yoki ID sini yuboring.\n\n"
           "Masalan: `@TOSHKENTANGRENTAKSI` yoki `-1001234567890`\n\n"
           "⚠️ Bot o'sha kanalda ADMIN bo'lishi shart!")
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('step') == 'source_channel')
def set_source_channel(message):
    user_id = message.from_user.id
    source = message.text.strip()
    
    user_data[user_id]['source'] = source
    user_data[user_id]['step'] = 'dest_channel'
    
    msg = ("✅ Manba kanal saqlandi!\n\n"
           "Endi qaysi kanalga/guruhga forward qilmoqchisiz?\n"
           "Kanal/guruh username yoki ID sini yuboring.\n\n"
           "Masalan: `@Angren_Toshkent_Taksi_pochta_a`")
    bot.send_message(user_id, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('step') == 'dest_channel')
def set_dest_channel(message):
    user_id = message.from_user.id
    dest = message.text.strip()
    
    source = user_data[user_id]['source']
    
    # Save to database
    database.add_channel_config(user_id, source, dest)
    
    user_data[user_id] = None
    
    msg = (f"✅ **Sozlamalar saqlandi!**\n\n"
           f"📥 Manba: `{source}`\n"
           f"📤 Manzil: `{dest}`\n\n"
           f"Endi {source} ga yozilgan xabarlar avtomatik {dest} ga forward bo'ladi!")
    bot.send_message(user_id, msg, parse_mode='Markdown')
    show_main_menu(user_id)

# --- Taxi Order Wizard ---
@bot.message_handler(func=lambda message: message.text == "🚖 Taksi Chaqirish")
def taxi_start(message):
    user_id = message.from_user.id
    if not is_subscribed(user_id):
        send_payment_info(user_id)
        return
    
    user_data[user_id] = {'step': 'taxi_name'}
    bot.send_message(user_id, "Ismingizni kiriting:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('step') == 'taxi_name')
def taxi_name(message):
    user_id = message.from_user.id
    name = message.text
    user_data[user_id]['name'] = name
    user_data[user_id]['step'] = 'taxi_phone'
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True))
    bot.send_message(user_id, "Telefon raqamingizni yuboring:", reply_markup=markup)

@bot.message_handler(content_types=['contact'])
def taxi_phone_contact(message):
    user_id = message.from_user.id
    if user_data.get(user_id, {}).get('step') == 'taxi_phone':
        phone = message.contact.phone_number
        user_data[user_id]['phone'] = phone
        ask_route(user_id)

@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('step') == 'taxi_phone')
def taxi_phone_text(message):
    user_id = message.from_user.id
    phone = message.text
    user_data[user_id]['phone'] = phone
    ask_route(user_id)

def ask_route(user_id):
    user_data[user_id]['step'] = 'taxi_route'
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Toshkent -> Angren", "Angren -> Toshkent")
    markup.add("Boshqa yo'nalish")
    bot.send_message(user_id, "Qayerdan qayerga borasiz?", reply_markup=markup)

@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('step') == 'taxi_route')
def taxi_route(message):
    user_id = message.from_user.id
    route = message.text
    user_data[user_id]['route'] = route
    user_data[user_id]['step'] = 'taxi_location'
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📍 Lokatsiyani yuborish", request_location=True))
    markup.add("Lokatsiyasiz davom etish")
    bot.send_message(user_id, "Lokatsiyangizni yuboring:", reply_markup=markup)

@bot.message_handler(content_types=['location'])
def taxi_location(message):
    user_id = message.from_user.id
    if user_data.get(user_id, {}).get('step') == 'taxi_location':
        user_data[user_id]['location'] = message.location
        finish_taxi_order(user_id)

@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('step') == 'taxi_location')
def taxi_location_skip(message):
    user_id = message.from_user.id
    user_data[user_id]['location'] = None
    finish_taxi_order(user_id)

def finish_taxi_order(user_id):
    data = user_data[user_id]
    
    # Get user's destination channel
    channels = database.get_user_channels(user_id)
    if not channels or not channels[1]:
        bot.send_message(user_id, "❌ Avval kanallarni sozlang!")
        show_main_menu(user_id)
        return
    
    dest_channel = channels[1]
    
    order_text = (f"🚖 **Yangi Buyurtma!**\n\n"
                  f"👤 **Ism:** {data['name']}\n"
                  f"📞 **Tel:** {data['phone']}\n"
                  f"🛣 **Yo'nalish:** {data['route']}\n")
    
    if data.get('location'):
        order_text += "📍 **Lokatsiya:** Mavjud (pastda)"
    else:
        order_text += "📍 **Lokatsiya:** Ko'rsatilmagan"
        
    try:
        sent_msg = bot.send_message(dest_channel, order_text, parse_mode='Markdown')
        if data.get('location'):
            bot.send_location(dest_channel, data['location'].latitude, 
                            data['location'].longitude, reply_to_message_id=sent_msg.message_id)
            
        bot.send_message(user_id, "✅ Buyurtma yuborildi!")
    except Exception as e:
        bot.send_message(user_id, f"❌ Xatolik: {e}")
        
    user_data[user_id] = None
    show_main_menu(user_id)

# --- Automatic Forwarding Logic ---
@bot.channel_post_handler(func=lambda message: True, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation'])
def auto_forward(message):
    print("\n" + "="*60)
    print(f"📨 KANAL XABARI KELDI!")
    print(f"   Kanal: {message.chat.title}")
    print(f"   ID: {message.chat.id}")
    print(f"   Username: @{message.chat.username}" if message.chat.username else "   Username: YO'Q")
    print("="*60)
    
    # Get all user channel configs
    configs = database.get_all_configs()
    
    forwarded_count = 0
    for config in configs:
        user_id, source, dest = config
        
        # Check subscription
        if not database.check_subscription(user_id) and user_id != ADMIN_ID:
            continue
        
        # Check if this message is from user's source channel
        is_match = False
        
        # Match by ID
        if str(message.chat.id) == str(source).strip():
            is_match = True
            print(f"✅ MATCH (ID): User {user_id}")
        # Match by username
        elif message.chat.username:
            source_clean = source.strip().lower().replace('@', '')
            chat_username = message.chat.username.lower()
            if source_clean == chat_username or f"@{source_clean}" == f"@{chat_username}":
                is_match = True
                print(f"✅ MATCH (Username): User {user_id}")
        
        if is_match:
            try:
                print(f"🔄 Forwarding to: {dest}")
                bot.copy_message(dest, message.chat.id, message.message_id)
                print(f"✅ SUCCESS!")
                forwarded_count += 1
            except Exception as e:
                print(f"❌ ERROR: {e}")
    
    if forwarded_count == 0:
        print("⚠️  Hech kim uchun forward qilinmadi (sozlamalar yo'q yoki obuna tugagan)")

@bot.message_handler(func=lambda message: message.text == "👤 Kabinet")
def cabinet(message):
    user_id = message.from_user.id
    user = database.get_user(user_id)
    
    if user:
        expiry = user[3] if user[3] else "Faol emas"
        channels = database.get_user_channels(user_id)
        
        msg = f"👤 **Kabinet**\n\n"
        msg += f"🆔 ID: `{user_id}`\n"
        msg += f"📅 Obuna: {expiry}\n\n"
        
        if channels:
            msg += f"📡 **Kanallar:**\n"
            msg += f"📥 Manba: `{channels[0]}`\n"
            msg += f"📤 Manzil: `{channels[1]}`"
        else:
            msg += "📡 Kanallar sozlanmagan"
            
        bot.send_message(user_id, msg, parse_mode='Markdown')
    else:
        send_payment_info(user_id)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    configs = database.get_all_configs()
    users_count = len(set([c[0] for c in configs]))
    
    msg = f"👨‍💼 **Admin Panel**\n\n"
    msg += f"👥 Foydalanuvchilar: {users_count}\n"
    msg += f"📡 Kanallar: {len(configs)}"
    
    bot.send_message(ADMIN_ID, msg, parse_mode='Markdown')

if __name__ == '__main__':
    print("="*60)
    print("🤖 BOT ISHGA TUSHDI!")
    print("="*60)
    bot.infinity_polling()
