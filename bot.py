import os
import random
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from supabase_db import (
    add_user,
    get_user,
    set_captcha_ok,
    set_joined_ok,
    get_points,
    remove_points,
    get_channels,
    add_channel,
    remove_channel,
    create_request,
    get_request,
    update_request,
    users_count
)


BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8291994828"))

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

captcha_answers = {}
waiting_for_username = {}
admin_waiting = {}

PRODUCTS = {
    "p3": {
        "name": "پریمیوم ۳ ماهه",
        "points": 30
    },
    "p6": {
        "name": "پریمیوم ۶ ماهه",
        "points": 50
    },
    "p12": {
        "name": "پریمیوم ۱۲ ماهه",
        "points": 90
    },
    "teddy": {
        "name": "گیفت تدی",
        "points": 12
    }
}

PROTECTED_CHANNELS = {
    "@Poneix",
    "https://t.me/BET_1XZX"
}


def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 زیرمجموعه",
                    callback_data="ref"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎁 پریمیوم ۳ ماهه",
                    callback_data="product:p3"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎁 پریمیوم ۶ ماهه",
                    callback_data="product:p6"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎁 پریمیوم ۱۲ ماهه",
                    callback_data="product:p12"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎁 گیفت تدی",
                    callback_data="product:teddy"
                )
            ]
        ]
    )


def captcha_keyboard(a, b):
    correct = a + b

    answers = [correct]

    while len(answers) < 3:
        x = random.randint(2, 40)

        if x not in answers:
            answers.append(x)

    random.shuffle(answers)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(x),
                    callback_data=f"captcha:{x}:{correct}"
                )
                for x in answers
            ]
        ]
    )


def join_keyboard():
    rows = []

    for channel in get_channels():
        rows.append([
            InlineKeyboardButton(
                text=f"📢 {channel['title']}",
                url=channel["chat_id"]
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="✅ بررسی عضویت",
            callback_data="check_join"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_captcha(message: Message):
    a = random.randint(1, 15)
    b = random.randint(1, 15)

    captcha_answers[message.from_user.id] = a + b

    await message.answer(
        "🛡 کپچا\n\n"
        f"حاصل عبارت زیر را انتخاب کن:\n\n"
        f"{a} + {b} = ?",
        reply_markup=captcha_keyboard(a, b)
    )


@dp.message(CommandStart())
async def start(message: Message):
    args = message.text.split()

    referred_by = None

    if len(args) > 1:
        try:
            referred_by = int(args[1])
        except ValueError:
            pass

    add_user(
        message.from_user.id,
        message.from_user.username,
        referred_by
    )

    user = get_user(message.from_user.id)

    if not user["captcha_ok"]:
        await send_captcha(message)
        return

    if not user["joined_ok"]:
        await message.answer(
            "📢 ابتدا در کانال‌های زیر عضو شو:",
            reply_markup=join_keyboard()
        )
        return

    await message.answer(
        "🎉 خوش اومدی!\n\n"
        f"⭐ امتیاز شما: {get_points(message.from_user.id)}",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data.startswith("captcha:"))
async def captcha_check(callback: CallbackQuery):
    _, answer, correct = callback.data.split(":")

    if int(answer) == int(correct):
        set_captcha_ok(callback.from_user.id)

        await callback.message.edit_text(
            "✅ کپچا با موفقیت تأیید شد.\n\n"
            "حالا در کانال‌های زیر عضو شو:",
            reply_markup=join_keyboard()
        )

    else:
        await callback.answer(
            "❌ جواب کپچا اشتباه است.",
            show_alert=True
        )


async def check_membership(user_id):
    for channel in get_channels():
        try:
            member = await bot.get_chat_member(
                channel["chat_id"],
                user_id
            )

            if member.status in ("left", "kicked"):
                return False

        except Exception:
            return False

    return True


@dp.callback_query(F.data == "check_join")
async def check_join(callback: CallbackQuery):
    if not await check_membership(callback.from_user.id):
        await callback.answer(
            "❌ هنوز در همه کانال‌ها عضو نشدی.",
            show_alert=True
        )
        return

    set_joined_ok(callback.from_user.id)

    await callback.message.edit_text(
        "✅ عضویت تأیید شد.\n\n"
        "از منوی زیر انتخاب کن:",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "ref")
async def referral(callback: CallbackQuery):
    me = await bot.get_me()

    link = (
        f"https://t.me/{me.username}"
        f"?start={callback.from_user.id}"
    )

    await callback.message.answer(
        "👥 زیرمجموعه\n\n"
        f"🔗 لینک دعوت شما:\n{link}\n\n"
        "هر دعوت موفق = ⭐ ۱ امتیاز\n\n"
        f"⭐ امتیاز فعلی: "
        f"{get_points(callback.from_user.id)}"
    )


@dp.callback_query(F.data.startswith("product:"))
async def product_click(callback: CallbackQuery):
    key = callback.data.split(":")[1]

    product = PRODUCTS[key]["name"]
    required = PRODUCTS[key]["points"]

    points = get_points(callback.from_user.id)

    if points < required:
        await callback.answer(
            f"برای این دکمه به {required} امتیاز نیاز دارید.",
            show_alert=True
        )

        await callback.message.answer(
            f"❌ برای {product} به {required} امتیاز نیاز دارید.\n\n"
            "🔗 لینک دعوت شما در دکمه «زیرمجموعه» قرار دارد."
        )

        return

    success = remove_points(
        callback.from_user.id,
        required
    )

    if not success:
        await callback.answer(
            "❌ امکان کسر امتیاز وجود ندارد.",
            show_alert=True
        )
        return

    waiting_for_username[callback.from_user.id] = {
        "product": product,
        "points": required
    }

    await callback.message.answer(
        f"✅ {required} امتیاز کسر شد.\n\n"
        "لطفاً آیدی تلگرام خودت را بفرست.\n"
        "مثال: @username"
    )


@dp.message()
async def username_handler(message: Message):
    user_id = message.from_user.id

    if user_id in waiting_for_username:
        username = message.text.strip()

        if not username.startswith("@"):
            username = "@" + username

        data = waiting_for_username.pop(user_id)

        request_id = create_request(
            user_id,
            username,
            data["product"],
            data["points"]
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ تأیید",
                        callback_data=f"approve:{request_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ رد",
                        callback_data=f"reject:{request_id}"
                    )
                ]
            ]
        )

        await bot.send_message(
            OWNER_ID,
            "📥 درخواست جدید\n\n"
            f"🆔 درخواست: #{request_id}\n"
            f"👤 آیدی: {username}\n"
            f"🆔 User ID: {user_id}\n"
            f"🎁 محصول: {data['product']}\n"
            f"⭐ امتیاز: {data['points']}",
            reply_markup=keyboard
        )

        await message.answer(
            "✅ درخواست شما ثبت شد.\n"
            "بعد از بررسی نتیجه برای شما ارسال می‌شود."
        )

        return

    if user_id == OWNER_ID:
        mode = admin_waiting.get(OWNER_ID)

        if mode and message.text:
            await process_admin_input(message, mode)


async def process_admin_input(message: Message, mode):
    link = message.text.strip()

    if mode == "add":
        try:
            chat = await bot.get_chat(link)

            me = await bot.get_me()

            member = await bot.get_chat_member(
                chat.id,
                me.id
            )

            if member.status not in (
                "administrator",
                "creator"
            ):
                await message.answer(
                    "❌ ربات در این کانال ادمین نیست."
                )
                return

            add_channel(
                link,
                chat.title or "Channel"
            )

            await message.answer(
                "✅ کانال با موفقیت اضافه شد."
            )

        except Exception:
            await message.answer(
                "❌ کانال ثبت نشد.\n"
                "لینک را بررسی کن و مطمئن شو ربات ادمین کانال است."
            )

    elif mode == "remove":
        if link in PROTECTED_CHANNELS:
            await message.answer(
                "❌ این کانال جزو کانال‌های اصلی است "
                "و حذف نمی‌شود."
            )
            return

        if remove_channel(link):
            await message.answer(
                "✅ کانال از جوین اجباری حذف شد."
            )
        else:
            await message.answer(
                "❌ کانال پیدا نشد یا قابل حذف نیست."
            )

    admin_waiting.pop(OWNER_ID, None)


@dp.callback_query(F.data.startswith("approve:"))
async def approve_request(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    request_id = int(callback.data.split(":")[1])
    request = get_request(request_id)

    if not request:
        await callback.answer("درخواست پیدا نشد.")
        return

    if request["status"] != "pending":
        await callback.answer("این درخواست قبلاً بررسی شده.")
        return

    update_request(request_id, "approved")

    await bot.send_message(
        request["user_id"],
        "✅ درخواست شما تأیید شد.\n\n"
        f"🎁 {request['product']}\n"
        "واریز/تحویل برای شما انجام شد."
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.answer("تأیید شد.")


@dp.callback_query(F.data.startswith("reject:"))
async def reject_request(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    request_id = int(callback.data.split(":")[1])
    request = get_request(request_id)

    if not request:
        await callback.answer("درخواست پیدا نشد.")
        return

    if request["status"] != "pending":
        await callback.answer("این درخواست قبلاً بررسی شده.")
        return

    update_request(request_id, "rejected")

    await bot.send_message(
        request["user_id"],
        "❌ درخواست شما رد شد.\n\n"
        f"🎁 {request['product']}"
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.answer("رد شد.")


@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 کاربران",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ افزودن جوین اجباری",
                    callback_data="add_join"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➖ حذف جوین اجباری",
                    callback_data="remove_join"
                )
            ]
        ]
    )

    await message.answer(
        "⚙️ پنل مدیریت",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    await callback.message.answer(
        f"👥 تعداد کاربران: {users_count()}"
    )


@dp.callback_query(F.data == "add_join")
async def add_join(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    admin_waiting[OWNER_ID] = "add"

    await callback.message.answer(
        "لینک کانال را بفرست.\n\n"
        "ربات باید در کانال ادمین باشد."
    )


@dp.callback_query(F.data == "remove_join")
async def remove_join(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    admin_waiting[OWNER_ID] = "remove"

    await callback.message.answer(
        "لینک کانالی که می‌خواهی حذف شود را بفرست."
    )


async def main():
    # دو کانال اولیه
    if not get_channels():
        add_channel("@Poneix", "Poneix")
        add_channel(
            "https://t.me/BET_1XZX",
            "BET"
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
