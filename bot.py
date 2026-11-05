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


BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(
    os.getenv("OWNER_ID", "8291994828")
)

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set"
    )


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


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


def is_admin(user_id):
    return user_id == OWNER_ID


async def start(update, context):

    user = update.effective_user

    referred_by = None

    if context.args:

        arg = context.args[0]

        if arg.startswith("ref_"):

            try:
                referred_by = int(
                    arg[4:]
                )
            except ValueError:
                referred_by = None

    if referred_by == user.id:
        referred_by = None

    old_user = get_user(user.id)

    if not old_user:

        create_user(
            user.id,
            user.username,
            referred_by,
        )

    else:

        create_user(
            user.id,
            user.username,
        )

    db_user = get_user(user.id)

    if (
        db_user
        and db_user["captcha_verified"]
        and db_user["membership_verified"]
    ):

        await update.message.reply_text(
            "👋 خوش اومدی!\n\n"
            "از منوی زیر استفاده کن:",
            reply_markup=main_keyboard(),
        )

        return

    if (
        db_user
        and db_user["captcha_verified"]
    ):

        await show_membership(
            update,
            context,
        )

        return

    await send_captcha(
        update,
        context,
    )


async def send_captcha(update, context):

    a = random.randint(1, 9)
    b = random.randint(1, 9)

    answer = a + b

    context.user_data[
        "captcha_answer"
    ] = answer

    choices = {
        answer,
        answer + 1,
        answer + 2,
        answer - 1,
    }

    choices = [
        x for x in choices
        if x >= 0
    ]

    random.shuffle(choices)

    keyboard = []

    row = []

    for number in choices:

        row.append(
            InlineKeyboardButton(
                str(number),
                callback_data=(
                    f"captcha:{number}"
                ),
            )
        )

        if len(row) == 2:

            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    await update.message.reply_text(
        f"🔐 کپچا\n\n"
        f"{a} + {b} = ؟\n\n"
        "جواب درست را انتخاب کن:",
        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        ),
    )


async def captcha_callback(update, context):

    query = update.callback_query

    await query.answer()

    selected = int(
        query.data.split(":")[1]
    )

    answer = context.user_data.get(
        "captcha_answer"
    )

    if selected != answer:

        await query.answer(
            "❌ جواب اشتباه است.",
            show_alert=True,
        )

        return

    user_id = query.from_user.id

    set_captcha_verified(
        user_id
    )

    context.user_data.pop(
        "captcha_answer",
        None,
    )

    referrer_id = reward_referrer(
        user_id
    )

    if referrer_id:

        try:

            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "🎉 زیرمجموعه جدید!\n\n"
                    "➕ ۱ امتیاز دریافت کردی."
                ),
            )

        except Exception:
            pass

    await query.edit_message_text(
        "✅ کپچا درست بود."
    )

    await show_membership(
        update,
        context,
    )


async def show_membership(update, context):

    channels = get_forced_channels()

    keyboard = []

    for channel in channels:

        username = channel["username"]

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📢 {username}",
                    url=(
                        "https://t.me/"
                        + username.lstrip("@")
                    ),
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "✅ بررسی عضویت",
                callback_data=(
                    "check_membership"
                ),
            )
        ]
    )

    markup = InlineKeyboardMarkup(
        keyboard
    )

    text = (
        "📢 برای استفاده از ربات "
        "باید در کانال‌های زیر عضو شوی:\n\n"
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

        try:

            member = await context.bot.get_chat_member(
                chat_id=channel["username"],
                user_id=user_id,
            )

            if member.status in (
                "left",
                "kicked",
            ):
                not_joined.append(
                    channel["username"]
                )

        except Exception as e:

            logger.error(
                "Membership error %s: %s",
                channel["username"],
                e,
            )

            not_joined.append(
                channel["username"]
            )

    if not_joined:

        await query.answer(
            "❌ هنوز عضو همه کانال‌ها نیستی.",
            show_alert=True,
        )

        return

    set_membership_verified(
        user_id
    )

    await query.edit_message_text(
        "✅ عضویت تأیید شد."
    )

    await query.message.reply_text(
        "🎉 ورود کامل شد.\n\n"
        "از منوی زیر استفاده کن:",
        reply_markup=main_keyboard(),
    )


async def referral_menu(update, context):

    user_id = update.effective_user.id

    user = get_user(user_id)

    if not user:
        return

    bot = await context.bot.get_me()

    link = (
        f"https://t.me/{bot.username}"
        f"?start=ref_{user_id}"
    )

    await update.message.reply_text(
        "👥 زیر مجموعه\n\n"
        f"⭐ امتیاز: {user['points']}\n"
        f"👤 دعوت موفق: "
        f"{user['referral_count']}\n\n"
        "🔗 لینک دعوت شما:\n"
        f"{link}\n\n"
        "هر دعوت موفق = ۱ امتیاز"
    )


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
            f"⭐ مورد نیاز: {required}\n\n"
            "برای گرفتن امتیاز بیشتر، "
            "از بخش «زیر مجموعه» استفاده کن."
        )

        return

    context.user_data[
        "pending_product"
    ] = product

    await update.message.reply_text(
        f"📦 محصول: {product}\n"
        f"⭐ هزینه: {required} امتیاز\n\n"
        "آیدی تلگرام خودت را بفرست.\n\n"
        "مثال:\n"
        "@username"
    )


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
            "❌ آیدی تلگرام معتبر نیست.\n\n"
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
            "❌ امتیاز کافی نیست."
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
        "⏳ برای ادمین ارسال شد."
    )

    text = (
        "📥 سفارش جدید\n\n"
        f"🆔 سفارش: #{order_id}\n"
        f"👤 User ID: "
        f"{update.effective_user.id}\n"
        f"📛 Username: "
        f"@{update.effective_user.username or 'ندارد'}\n"
        f"📦 محصول: {product}\n"
        f"⭐ هزینه: {points}\n"
        f"🎯 آیدی دریافت‌کننده: "
        f"{username}"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ تأیید",
                    callback_data=(
                        f"approve:{order_id}"
                    ),
                ),
                InlineKeyboardButton(
                    "❌ رد",
                    callback_data=(
                        f"reject:{order_id}"
                    ),
                ),
            ]
        ]
    )

    try:

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=text,
            reply_markup=keyboard,
        )

    except Exception as e:

        logger.error(
            "Sending order to owner failed: %s",
            e,
        )

    return True


async def admin_command(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        await update.message.reply_text(
            "❌ دسترسی ندارید."
        )
        return

    await update.message.reply_text(
        "⚙️ پنل مدیریت",
        reply_markup=admin_keyboard(),
    )


async def admin_users(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    users, points, pending = (
        get_user_stats()
    )

    await update.message.reply_text(
        "📊 آمار کاربران\n\n"
        f"👤 کاربران: {users}\n"
        f"⭐ مجموع امتیاز: {points}\n"
        f"📦 سفارش در انتظار: {pending}"
    )


async def admin_add_channel(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    context.user_data[
        "admin_action"
    ] = "add_channel"

    await update.message.reply_text(
        "➕ آیدی کانال را بفرست.\n\n"
        "مثال:\n"
        "@MyChannel\n\n"
        "ربات باید در کانال ادمین باشد."
    )


async def admin_remove_channel(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    channels = get_forced_channels()

    text = "📢 کانال‌های ثبت‌شده:\n\n"

    for channel in channels:

        status = (
            "🔒 محافظت‌شده"
            if channel["protected"]
            else "قابل حذف"
        )

        text += (
            f"{channel['username']} "
            f"- {status}\n"
        )

    text += (
        "\nآیدی کانال موردنظر را بفرست."
    )

    context.user_data[
        "admin_action"
    ] = "remove_channel"

    await update.message.reply_text(
        text
    )


async def admin_text_handler(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):
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

            bot = await context.bot.get_me()

            member = (
                await context.bot.get_chat_member(
                    chat_id=value,
                    user_id=bot.id,
                )
            )

            if member.status not in (
                "administrator",
                "creator",
            ):

                await update.message.reply_text(
                    "❌ ربات در کانال ادمین نیست."
                )

                return True

            chat = (
                await context.bot.get_chat(
                    value
                )
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
                "Add channel error: %s",
                e,
            )

            await update.message.reply_text(
                "❌ کانال پیدا نشد یا "
                "ربات ادمین نیست."
            )

        return True

    if action == "remove_channel":

        protected = {
            "@poneix",
            "@bet_1xzx",
        }

        if value.lower() in protected:

            await update.message.reply_text(
                "❌ این کانال قابل حذف نیست."
            )

            return True

        remove_forced_channel(
            value
        )

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


async def order_action(update, context):

    query = update.callback_query

    await query.answer()

    if not is_admin(
        query.from_user.id
    ):
        return

    action, order_id = (
        query.data.split(":")
    )

    order_id = int(order_id)

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
                    f"📦 محصول: "
                    f"{order['product']}\n"
                    f"🆔 سفارش: #{order_id}\n\n"
                    "✅ تحویل/پرداخت انجام شد."
                ),
            )

        except Exception:
            pass

    elif action == "reject":

        refunded = refund_order(
            order_id
        )

        if not refunded:
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
                    f"📦 محصول: "
                    f"{order['product']}\n"
                    f"🆔 سفارش: #{order_id}\n\n"
                    f"⭐ {order['points']} "
                    "امتیاز برگشت داده شد."
                ),
            )

        except Exception:
            pass


async def text_router(update, context):

    text = update.message.text

    if is_admin(
        update.effective_user.id
    ):

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

            context.user_data.clear()

            await update.message.reply_text(
                "🔙 برگشتی.",
                reply_markup=main_keyboard(),
            )

            return

        if await admin_text_handler(
            update,
            context
        ):
            return

    if text == "زیر مجموعه":

        await referral_menu(
            update,
            context
        )

        return

    if text in PRODUCTS:

        await product_menu(
            update,
            context
        )

        return

    if await receive_username(
        update,
        context
    ):
        return

    await update.message.reply_text(
        "یکی از گزینه‌های منو را انتخاب کن.",
        reply_markup=main_keyboard(),
    )


async def error_handler(update, context):

    logger.error(
        "Unhandled error:",
        exc_info=context.error
    )


def main():

    print(
        "🚀 BOT STARTING...",
        flush=True
    )

    init_db()

    print(
        "✅ DATABASE CONNECTED",
        flush=True
    )

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            captcha_callback,
            pattern=r"^captcha:"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern=(
                r"^check_membership$"
            )
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            order_action,
            pattern=(
                r"^(approve|reject):"
            )
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            text_router
        )
    )

    app.add_error_handler(
        error_handler
    )

    print(
        "🤖 BOT IS RUNNING...",
        flush=True
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
