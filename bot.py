import os
import psycopg2
from psycopg2.extras import RealDictCursor
import telebot
from telebot import types

# --- تنظیمات ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
OWNER_ID = 8291994828

bot = telebot.TeleBot(BOT_TOKEN)

# --- اتصال به دیتابیس ---
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                points INT DEFAULT 0,
                is_verified BOOLEAN DEFAULT FALSE,
                referrals INT DEFAULT 0,
                await_username_reward VARCHAR(100) DEFAULT NULL,
                admin_step VARCHAR(50) DEFAULT NULL
            );
        """)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS await_username_reward VARCHAR(100) DEFAULT NULL;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_step VARCHAR(50) DEFAULT NULL;")
        except: pass
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS force_channels (
                channel_username VARCHAR(255) PRIMARY KEY
            );
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM force_channels")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO force_channels VALUES ('@Poneix') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO force_channels VALUES ('@BET_1XZX') ON CONFLICT DO NOTHING")
            conn.commit()
            
        cur.close()
        conn.close()
    except Exception as e:
        print("DB Init Error:", e)

def get_force_channels():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT channel_username FROM force_channels")
        channels = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return channels
    except:
        return ["@Poneix", "@BET_1XZX"]

def get_user(user_id):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.execute("INSERT INTO users (user_id) VALUES (%s) RETURNING *", (user_id,))
            user = cur.fetchone()
            conn.commit()
        cur.close()
        conn.close()
        return user
    except Exception as e:
        print("DB Get User Error:", e)
        return {"user_id": user_id, "points": 0, "is_verified": False, "referrals": 0, "await_username_reward": None, "admin_step": None}

def update_user(user_id, **kwargs):
    if not kwargs: return
    try:
        conn = get_db()
        cur = conn.cursor()
        fields = ", ".join([f"{k} = %s" for k in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        cur.execute(f"UPDATE users SET {fields} WHERE user_id = %s", values)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("DB Update Error:", e)

def add_points(user_id, amount):
    user = get_user(user_id)
    if user:
        update_user(user_id, points=user.get("points", 0) + amount)

def deduct_points(user_id, amount):
    user = get_user(user_id)
    if user and user.get("points", 0) >= amount:
        update_user(user_id, points=user.get("points", 0) - amount)
        return True
    return False

# --- کیبوردها ---
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("زیر مجموعه"),
        types.KeyboardButton("پریمیوم ۳ ماهه"),
        types.KeyboardButton("پریمیوم ۶ ماهه"),
        types.KeyboardButton("پریمیوم ۱۲ ماهه"),
        types.KeyboardButton("گیفت تدی"),
    )
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ اضافه کردن جوین اجباری", callback_data="admin_add_channel"))
    markup.add(types.InlineKeyboardButton("➖ حذف کردن جوین اجباری", callback_data="admin_del_channel"))
    return markup

def check_channels(user_id):
    not_joined = []
    channels = get_force_channels()
    for ch in channels:
        try:
            m = bot.get_chat_member(ch, user_id)
            if m.status in ['left', 'kicked']:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    return not_joined

def show_join_buttons(chat_id, channels):
    markup = types.InlineKeyboardMarkup()
    for ch in channels:
        channel_url = f"https://t.me/{ch.replace('@','')}"
        markup.add(types.InlineKeyboardButton(f"عضویت در {ch}", url=channel_url))
    markup.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
    bot.send_message(chat_id, "⚠️ برای استفاده از ربات، ابتدا باید در چنل‌های زیر عضو شوید:", reply_markup=markup)

# --- استارت (بدون کپچا) ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user = get_user(user_id)

    # رفرال
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id and not user.get("is_verified"):
            update_user(referrer_id, referrals=get_user(referrer_id).get("referrals", 0) + 1)
            add_points(referrer_id, 1)
            try:
                bot.send_message(referrer_id, "🎉 یک نفر با لینک شما وارد شد! +۱ امتیاز")
            except:
                pass

    # مستقیم چک عضویت
    not_joined = check_channels(user_id)
    if not not_joined:
        if not user.get("is_verified"):
            update_user(user_id, is_verified=True)
        bot.send_message(message.chat.id, "خوش اومدی داداش! 👋\nاز منو انتخاب کن:", reply_markup=main_keyboard())
    else:
        show_join_buttons(message.chat.id, not_joined)

# --- چک عضویت (بعد از زدن دکمه عضو شدم) ---
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join(call):
    user_id = call.from_user.id
    not_joined = check_channels(user_id)
    
    if not not_joined:
        update_user(user_id, is_verified=True)
        # ۱. پاک کردن پیام عضویت
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # ۲. ارسال پیام تایید
        bot.send_message(call.message.chat.id, "✅ تایید شد! خوش اومدی داداش.")
        
        # ۳. ارسال کیبورد اصلی در یک پیام جداگانه (تضمینی)
        bot.send_message(call.message.chat.id, "👇 از منو زیر انتخاب کن:", reply_markup=main_keyboard())
    else:
        bot.answer_callback_query(call.id, f"❌ هنوز عضو اینا نشدی: {', '.join(not_joined)}", show_alert=True)

# --- منوها ---
@bot.message_handler(func=lambda m: m.text == "زیر مجموعه")
def show_referral(message):
    user_id = message.from_user.id
    username = bot.get_me().username
    link = f"https://t.me/{username}?start={user_id}"
    user = get_user(user_id)
    if not user: return
    bot.send_message(message.chat.id,
        f"🔗 لینک زیرمجموعه شما:\n{link}\n\n"
        f"👥 تعداد دعوت‌ها: {user.get('referrals', 0)}\n"
        f"⭐ امتیاز شما: {user.get('points', 0)}\n\n"
        f"هر دعوت = ۱ امتیاز")

REWARDS = {
    "پریمیوم ۳ ماهه": 30,
    "پریمیوم ۶ ماهه": 50,
    "پریمیوم ۱۲ ماهه": 90,
    "گیفت تدی": 12,
}

@bot.message_handler(func=lambda m: m.text in REWARDS)
def handle_reward(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user: return
    cost = REWARDS[message.text]

    if user.get("points", 0) < cost:
        bot.reply_to(message,
            f"برای این دکمه به {cost} امتیاز نیاز دارید.\n"
            f"⭐ امتیاز شما: {user.get('points', 0)}\n"
            f"🔗 لینک زیرمجموعه در دکمه «زیر مجموعه» هست.")
        return

    if deduct_points(user_id, cost):
        update_user(user_id, await_username_reward=message.text)
        bot.reply_to(message,
            f"✅ {cost} امتیاز کسر شد.\n"
            f"لطفاً آیدی یوزرنیم خود را بفرستید (مثال: @username):")
    else:
        bot.reply_to(message, "خطا در کسر امتیاز.")

@bot.message_handler(func=lambda m: get_user(m.from_user.id) and get_user(m.from_user.id).get("await_username_reward"))
def receive_username(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user: return
    reward = user.get("await_username_reward")
    
    update_user(user_id, await_username_reward=None)

    text = (f"📥 درخواست جدید:\n"
            f"👤 کاربر: {message.from_user.first_name} ({user_id})\n"
            f"🎁 جایزه: {reward}\n"
            f"🆔 یوزرنیم: {message.text}")
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_{user_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id}"),
    )
    bot.send_message(OWNER_ID, text, reply_markup=markup)
    bot.reply_to(message, "درخواست برای مالک ارسال شد. منتظر تایید باش.")

@bot.callback_query_handler(func=lambda c: c.data.startswith(('approve_', 'reject_')))
def owner_action(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "مخصوص مالک است.")
        return
    action, uid = call.data.split('_')
    uid = int(uid)
    if action == "approve":
        bot.send_message(uid, "✅ واریز شد! درخواست شما تایید گردید.")
        bot.edit_message_text(f"{call.message.text}\n\n✅ تایید شد.", call.message.chat.id, call.message.message_id)
    else:
        bot.send_message(uid, "❌ درخواست شما رد شد.")
        bot.edit_message_text(f"{call.message.text}\n\n❌ رد شد.", call.message.chat.id, call.message.message_id)

# --- پنل ادمین ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ دسترسی ندارید.")
        return
    bot.send_message(message.chat.id, "👨‍💻 پنل مدیریت:", reply_markup=admin_keyboard())

@bot.callback_query_handler(func=lambda c: c.data.startswith('admin_'))
def admin_callbacks(call):
    if call.from_user.id != OWNER_ID: return
    
    action = call.data
    if action == "admin_add_channel":
        update_user(OWNER_ID, admin_step="add_channel")
        bot.send_message(OWNER_ID, "لطفاً آیدی چنل را با @ بفرستید:")
        bot.answer_callback_query(call.id)
    elif action == "admin_del_channel":
        channels = get_force_channels()
        if not channels:
            bot.send_message(OWNER_ID, "هیچ چنلی ثبت نشده است.")
            return
        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"❌ حذف {ch}", callback_data=f"delch_{ch}"))
        bot.send_message(OWNER_ID, "کدام چنل حذف شود؟", reply_markup=markup)
        bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: get_user(m.from_user.id) and get_user(m.from_user.id).get("admin_step") == "add_channel")
def admin_add_channel_receive(message):
    if message.from_user.id != OWNER_ID: return
    ch = message.text.strip()
    if not ch.startswith("@"): ch = "@" + ch
    try:
        bot_member = bot.get_chat_member(ch, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "❌ ربات در این چنل ادمین نیست!")
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO force_channels (channel_username) VALUES (%s) ON CONFLICT DO NOTHING", (ch,))
        conn.commit()
        cur.close()
        conn.close()
        bot.reply_to(message, f"✅ چنل {ch} با موفقیت اضافه شد.")
        update_user(OWNER_ID, admin_step=None)
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith('delch_'))
def admin_delete_channel(call):
    if call.from_user.id != OWNER_ID: return
    ch = call.data.replace("delch_", "")
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM force_channels WHERE channel_username = %s", (ch,))
        conn.commit()
        cur.close()
        conn.close()
        bot.edit_message_text(f"✅ چنل {ch} حذف شد.", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "حذف شد")
    except Exception as e:
        bot.answer_callback_query(call.id, f"خطا: {e}")

# --- اجرا ---
if __name__ == "__main__":
    init_db()
    print("Bot running...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
