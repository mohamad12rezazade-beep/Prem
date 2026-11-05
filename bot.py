import os
import random
import logging
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
    add_points,
    get_points,
    set_captcha_verified,
    set_membership_verified,
    get_forced_channels,
    add_forced_channel,
    remove_forced_channel,
    create_order,
    update_order_status,
    get_order,
)


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8291994828"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# PRODUCTS
# =========================================================

PRODUCTS = {
    "پریمیوم ۳ ماهه": {
        "name": "پریمیوم ۳ ماهه",
        "points": 30,
    },

    "پریمیوم ۶ ماهه": {
        "name": "پریمیوم ۶ ماهه",
        "points": 50,
    },

    "پریمیوم ۱۲ ماهه": {
        "name": "پریمیوم ۱۲ ماهه",
        "points": 90,
    },

    "گیفت تدی": {
        "name": "گیفت تدی",
        "points": 12,
    },
}


# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard():
    keyboard = [
        ["زیر مجموعه"],
        ["پریمیوم ۳ ماهه"],
        ["پریمیوم ۶ ماهه"],
        ["پریمیوم ۱۲ ماهه"],
        ["گیفت تدی"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


def admin_keyboard():
    keyboard = [
        ["کاربران"],
        ["➕ افزودن کانال"],
        ["➖ حذف کانال"],
        ["🔙 بازگشت"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# =========================================================
# CAPTCHA
# =========================================================

def create_captcha(context):
    answer = random.randint(1, 5)

    numbers = list(range(1, 6))
    random.shuffle(numbers)

    keyboard = []

    for number in numbers:
        keyboard.append([
            InlineKeyboardButton(
                str(number),
                callback_data=f"captcha:{number}:{answer}"
            )
        ])

    context.user_data["captcha_answer"] = answer

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# FORCED JOIN KEYBOARD
# =========================================================

def forced_join_keyboard(channels):

    keyboard = []

    for channel in channels:

        username = channel["username"]

        keyboard.append([
            InlineKeyboardButton(
                f"عضویت در {username}",
                url=f"https://t.me/{username.lstrip('@')}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "✅ بررسی عضویت",
            callback_data="check_membership"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    # referral
    referred_by = None

    if context.args:

        try:
            referrer_id = int(context.args[0])

            if referrer_id != user.id:
                referred_by = referrer_id

        except Exception:
            pass

    existing_user = get_user(user.id)

    if not existing_user:

        create_user(
            user_id=user.id,
            username=user.username,
            referred_by=referred_by
        )

    else:

        create_user(
            user_id=user.id,
            username=user.username
        )

    # اگر قبلاً تأیید شده
    user_data = get_user(user.id)

    if (
        user_data
        and user_data["captcha_verified"]
        and user_data["membership_verified"]
    ):

        await update.message.reply_text(
            "👋 خوش اومدی!\n\n"
            "از منوی زیر استفاده کن:",
            reply_markup=main_keyboard()
        )

        return

    # اگر کپچا قبلاً انجام شده
    if user_data and user_data["captcha_verified"]:

        channels = get_forced_channels()

        if channels:

            await update.message.reply_text(
                "🔒 برای استفاده از ربات باید در کانال‌های زیر عضو باشی:",
                reply_markup=forced_join_keyboard(channels)
            )

            return

    # کپچا
    keyboard = create_captcha(context)

    await update.message.reply_text(
        "🔐 کپچا\n\n"
        "برای ورود به ربات، عدد درست را انتخاب کن:",
        reply_markup=keyboard
    )


# =========================================================
# CAPTCHA CALLBACK
# =========================================================

async def captcha_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    parts = query.data.split(":")

    if len(parts) != 3:
        return

    selected = int(parts[1])
    answer = int(parts[2])

    if selected != answer:

        await query.answer(
            "❌ پاسخ اشتباه است.",
            show_alert=True
        )

        return

    user_id = query.from_user.id

    user = get_user(user_id)

    if not user:
        return

    # فقط اولین بار referral حساب می‌شود
    if not user["captcha_verified"]:

        set_captcha_verified(user_id)

        referred_by = user["referred_by"]

        if referred_by and referred_by != user_id:

            referrer = get_user(referred_by)

            if referrer:

                add_points(referred_by, 1)

                try:

                    await context.bot.send_message(
                        chat_id=referred_by,
                        text=(
                            "🎉 یک زیرمجموعه جدید وارد ربات شد.\n\n"
                            "➕ ۱ امتیاز به حساب شما اضافه شد."
                        )
                    )

                except Exception as e:

                    logger.warning(
                        f"Could not send referral message: {e}"
                    )

    channels = get_forced_channels()

    if channels:

        await query.edit_message_text(
            "✅ کپچا درست بود.\n\n"
            "حالا در کانال‌های زیر عضو شو و سپس روی "
            "«بررسی عضویت» بزن:",
            reply_markup=forced_join_keyboard(channels)
        )

    else:

        set_membership_verified(user_id)

        await query.edit_message_text(
            "✅ ورود با موفقیت انجام شد."
        )

        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 خوش اومدی!",
            reply_markup=main_keyboard()
        )


# =========================================================
# MEMBERSHIP CHECK
# =========================================================

async def check_membership(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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
                user_id=user_id
            )

            if member.status in (
                "left",
                "kicked",
            ):

                not_joined.append(username)

        except Exception as e:

            logger.warning(
                f"Membership check failed for {username}: {e}"
            )

            not_joined.append(username)

    if not_joined:

        await query.answer(
            "❌ هنوز در همه کانال‌ها عضو نشده‌ای.",
            show_alert=True
        )

        return

    set_membership_verified(user_id)

    await query.edit_message_text(
        "✅ عضویت شما تأیید شد."
    )

    await context.bot.send_message(
        chat_id=user_id,
        text="🎉 ورود کامل شد.\n\nاز منوی زیر استفاده کن:",
        reply_markup=main_keyboard()
    )


# =========================================================
# CHECK USER VERIFICATION
# =========================================================

def is_verified(user_id):

    user = get_user(user_id)

    if not user:
        return False

    return (
        user["captcha_verified"]
        and user["membership_verified"]
    )


async def require_verified(update, context):

    if not is_verified(update.effective_user.id):

        await update.message.reply_text(
            "❌ ابتدا /start را بزن و مراحل ورود را کامل کن."
        )

        return False

    return True


# =========================================================
# REFERRAL MENU
# =========================================================

async def referral_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_verified(update, context):
        return

    user_id = update.effective_user.id

    user = get_user(user_id)

    points = get_points(user_id)

    bot = await context.bot.get_me()

    referral_link = (
        f"https://t.me/{bot.username}?start={user_id}"
    )

    await update.message.reply_text(
        "👥 زیر مجموعه\n\n"
        f"⭐ امتیاز شما: {points}\n"
        f"👤 تعداد دعوت موفق: {user['referral_count']}\n\n"
        "🔗 لینک دعوت شما:\n"
        f"{referral_link}\n\n"
        "هر دعوت موفق = ۱ امتیاز"
    )


# =========================================================
# PRODUCT SELECTION
# =========================================================

async def product_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_verified(update, context):
        return

    product_text = update.message.text

    product = PRODUCTS.get(product_text)

    if not product:
        return

    required_points = product["points"]

    current_points = get_points(
        update.effective_user.id
    )

    if current_points < required_points:

        await update.message.reply_text(
            "❌ امتیاز کافی نیست.\n\n"
            f"📌 محصول: {product_text}\n"
            f"⭐ امتیاز مورد نیاز: {required_points}\n"
            f"⭐ امتیاز فعلی شما: {current_points}\n\n"
            "برای گرفتن امتیاز بیشتر، از لینک دعوتت "
            "در بخش «زیر مجموعه» استفاده کن."
        )

        return

    context.user_data["pending_product"] = product_text

    await update.message.reply_text(
        "✅ امتیاز کافی داری.\n\n"
        f"📦 محصول: {product_text}\n"
        f"⭐ هزینه: {required_points} امتیاز\n\n"
        "حالا آیدی تلگرام خودت را ارسال کن.\n\n"
        "مثال:\n"
        "@username"
    )


# =========================================================
# RECEIVE TELEGRAM USERNAME
# =========================================================

async def receive_username(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_verified(update, context):
        return

    product_text = context.user_data.get(
        "pending_product"
    )

    if not product_text:
        return

    username = update.message.text.strip()

    if not re.match(
        r"^@[A-Za-z0-9_]{5,32}$",
        username
    ):

        await update.message.reply_text(
            "❌ آیدی تلگرام معتبر نیست.\n\n"
            "مثال درست:\n"
            "@username"
        )

        return

    product = PRODUCTS.get(product_text)

    if not product:
        return

    required_points = product["points"]

    current_points = get_points(
        update.effective_user.id
    )

    if current_points < required_points:

        context.user_data.pop(
            "pending_product",
            None
        )

        await update.message.reply_text(
            "❌ امتیاز کافی نیست."
        )

        return

    # کسر امتیاز + ساخت سفارش
    order_id = create_order(
        user_id=update.effective_user.id,
        product=product_text,
        points=required_points,
        telegram_username=username
    )

    if not order_id:

        await update.message.reply_text(
            "❌ ثبت سفارش انجام نشد.\n"
            "ممکن است امتیازت کافی نباشد."
        )

        return

    context.user_data.pop(
        "pending_product",
        None
    )

    await update.message.reply_text(
        "✅ درخواست شما ثبت شد.\n\n"
        f"📦 محصول: {product_text}\n"
        f"⭐ هزینه: {required_points} امتیاز\n"
        f"👤 آیدی تلگرام: {username}\n\n"
        "⏳ درخواست برای ادمین ارسال شد."
    )

    # ارسال برای مالک
    user = update.effective_user

    admin_text = (
        "📥 سفارش جدید\n\n"
        f"🆔 شماره سفارش: #{order_id}\n"
        f"👤 User ID: {user.id}\n"
        f"📛 Username: @{user.username if user.username else 'ندارد'}\n"
        f"📦 محصول: {product_text}\n"
        f"⭐ هزینه: {required_points} امتیاز\n"
        f"🎯 آیدی دریافت‌کننده: {username}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ تأیید",
                callback_data=f"approve:{order_id}"
            ),
            InlineKeyboardButton(
                "❌ رد",
                callback_data=f"reject:{order_id}"
            )
        ]
    ])

    try:

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=admin_text,
            reply_markup=keyboard
        )

    except Exception as e:

        logger.error(
            f"Could not send order to owner: {e}"
        )


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(user_id):

    return user_id == OWNER_ID


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):

        await update.message.reply_text(
            "❌ دسترسی ندارید."
        )

        return

    await update.message.reply_text(
        "🛠 پنل مدیریت",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADMIN USERS
# =========================================================

async def admin_users(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "📊 مدیریت کاربران\n\n"
        "برای نمایش کامل کاربران، بهتر است از دیتابیس استفاده شود."
    )


# =========================================================
# ADD CHANNEL
# =========================================================

async def admin_add_channel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["admin_action"] = "add_channel"

    await update.message.reply_text(
        "➕ آیدی کانال را ارسال کن.\n\n"
        "مثال:\n"
        "@MyChannel\n\n"
        "ربات باید در کانال ادمین باشد."
    )


# =========================================================
# REMOVE CHANNEL
# =========================================================

async def admin_remove_channel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    channels = get_forced_channels()

    if not channels:

        await update.message.reply_text(
            "هیچ کانالی ثبت نشده."
        )

        return

    text = "➖ کانال‌های ثبت شده:\n\n"

    for channel in channels:

        protected = (
            "🔒 محافظت شده"
            if channel["protected"]
            else "قابل حذف"
        )

        text += (
            f"{channel['username']} - {protected}\n"
        )

    text += (
        "\nآیدی کانالی که می‌خواهی حذف شود را ارسال کن."
    )

    context.user_data["admin_action"] = "remove_channel"

    await update.message.reply_text(text)


# =========================================================
# ADMIN TEXT HANDLER
# =========================================================

async def admin_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    action = context.user_data.get(
        "admin_action"
    )

    if not action:
        return

    text = update.message.text.strip()

    # ADD CHANNEL
    if action == "add_channel":

        if not text.startswith("@"):

            await update.message.reply_text(
                "❌ فرمت اشتباه است.\n"
                "مثال: @MyChannel"
            )

            return

        try:

            chat = await context.bot.get_chat(text)

            bot_member = await context.bot.get_chat_member(
                chat_id=chat.id,
                user_id=context.bot.id
            )

            if bot_member.status not in (
                "administrator",
                "creator",
            ):

                await update.message.reply_text(
                    "❌ ربات در این کانال ادمین نیست."
                )

                return

            add_forced_channel(
                username=text,
                title=chat.title
            )

            await update.message.reply_text(
                f"✅ کانال {text} با موفقیت اضافه شد.",
                reply_markup=admin_keyboard()
            )

            context.user_data.pop(
                "admin_action",
                None
            )

        except Exception as e:

            logger.error(
                f"Could not add channel: {e}"
            )

            await update.message.reply_text(
                "❌ نتوانستم کانال را بررسی کنم.\n\n"
                "مطمئن شو آیدی درست است و ربات در کانال ادمین است."
            )

        return

    # REMOVE CHANNEL
    if action == "remove_channel":

        protected_channels = [
            "@Poneix",
            "@BET_1XZX",
        ]

        if text in protected_channels:

            await update.message.reply_text(
                "❌ این کانال محافظت شده است و حذف نمی‌شود."
            )

            return

        remove_forced_channel(text)

        await update.message.reply_text(
            f"✅ کانال {text} حذف شد.",
            reply_markup=admin_keyboard()
        )

        context.user_data.pop(
            "admin_action",
            None
        )


# =========================================================
# ORDER APPROVE / REJECT
# =========================================================

async def order_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != OWNER_ID:

        await query.answer(
            "❌ دسترسی ندارید.",
            show_alert=True
        )

        return

    parts = query.data.split(":")

    if len(parts) != 2:
        return

    action = parts[0]

    try:
        order_id = int(parts[1])
    except ValueError:
        return

    order = get_order(order_id)

    if not order:

        await query.edit_message_text(
            "❌ سفارش پیدا نشد."
        )

        return

    if order["status"] != "pending":

        await query.answer(
            "این سفارش قبلاً بررسی شده.",
            show_alert=True
        )

        return

    user_id = order["user_id"]

    if action == "approve":

        update_order_status(
            order_id,
            "approved"
        )

        await query.edit_message_text(
            query.message.text +
            "\n\n✅ سفارش تأیید شد."
        )

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉 درخواست شما تأیید شد.\n\n"
                    f"📦 محصول: {order['product']}\n"
                    f"👤 آیدی: {order['telegram_username']}\n\n"
                    "پرداخت/تحویل انجام شد."
                )
            )

        except Exception as e:

            logger.warning(
                f"Could not notify user: {e}"
            )

    elif action == "reject":

        update_order_status(
            order_id,
            "rejected"
        )

        # برگرداندن امتیاز در صورت رد شدن
        add_points(
            user_id,
            order["points"]
        )

        await query.edit_message_text(
            query.message.text +
            "\n\n❌ سفارش رد شد.\n"
            "⭐ امتیازها به کاربر برگشت داده شد."
        )

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ درخواست شما رد شد.\n\n"
                    f"📦 محصول: {order['product']}\n\n"
                    f"⭐ {order['points']} امتیاز "
                    "به حساب شما برگشت داده شد."
                )
            )

        except Exception as e:

            logger.warning(
                f"Could not notify rejected user: {e}"
            )


# =========================================================
# TEXT ROUTER
# =========================================================

async def text_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text

    # admin
    if update.effective_user.id == OWNER_ID:

        if text == "کاربران":

            await admin_users(
                update,
                context
            )

            return

        if text == "➕ افزودن کانال":

            await admin_add_channel(
                update,
                context
            )

            return

        if text == "➖ حذف کانال":

            await admin_remove_channel(
                update,
                context
            )

            return

        if text == "🔙 بازگشت":

            context.user_data.pop(
                "admin_action",
                None
            )

            await update.message.reply_text(
                "🔙 برگشتی به منوی اصلی.",
                reply_markup=main_keyboard()
            )

            return

        if context.user_data.get("admin_action"):

            await admin_text_handler(
                update,
                context
            )

            return

    # referral
    if text == "زیر مجموعه":

        await referral_menu(
            update,
            context
        )

        return

    # products
    if text in PRODUCTS:

        await product_menu(
            update,
            context
        )

        return

    # username waiting
    if context.user_data.get("pending_product"):

        await receive_username(
            update,
            context
        )

        return

    await update.message.reply_text(
        "یکی از گزینه‌های منو را انتخاب کن.",
        reply_markup=main_keyboard()
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Exception while handling update:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # ساخت جدول‌های PostgreSQL
    init_db()

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin_command)
    )

    # CAPTCHA
    application.add_handler(
        CallbackQueryHandler(
            captcha_callback,
            pattern=r"^captcha:"
        )
    )

    # Membership
    application.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern=r"^check_membership$"
        )
    )

    # Orders
    application.add_handler(
        CallbackQueryHandler(
            order_action,
            pattern=r"^(approve|reject):"
        )
    )

    # Text
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info("Bot started...")

    application.run_polling()


if __name__ == "__main__":
    main()
