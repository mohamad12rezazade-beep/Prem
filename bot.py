import os
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import telebot
from telebot import types

# --- تنظیمات ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
OWNER_ID = 8291994828

FORCE_CHANNELS = ["@Poneix", "@BET_1XZX"]

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# --- اتصال به دیتابیس ---
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            points INT DEFAULT 0,
            is_verified BOOLEAN DEFAULT FALSE,
            referrals INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_user(user_id):
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

def update_user(user_id, **kwargs):
    conn = get_db()
    cur = conn.cursor()
    fields = ", ".join([f"{k} = %s" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    cur.execute(f"UPDATE users SET {fields} WHERE user_id = %s", values)
    conn.commit()
    cur.close()
    conn.close()

def add_points(user_id, amount):
    user = get_user(user_id)
    new_points = user["points"] + amount
    update_user(user_id, points=new_points)
    return new_points

def deduct_points(user_id, amount):
    user = get_user(user_id)
    if user["points"] >= amount:
        update_user(user_id, points=user["points"] - amount)
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

def captcha_keyboard():
    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    correct = num1 + num2
    options = list({correct, correct + random.randint(1, 5), correct - random.randint(1, 5)})
    random.shuffle(options)
    markup = types.InlineKeyboardMarkup()
    for opt in options:
        markup.add(types.InlineKeyboardButton(str(opt), callback_data=f"captcha_{opt}"))
    return markup, correct

# --- هندلرها ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user = get_user(user_id)

    # پردازش رفرال (start با پارامتر)
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            # اگه کاربر جدید بود و قبلاً رفرال نشده بود
            if not user.get("is_verified"):
                update_user(referrer_id, referrals=get_user(referrer_id)["referrals"] + 1)
                add_points(referrer_id, 1)
                try:
                    bot.send_message(referrer_id, "🎉 یک نفر با لینک شما وارد شد! +۱ امتیاز")
                except:
                    pass

    if user.get("is_verified"):
        not_joined = check_channels(user_id)
        if not not_joined:
            bot.send_message(message.chat.id, "خوش اومدی داداش! 👋\nاز منو انتخاب کن:", reply_markup=main_keyboard())
            return
        else:
            show_join_buttons(message.chat.id, not_joined)
            return

    markup, correct = captcha_keyboard()
    user_states[user_id] = {"captcha_answer": correct, "step": "captcha"}
    bot.send_message(message.chat.id, "سلام! برای شروع حاصل جمع زیر رو انتخاب کن:", reply_markup=markup)

def check_channels(user_id):
    not_joined = []
    for ch in FORCE_CHANNELS:
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
        markup.add(types.InlineKeyboardButton(f"عضویت در {ch}", url=f"https://t.me/{ch.replace('@','')}"))
    markup.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
    bot.send_message(chat_id, "برای استفاده باید عضو چنل‌های زیر بشی:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def handle_captcha(call):
    user_id = call.from_user.id
    ans = int(call.data.split('_')[1])
    state = user_states.get(user_id)
    if not state or state.get("step") != "captcha":
        bot.answer_callback_query(call.id, "دوباره /start بزن.")
        return
    if ans == state["captcha_answer"]:
        bot.answer_callback_query(call.id, "✅ درست بود!")
        user_states[user_id]["step"] = "join_check"
        not_joined = check_channels(user_id)
        if not not_joined:
            finish_verify(call.message, user_id)
        else:
            show_join_buttons(call.message.chat.id, not_joined)
    else:
        bot.answer_callback_query(call.id, "❌ اشتباهه! دوباره /start بزن.")

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join(call):
    user_id = call.from_user.id
    not_joined = check_channels(user_id)
    if not not_joined:
        finish_verify(call.message, user_id)
    else:
        bot.answer_callback_query(call.id, f"❌ هنوز عضو نشدی: {', '.join(not_joined)}")

def finish_verify(message, user_id):
    update_user(user_id, is_verified=True)
    try:
        bot.edit_message_text("✅ تایید شد! خوش اومدی.", message.chat.id, message.message_id)
    except:
        pass
    bot.send_message(message.chat.id, "منوی اصلی:", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "زیر مجموعه")
def show_referral(message):
    user_id = message.from_user.id
    username = bot.get_me().username
    link = f"https://t.me/{username}?start={user_id}"
    user = get_user(user_id)
    bot.send_message(message.chat.id,
        f"🔗 لینک زیرمجموعه شما:\n{link}\n\n"
        f"👥 تعداد دعوت‌ها: {user['referrals']}\n"
        f"⭐ امتیاز شما: {user['points']}\n\n"
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
    cost = REWARDS[message.text]

    if user["points"] < cost:
        bot.reply_to(message,
            f"برای این دکمه به {cost} امتیاز نیاز دارید.\n"
            f"⭐ امتیاز شما: {user['points']}\n"
            f"🔗 لینک زیرمجموعه در دکمه «زیر مجموعه» هست.")
        return

    if deduct_points(user_id, cost):
        user_states[user_id] = {"step": "await_username", "reward": message.text}
        bot.reply_to(message,
            f"✅ {cost} امتیاز کسر شد.\n"
            f"لطفاً آیدی یوزرنیم خود را بفرستید (مثال: @username):")
    else:
        bot.reply_to(message, "خطا در کسر امتیاز.")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("step") == "await_username")
def receive_username(message):
    user_id = message.from_user.id
    username = message.text
    state = user_states[user_id]

    text = (f"📥 درخواست جدید:\n"
            f"👤 کاربر: {message.from_user.first_name} ({user_id})\n"
            f"🎁 جایزه: {state['reward']}\n"
            f"🆔 یوزرنیم: {username}")
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_{user_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id}"),
    )
    bot.send_message(OWNER_ID, text, reply_markup=markup)
    bot.reply_to(message, "درخواست برای مالک ارسال شد. منتظر تایید باش.")
    del user_states[user_id]

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

# --- اجرا ---
if __name__ == "__main__":
    init_db()
    print("Bot running...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
