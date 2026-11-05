import os
import random
import asyncio
import logging

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from database import (
    init_db,
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
    update_request,
    get_request,
    users_count
)


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8291994828"))

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

captcha_answers = {}

PRODUCTS = {
    "p3": ("پریمیوم ۳ ماهه", 30),
    "p6": ("پریمیوم ۶ ماهه", 50),
    "p12": ("پریمیوم ۱۲ ماهه", 90),
    "teddy": ("گیفت تدی", 12),
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
        x = random.randint(5, 30)
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
        f"🛡 کپچا\n\n"
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
        except:
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
            "برای استفاده از ربات ابتدا در کانال‌های زیر عضو شو:",
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
            "✅ کپچا درست بود.\n\n"
            "حالا در کانال‌های زیر عضو شو:",
            reply_markup=join_keyboard()
        )

    else:
        await callback.answer(
            "❌ جواب اشتباهه!",
            show_alert=True
        )


async def check_membership(user_id):
    channels = get_channels()

    for channel in channels:
        try:
            member = await bot.get_chat_member(
                channel["chat_id"],
                user_id
            )

            if member.status in ["left", "kicked"]:
                return False

        except Exception:
            return False

    return True


@dp.callback_query(F.data == "check_join")
async def check_join(callback: CallbackQuery):
    ok = await check_membership(callback.from_user.id)

    if not ok:
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

    link = f"https://t.me/{me.username}?start={callback.from_user.id}"

    points = get_points(callback.from_user.id)

    await callback.message.answer(
        "👥 سیستم زیرمجموعه\n\n"
        f"🔗 لینک دعوت شما:\n{link}\n\n"
        "هر دعوت موفق = ⭐ ۱ امتیاز\n\n"
        f"⭐ امتیاز فعلی: {points}"
    )


@dp.callback_query(F.data.startswith("product:"))
async def product_click(callback: CallbackQuery):
    key = callback.data.split(":")[1]

    product, required_points = PRODUCTS[key]

    points = get_points(callback.from_user.id)

    if points < required_points:
        await callback.answer(
            f"❌ برای این دکمه به {required_points} امتیاز نیاز دارید.",
            show_alert=True
        )

        await callback.message.answer(
            f"❌ برای {product} به {required_points} امتیاز نیاز دارید.\n\n"
            "🔗 لینک دعوت شما در بخش «زیرمجموعه» قرار دارد."
        )

        return

    remove_points(callback.from_user.id, required_points)

    await callback.message.answer(
        f"✅ {required_points} امتیاز از حساب شما کسر شد.\n\n"
        "لطفاً آیدی تلگرام خود را ارسال کنید.\n"
        "مثال:\n"
        "`@username`",
        parse_mode="Markdown"
    )

    await callback.message.answer(
        "لطفاً آیدی را در یک پیام جداگانه ارسال کن."
    )

    # ذخیره وضعیت انتظار
    waiting_for_username[callback.from_user.id] = {
        "product": product,
        "points": required_points
    }


waiting_for_username = {}


@dp.message()
async def username_handler(message: Message):
    user_id = message.from_user.id

    if user_id not in waiting_for_username:
        return

    username = message.text.strip()

    if not username.startswith("@"):
        username = "@" + username

    data = waiting_for_username.pop(user_id)

    request_id = create_request(
        user_id=user_id,
        username=username,
        product=data["product"],
        points=data["points"]
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
        f"👤 کاربر: {username}\n"
        f"🆔 Telegram ID: `{user_id}`\n"
        f"🎁 محصول: {data['product']}\n"
        f"⭐ امتیاز کسر شده: {data['points']}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    await message.answer(
        "✅ درخواست شما ثبت شد.\n\n"
        "درخواست برای مدیریت ارسال شد. پس از بررسی نتیجه به شما اعلام می‌شود."
    )


@dp.callback_query(F.data.startswith("approve:"))
async def approve(callback: CallbackQuery):
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
        f"✅ درخواست شما تأیید شد.\n\n"
        f"🎁 {request['product']}\n"
        "واریز/تحویل برای شما انجام شد."
    )

    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.answer("درخواست تأیید شد.")


@dp.callback_query(F.data.startswith("reject:"))
async def reject(callback: CallbackQuery):
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
        f"❌ درخواست شما رد شد.\n\n"
        f"🎁 {request['product']}"
    )

    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.answer("درخواست رد شد.")


# -------------------------
# ADMIN
# -------------------------

@dp.message(Command("admin"))
async def admin(message: Message):
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


admin_waiting = {}


@dp.callback_query(F.data == "add_join")
async def add_join_start(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    admin_waiting[OWNER_ID] = "add"

    await callback.message.answer(
        "لینک کانال را ارسال کن.\n\n"
        "مثال:\n"
        "https://t.me/example"
    )


@dp.callback_query(F.data == "remove_join")
async def remove_join_start(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return

    admin_waiting[OWNER_ID] = "remove"

    channels = get_channels()

    if not channels:
        await callback.message.answer("کانال اجباری دیگری وجود ندارد.")
        return

    text = "کانالی که می‌خواهی حذف کنی را با لینک ارسال کن:\n\n"

    for ch in channels:
        text += f"{ch['title']} - {ch['chat_id']}\n"

    await callback.message.answer(text)


@dp.message(F.text.startswith("https://t.me/"))
async def channel_handler(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    mode = admin_waiting.get(OWNER_ID)

    if not mode:
        return

    link = message.text.strip()

    if mode == "add":
        try:
            chat = await bot.get_chat(link)

            member = await bot.get_chat_member(
                chat.id,
                (await bot.get_me()).id
            )

            if member.status not in ["administrator", "creator"]:
                await message.answer(
                    "❌ ربات در این کانال ادمین نیست.\n"
                    "اول ربات را ادمین کن."
                )
                return

            add_channel(
                link,
                chat.title or "Channel"
            )

            await message.answer(
                "✅ کانال با موفقیت به جوین اجباری اضافه شد."
            )

        except Exception as e:
            await message.answer(
                "❌ کانال قابل ثبت نیست.\n"
                "مطمئن شو لینک درست است و ربات داخل کانال ادمین است."
            )

    elif mode == "remove":
        # کانال‌های اولیه حذف نمی‌شوند
        protected = {
            "@Poneix",
            "https://t.me/BET_1XZX"
        }

        if link in protected:
            await message.answer(
                "❌ این کانال جزو جوین‌های اجباری اصلی است و حذف نمی‌شود."
            )
            return

        remove_channel(link)

        await message.answer(
            "✅ کانال از جوین اجباری حذف شد."
        )

    admin_waiting.pop(OWNER_ID, None)


async def main():
    init_db()

    # کانال‌های اولیه
    add_channel("@Poneix", "Poneix")
    add_channel("https://t.me/BET_1XZX", "BET")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
