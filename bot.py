import os
import logging
import random
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from database import (
    init_db,
    create_user,
    get_user,
    set_captcha_verified,
    set_membership_verified,
    reward_referrer,
    get_forced_channels,
    add_forced_channel,
    remove_forced_channel,
    get_points,
    create_order,
    get_order,
    update_order_status,
    refund_order,
    get_user_stats,
)


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_ID = int(os.getenv("OWNER_ID", "8291994828"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN is missing")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is missing")


# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# =========================
# PRODUCTS
# =========================

PRODUCTS = {
    "پریمیوم ۳ ماهه": 30,
    "پریمیوم ۶ ماهه": 50,
    "پریمیوم ۱۲ ماهه": 90,
    "گیفت تدی": 12,
}


# =========================
# KEYBOARDS
# =========================

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["زیر مجموعه"],
            ["پریمیوم ۳ ماهه"],
            ["پریمیوم ۶ ماهه"],
            ["پریمیوم ۱۲ ماهه"],
            ["گیفت تدی"],
        ],
        resize_keyboard=True,
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["کاربران"],
            ["➕ افزودن کانال"],
            ["➖ حذف کانال"],
            ["🔙 بازگشت"],
        ],
        resize_keyboard=True,
    )


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    print(
        f"✅ START RECEIVED | user={update.effective_user.id}",
        flush=True,
    )

    user = update.effective_user

    referred_by = None

    if context.args:

        arg = context.args[0]

        if arg.startswith("ref_"):

            try:
                referred_by = int(arg.replace("ref_", ""))
            except Exception:
                referred_by = None

    if referred_by == user.id:
        referred_by = None

    existing = get_user(user.id)

    if not existing:
        create_user(
            user.id,
            user.username,
            referred_by,
        )
    else:
        create_user(
            user.id,
            user.username,
            None,
        )

    db_user = get_user(user.id)

    if db_user["captcha_verified"]:
        await show_membership(update, context)
        return

    await send_captcha(update, context)


# =========================
# CAPTCHA
# =========================

async def send_captcha(update, context):

    a = random.randint(1, 9)
    b = random.randint(1, 9)

    answer = a + b

    context.user_data["captcha_answer"] = answer

    wrong1 = answer + 1
    wrong2 = answer + 2
    wrong3 = max(0, answer - 1)

    numbers = [
        answer,
        wrong1,
        wrong2,
        wrong3,
    ]

    random.shuffle(numbers)

    keyboard = []

    row = []

    for number in numbers:

        row.append(
            InlineKeyboardButton(
                str(number),
                callback_data=f"captcha:{number}",
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🔐 کپچا\n\n"
        f"{a} + {b} = ؟\n\n"
        "جواب صحیح را انتخاب کن:"
    )

    await update.message.reply_text(
        text,
        reply_markup=markup,
    )


async def captcha_callback(update, context):

    query = update.callback_query

    await query.answer()

    selected = int(
        query.data.split(":")[1]
    )

    correct = context.user_data.get(
        "captcha_answer"
    )

    if selected != correct:

        await query.answer(
            "❌ جواب اشتباهه",
            show_alert=True,
        )

        return

    user_id = query.from_user.id

    set_captcha_verified(user_id)

    context.user_data.pop(
        "captcha_answer",
        None,
    )

    referrer_id = reward_referrer(user_id)

    if referrer_id:

        try:

            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "🎉 زیرمجموعه جدید!\n\n"
                    "⭐ ۱ امتیاز به حساب شما اضافه شد."
                ),
            )

        except Exception as e:

            logger.warning(
                "Referral notification failed: %s",
                e,
            )

    await query.edit_message_text(
        "✅ کپچا درست بود."
    )

    await show_membership(
        update,
        context,
    )


# =========================
# MEMBERSHIP
# =========================

async def show_membership(update, context):

    channels = get_forced_channels()

    keyboard = []

    for channel in channels:

        username = channel["username"]

        link = (
            f"https://t.me/{username.lstrip('@')}"
        )

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📢 {username}",
                    url=link,
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "✅ بررسی عضویت",
                callback_data="check_membership",
            )
        ]
    )

    markup = InlineKeyboardMarkup(
        keyboard
    )

    text = (
        "📢 برای ورود به ربات، "
        "ابتدا در کانال‌های زیر عضو شو.\n\n"
        "بعد از عضویت روی "
        "«بررسی عضویت» بزن."
    )

    if update.callback_query:

        await update.callback_query.message.reply_text(
            text,
            reply_markup=markup,
        )

    else:

        await update.message.reply_text(
            text,
            reply_markup=markup,
        )


async def check_membership(update, context):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    channels = get_forced_channels()

    not_joined = []

    for channel in channels:

        username = channel["username"]

        try:

            member = await context.bot.get_chat_member(
                chat_id=username,
                user_id=user_id,
            )

            status = member.status

            if status in (
                "left",
                "kicked",
            ):
                not_joined.append(username)

        except Exception as e:

            logger.error(
                "Membership check error for %s: %s",
                username,
                e,
            )

            not_joined.append(username)

    if not_joined:

        await query.answer(
            "❌ هنوز عضو همه کانال‌ها نشدی.",
            show_alert=True,
        )

        return

    set_membership_verified(user_id)

    await query.edit_message_text(
        "✅ عضویت تأیید شد."
    )

    await query.message.reply_text(
        "🎉 خوش اومدی!\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن:",
        reply_markup=main_keyboard(),
    )


# =========================
# REFERRAL
# =========================

async def referral_menu(update, context):

    user_id = update.effective_user.id

    user = get_user(user_id)

    points = get_points(user_id)

    bot = await context.bot.get_me()

    link = (
        f"https://t.me/{bot.username}?start=ref_{user_id}"
    )

    count = user["referral_count"]

    await update.message.reply_text(
        "👥 زیر مجموعه\n\n"
        f"⭐ امتیاز: {points}\n"
        f"👤 دعوت موفق: {count}\n\n"
        "🔗 لینک دعوت شما:\n"
        f"{link}\n\n"
        "هر دعوت موفق = ۱ امتیاز"
    )


# =========================
# PRODUCTS
# =========================

async def product_menu(update, context):

    product = update.message.text

    if product not in PRODUCTS:
        return

    user_id = update.effective_user.id

    required = PRODUCTS[product]

    current = get_points(user_id)

    if current < required:

        await update.message.reply_text(
            "❌ امتیاز کافی نیست.\n\n"
            f"⭐ امتیاز فعلی: {current}\n"
            f"⭐ امتیاز مورد نیاز: {required}\n\n"
            "برای گرفتن امتیاز بیشتر "
            "از بخش «زیر مجموعه» استفاده کن."
        )

        return

    context.user_data[
        "pending_product"
    ] = product

    await update.message.reply_text(
        f"📦 محصول: {product}\n"
        f"⭐ قیمت: {required} امتیاز\n\n"
        "آیدی تلگرام خودت را ارسال کن.\n\n"
        "مثال:\n"
        "@username"
    )


# =========================
# ORDER
# =========================

async def receive_username(update, context):

    product = context.user_data.get(
        "pending_product"
    )

    if not product:
        return False

    username = update.message.text.strip()

    if not re.fullmatch(
        r"@[A-Za-z0-9_]{5,32}",
        username,
    ):

        await update.message.reply_text(
            "❌ آیدی تلگرام اشتباهه.\n\n"
            "مثال:\n"
            "@username"
        )

        return True

    points = PRODUCTS[product]

    order_id = create_order(
        user_id=update.effective_user.id,
        product=product,
        points=points,
        telegram_username=username,
    )

    if not order_id:

        context.user_data.pop(
            "pending_product",
            None,
        )

        await update.message.reply_text(
            "❌ ثبت سفارش انجام نشد."
        )

        return True

    context.user_data.pop(
        "pending_product",
        None,
    )

    await update.message.reply_text(
        "✅ سفارش ثبت شد.\n\n"
        f"📦 محصول: {product}\n"
        f"⭐ هزینه: {points} امتیاز\n"
        f"🆔 سفارش: #{order_id}\n\n"
        "⏳ منتظر بررسی ادمین باش."
    )

    admin_text = (
        "📥 سفارش جدید\n\n"
        f"🆔 سفارش: #{order_id}\n"
        f"👤 User ID: {update.effective_user.id}\n"
        f"📛 Username: "
        f"@{update.effective_user.username or 'ندارد'}\n"
        f"📦 محصول: {product}\n"
        f"⭐ هزینه: {points}\n"
        f"🎯 آیدی: {username}"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ تأیید",
                    callback_data=f"approve:{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ رد",
                    callback_data=f"reject:{order_id}",
                ),
            ]
        ]
    )

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=admin_text,
        reply_markup=keyboard,
    )

    return True


# =========================
# ADMIN
# =========================

async def admin_command(update, context):

    if update.effective_user.id != OWNER_ID:

        await update.message.reply_text(
            "❌ دسترسی ندارید."
        )

        return

    await update.message.reply_text(
        "⚙️ پنل مدیریت",
        reply_markup=admin_keyboard(),
    )


async def admin_users(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    users, points, pending = get_user_stats()

    await update.message.reply_text(
        "📊 آمار\n\n"
        f"👤 کاربران: {users}\n"
        f"⭐ مجموع امتیاز: {points}\n"
        f"📦 سفارش‌های در انتظار: {pending}"
    )


async def admin_add_channel(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    context.user_data[
        "admin_action"
    ] = "add_channel"

    await update.message.reply_text(
        "➕ آیدی کانال را بفرست.\n\n"
        "مثال:\n"
        "@MyChannel"
    )


async def admin_remove_channel(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    channels = get_forced_channels()

    text = "📢 کانال‌ها:\n\n"

    for channel in channels:

        if channel["protected"]:
            status = "🔒 محافظت‌شده"
        else:
            status = "قابل حذف"

        text += (
            f"{channel['username']} - {status}\n"
        )

    text += "\nآیدی کانالی که می‌خواهی حذف کنی را بفرست."

    context.user_data[
        "admin_action"
    ] = "remove_channel"

    await update.message.reply_text(
        text
    )


async def admin_text_handler(update, context):

    if update.effective_user.id != OWNER_ID:
        return False

    action = context.user_data.get(
        "admin_action"
    )

    if not action:
        return False

    value = update.message.text.strip()

    if action == "add_channel":

        if not value.startswith("@"):

            await update.message.reply_text(
                "❌ مثال صحیح: @MyChannel"
            )

            return True

        try:

            me = await context.bot.get_me()

            member = await context.bot.get_chat_member(
                chat_id=value,
                user_id=me.id,
            )

            if member.status not in (
                "administrator",
                "creator",
            ):

                await update.message.reply_text(
                    "❌ ربات ادمین این کانال نیست."
                )

                return True

            chat = await context.bot.get_chat(
                value
            )

            add_forced_channel(
                value,
                chat.title,
            )

            context.user_data.pop(
                "admin_action",
                None,
            )

            await update.message.reply_text(
                "✅ کانال اضافه شد.",
                reply_markup=admin_keyboard(),
            )

        except Exception as e:

            logger.error(
                "ADD CHANNEL ERROR: %s",
                e,
            )

            await update.message.reply_text(
                "❌ نتوانستم کانال را بررسی کنم.\n"
                "آیدی کانال یا دسترسی ادمین ربات را بررسی کن."
            )

        return True

    if action == "remove_channel":

        protected = {
            "@poneix",
            "@bet_1xzx",
        }

        if value.lower() in protected:

            await update.message.reply_text(
                "❌ این کانال اصلی قابل حذف نیست."
            )

            return True

        remove_forced_channel(value)

        context.user_data.pop(
            "admin_action",
            None,
        )

        await update.message.reply_text(
            "✅ کانال حذف شد.",
            reply_markup=admin_keyboard(),
        )

        return True

    return False


# =========================
# ORDER ACTION
# =========================

async def order_action(update, context):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != OWNER_ID:

        await query.answer(
            "❌ دسترسی ندارید.",
            show_alert=True,
        )

        return

    action, order_id_text = query.data.split(":")

    order_id = int(order_id_text)

    order = get_order(order_id)

    if not order:

        await query.edit_message_text(
            "❌ سفارش پیدا نشد."
        )

        return

    if order["status"] != "pending":

        await query.answer(
            "این سفارش قبلاً بررسی شده.",
            show_alert=True,
        )

        return

    if action == "approve":

        update_order_status(
            order_id,
            "approved",
        )

        await query.edit_message_text(
            f"✅ سفارش #{order_id} تأیید شد."
        )

        try:

            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    "🎉 سفارش شما تأیید شد.\n\n"
                    f"📦 محصول: {order['product']}\n"
                    f"🆔 سفارش: #{order_id}\n\n"
                    "✅ تحویل/پرداخت توسط ادمین تأیید شد."
                ),
            )

        except Exception as e:

            logger.error(
                "APPROVE MESSAGE ERROR: %s",
                e,
            )

    elif action == "reject":

        refunded = refund_order(
            order_id
        )

        if not refunded:
            await query.answer(
                "این سفارش قبلاً بررسی شده.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            f"❌ سفارش #{order_id} رد شد.\n"
            "⭐ امتیازها برگشت داده شد."
        )

        try:

            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    "❌ سفارش شما رد شد.\n\n"
                    f"📦 محصول: {order['product']}\n"
                    f"🆔 سفارش: #{order_id}\n\n"
                    f"⭐ {order['points']} امتیاز "
                    "به حساب شما برگشت داده شد."
                ),
            )

        except Exception as e:

            logger.error(
                "REJECT MESSAGE ERROR: %s",
                e,
            )


# =========================
# TEXT ROUTER
# =========================

async def text_router(update, context):

    text = update.message.text

    if update.effective_user.id == OWNER_ID:

        if text == "کاربران":
            await admin_users(
                update,
                context,
            )
            return

        if text == "➕ افزودن کانال":
            await admin_add_channel(
                update,
                context,
            )
            return

        if text == "➖ حذف کانال":
            await admin_remove_channel(
                update,
                context,
            )
            return

        if text == "🔙 بازگشت":

            context.user_data.clear()

            await update.message.reply_text(
                "🔙 برگشتی.",
                reply_markup=main_keyboard(),
            )

            return

        if await admin_text_handler(
            update,
            context,
        ):
            return

    if text == "زیر مجموعه":

        await referral_menu(
            update,
            context,
        )

        return

    if text in PRODUCTS:

        await product_menu(
            update,
            context,
        )

        return

    if await receive_username(
        update,
        context,
    ):
        return

    await update.message.reply_text(
        "یکی از گزینه‌های منو را انتخاب کن.",
        reply_markup=main_keyboard(),
    )


# =========================
# ERROR
# =========================

async def error_handler(update, context):

    logger.error(
        "BOT ERROR",
        exc_info=context.error,
    )


# =========================
# MAIN
# =========================

def main():

    print("=" * 40, flush=True)
    print("STARTING BOT...", flush=True)

    print(
        "DATABASE_URL: OK",
        flush=True,
    )

    print(
        "BOT_TOKEN: OK",
        flush=True,
    )

    # تست اتصال دیتابیس
    init_db()

    print(
        "DATABASE CONNECTION: OK",
        flush=True,
    )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            captcha_callback,
            pattern=r"^captcha:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern=r"^check_membership$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            order_action,
            pattern=r"^(approve|reject):",
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router,
        )
    )

    application.add_error_handler(
        error_handler
    )

    print(
        "POLLING STARTING...",
        flush=True,
    )

    # اگر آپدیت‌های قدیمی مانده باشند، ردشان می‌کند.
    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
