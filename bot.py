import os
import re
import logging
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.constants import ChatMemberStatus
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


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8291994828"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


PRODUCTS = {
    "پریمیوم ۳ ماهه": 30,
    "پریمیوم ۶ ماهه": 50,
    "پریمیوم ۱۲ ماهه": 90,
    "گیفت تدی": 12,
}


def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["زیر مجموعه"],
            ["پریمیوم ۳ ماهه", "پریمیوم ۶ ماهه"],
            ["پریمیوم ۱۲ ماهه"],
            ["گیفت تدی"],
        ],
        resize_keyboard=True
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["کاربران"],
            ["➕ افزودن کانال", "➖ حذف کانال"],
        ],
        resize_keyboard=True
    )


def is_admin(user_id):
    return user_id == OWNER_ID


def referral_link(bot_username, user_id):
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    referred_by = None

    if context.args:
        arg = context.args[0]

        if arg.startswith("ref_"):
            try:
                referred_by = int(arg.replace("ref_", ""))
            except ValueError:
                referred_by = None

    if referred_by == user.id:
        referred_by = None

    existing = get_user(user.id)

    if not existing:
        create_user(
            user.id,
            user.username,
            referred_by
        )
    else:
        create_user(
            user.id,
            user.username,
            None
        )

    user_db = get_user(user.id)

    if user_db["captcha_verified"]:
        await show_membership(update, context)
        return

    await send_captcha(update, context)


async def send_captcha(update, context):
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    answer = a + b

    context.user_data["captcha_answer"] = answer

    keyboard = [
        [
            InlineKeyboardButton(
                str(answer),
                callback_data=f"captcha:{answer}"
            ),
            InlineKeyboardButton(
                str(answer + 1),
                callback_data=f"captcha:{answer + 1}"
            ),
            InlineKeyboardButton(
                str(answer + 2),
                callback_data=f"captcha:{answer + 2}"
            ),
        ],
        [
            InlineKeyboardButton(
                str(answer - 1),
                callback_data=f"captcha:{answer - 1}"
            ),
            InlineKeyboardButton(
                str(answer + 3),
                callback_data=f"captcha:{answer + 3}"
            ),
        ]
    ]

    text = (
        "🔐 کپچا\n\n"
        f"حاصل عبارت زیر چند است؟\n\n"
        f"{a} + {b} = ?\n\n"
        "جواب صحیح را انتخاب کنید."
    )

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text,
            reply_markup=markup
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=markup
        )


async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = int(query.data.split(":")[1])
    correct = context.user_data.get("captcha_answer")

    if selected != correct:
        await query.answer("❌ پاسخ اشتباه است", show_alert=True)
        return

    set_captcha_verified(query.from_user.id)

    context.user_data.pop("captcha_answer", None)

    await query.edit_message_text(
        "✅ کپچا با موفقیت انجام شد."
    )

    await show_membership(update, context)


async def show_membership(update, context):
    channels = get_forced_channels()

    keyboard = []

    for channel in channels:
        username = channel["username"]

        if username.startswith("@"):
            url = f"https://t.me/{username[1:]}"
        else:
            url = username

        keyboard.append([
            InlineKeyboardButton(
                f"📢 {channel['title'] or username}",
                url=url
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "✅ بررسی عضویت",
            callback_data="check_membership"
        )
    ])

    text = (
        "📢 برای استفاده از ربات، ابتدا در کانال‌های زیر عضو شوید:\n\n"
        "بعد از عضویت روی «بررسی عضویت» بزنید."
    )

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text,
            reply_markup=markup
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=markup
        )


async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    channels = get_forced_channels()

    not_joined = []

    for channel in channels:
        try:
            member = await context.bot.get_chat_member(
                channel["username"],
                user_id
            )

            if member.status in (
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
            ):
                not_joined.append(channel["username"])

        except Exception as e:
            logger.error(
                "Membership check failed for %s: %s",
                channel["username"],
                e
            )
            not_joined.append(channel["username"])

    if not_joined:
        await query.answer(
            "❌ هنوز در همه کانال‌ها عضو نیستی.",
            show_alert=True
        )
        return

    set_membership_verified(user_id)

    # امتیاز معرف فقط بعد از کپچا + عضویت داده می‌شود.
    referrer_id = reward_referrer(user_id)

    if referrer_id:
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "🎉 یک زیرمجموعه جدید داری!\n\n"
                    "✅ ۱ امتیاز به حساب شما اضافه شد."
                )
            )
        except Exception:
            pass

    await query.edit_message_text(
        "✅ عضویت شما تأیید شد.\n\n"
        "به منوی اصلی خوش آمدید."
    )

    await query.message.reply_text(
        "یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_keyboard()
    )


async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        me = await context.bot.get_me()
        link = referral_link(me.username, user.id)
    except Exception:
        link = "خطا در ساخت لینک"

    db_user = get_user(user.id)

    points = db_user["points"] if db_user else 0
    count = db_user["referral_count"] if db_user else 0

    text = (
        "👥 بخش زیرمجموعه\n\n"
        f"👤 تعداد زیرمجموعه موفق: {count}\n"
        f"⭐ امتیاز شما: {points}\n\n"
        "🔗 لینک اختصاصی شما:\n"
        f"{link}\n\n"
        "هر زیرمجموعه‌ای که کپچا را انجام دهد و عضو کانال‌های اجباری شود، "
        "۱ امتیاز برای شما ثبت می‌کند."
    )

    await update.message.reply_text(text)


async def product_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text not in PRODUCTS:
        return

    user_id = update.effective_user.id
    required = PRODUCTS[text]
    points = get_points(user_id)

    if points < required:
        await update.message.reply_text(
            f"❌ امتیاز کافی ندارید.\n\n"
            f"💰 امتیاز فعلی: {points}\n"
            f"⭐ امتیاز مورد نیاز: {required}\n\n"
            "برای دریافت امتیاز بیشتر از بخش «زیر مجموعه» استفاده کنید."
        )
        return

    context.user_data["pending_product"] = text

    await update.message.reply_text(
        f"🛒 محصول: {text}\n"
        f"⭐ قیمت: {required} امتیاز\n\n"
        "حالا آیدی تلگرام خود را ارسال کنید.\n"
        "مثال:\n"
        "@username"
    )


async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_product" not in context.user_data:
        return False

    username = update.message.text.strip()

    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", username):
        await update.message.reply_text(
            "❌ آیدی تلگرام نامعتبر است.\n\n"
            "مثال صحیح:\n"
            "@username"
        )
        return True

    product = context.user_data["pending_product"]
    points = PRODUCTS[product]

    order_id = create_order(
        update.effective_user.id,
        product,
        points,
        username
    )

    if not order_id:
        context.user_data.pop("pending_product", None)

        await update.message.reply_text(
            "❌ امتیاز شما دیگر کافی نیست."
        )
        return True

    context.user_data.pop("pending_product", None)

    await update.message.reply_text(
        "✅ سفارش شما ثبت شد.\n\n"
        f"🛒 محصول: {product}\n"
        f"⭐ هزینه: {points} امتیاز\n"
        f"📦 شماره سفارش: #{order_id}\n\n"
        "⏳ سفارش برای بررسی ادمین ارسال شد."
    )

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=(
            "🔔 سفارش جدید\n\n"
            f"📦 سفارش: #{order_id}\n"
            f"👤 کاربر: {update.effective_user.id}\n"
            f"🆔 آیدی: @{update.effective_user.username or 'ندارد'}\n"
            f"📨 دریافت‌کننده: {username}\n"
            f"🛒 محصول: {product}\n"
            f"⭐ امتیاز: {points}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ تأیید",
                    callback_data=f"approve:{order_id}"
                ),
                InlineKeyboardButton(
                    "❌ رد",
                    callback_data=f"reject:{order_id}"
                ),
            ]
        ])
    )

    return True


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "⚙️ پنل مدیریت",
        reply_markup=admin_keyboard()
    )


async def users_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    users, points, pending = get_user_stats()

    await update.message.reply_text(
        "👥 آمار کاربران\n\n"
        f"👤 تعداد کاربران: {users}\n"
        f"⭐ مجموع امتیازها: {points}\n"
        f"📦 سفارش‌های در انتظار: {pending}"
    )


async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    context.user_data["admin_action"] = "add_channel"

    await update.message.reply_text(
        "📢 یوزرنیم کانال را ارسال کنید.\n\n"
        "مثال:\n"
        "@MyChannel\n\n"
        "⚠️ ربات باید در کانال ادمین باشد."
    )


async def remove_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    channels = get_forced_channels()

    text = "📢 کانال‌های ثبت‌شده:\n\n"

    for channel in channels:
        protected = "🔒" if channel["protected"] else "🗑"
        text += f"{protected} {channel['username']}\n"

    text += (
        "\nبرای حذف یک کانال، یوزرنیم آن را ارسال کنید."
    )

    context.user_data["admin_action"] = "remove_channel"

    await update.message.reply_text(text)


async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return False

    action = context.user_data.get("admin_action")

    if not action:
        return False

    value = update.message.text.strip()

    if action == "add_channel":

        if not value.startswith("@"):
            await update.message.reply_text(
                "❌ یوزرنیم باید با @ شروع شود."
            )
            return True

        try:
            me = await context.bot.get_me()

            member = await context.bot.get_chat_member(
                value,
                me.id
            )

            if member.status not in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ):
                await update.message.reply_text(
                    "❌ ربات در این کانال ادمین نیست."
                )
                return True

            chat = await context.bot.get_chat(value)

            add_forced_channel(
                value,
                chat.title
            )

            context.user_data.pop("admin_action", None)

            await update.message.reply_text(
                f"✅ کانال {value} با موفقیت اضافه شد.",
                reply_markup=admin_keyboard()
            )

        except Exception as e:
            logger.error("Add channel error: %s", e)

            await update.message.reply_text(
                "❌ کانال پیدا نشد یا ربات در آن ادمین نیست."
            )

        return True

    if action == "remove_channel":

        if value.lower() in (
            "@poneix",
            "@bet_1xzx"
        ):
            await update.message.reply_text(
                "❌ این دو کانال اصلی قابل حذف نیستند."
            )
            return True

        remove_forced_channel(value)

        context.user_data.pop("admin_action", None)

        await update.message.reply_text(
            f"✅ کانال {value} حذف شد.",
            reply_markup=admin_keyboard()
        )

        return True

    return False


async def order_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        await query.answer(
            "دسترسی ندارید.",
            show_alert=True
        )
        return

    action, order_id_str = query.data.split(":")
    order_id = int(order_id_str)

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

    if action == "approve":

        update_order_status(
            order_id,
            "approved"
        )

        await query.edit_message_text(
            f"✅ سفارش #{order_id} تأیید شد."
        )

        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    "🎉 سفارش شما تأیید شد.\n\n"
                    f"📦 سفارش: #{order_id}\n"
                    f"🛒 محصول: {order['product']}\n\n"
                    "✅ پرداخت/تحویل شما توسط ادمین تأیید شد."
                )
            )
        except Exception as e:
            logger.error("Send approval message failed: %s", e)

    elif action == "reject":

        refunded = refund_order(order_id)

        if refunded:
            await query.edit_message_text(
                f"❌ سفارش #{order_id} رد شد.\n"
                "⭐ امتیازها به کاربر برگشت داده شد."
            )

            try:
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text=(
                        "❌ سفارش شما رد شد.\n\n"
                        f"📦 سفارش: #{order_id}\n"
                        f"🛒 محصول: {order['product']}\n\n"
                        "⭐ امتیازهای شما به حسابتان برگشت داده شد."
                    )
                )
            except Exception as e:
                logger.error("Send rejection message failed: %s", e)


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if is_admin(update.effective_user.id):

        if text == "کاربران":
            await users_info(update, context)
            return

        if text == "➕ افزودن کانال":
            await add_channel_start(update, context)
            return

        if text == "➖ حذف کانال":
            await remove_channel_start(update, context)
            return

        if await admin_text(update, context):
            return

    if text == "زیر مجموعه":
        await show_referral(update, context)
        return

    if text in PRODUCTS:
        await product_menu(update, context)
        return

    if await receive_username(update, context):
        return

    if text == "/admin":
        await admin_panel(update, context)
        return


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(
        "Unhandled exception:",
        exc_info=context.error
    )


def main():
    init_db()

    print("DATABASE OK")
    print("BOT TOKEN OK")
    print("STARTING POLLING...")

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin_panel)
    )

    application.add_handler(
        CallbackQueryHandler(
            captcha_callback,
            pattern=r"^captcha:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern=r"^check_membership$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            order_action,
            pattern=r"^(approve|reject):"
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router
        )
    )

    application.add_error_handler(error_handler)

    print("BOT IS RUNNING...")

    application.run_polling()


if __name__ == "__main__":
    main()
