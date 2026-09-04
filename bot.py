import asyncio
import html
import logging
import os
import random

from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from db import Database

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv(
        "ADMIN_IDS",
        "",
    ).split(",")
    if x.strip().isdigit()
}

MAX_PHOTOS = 5
MAX_FACTS_LENGTH = 500
MAX_ADVICE_LENGTH = 500
MAX_REPORT_LENGTH = 1000

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger("dating_bot")

db = Database()

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================================================
# RATING TABLES
# =========================================================

MEN_TABLE = [
    ("sub 3", 1.0),
    ("sub 5", 2.5),
    ("ltn", 4.0),
    ("mtn", 5.5),
    ("htn", 7.0),
    ("chad", 8.5),
    ("true adam", 10.0),
]

WOMEN_TABLE = [
    ("sub 3", 1.0),
    ("sub 5", 2.5),
    ("ltb", 4.0),
    ("mtb", 5.5),
    ("htb", 7.0),
    ("stacy", 8.5),
    ("true eve", 10.0),
]

MEN_TABLE_IMAGE = (
    "https://raw.githubusercontent.com/"
    "dbmpwddcsj-create/photo/"
    "b210ff5eeae904c276ea9d49d6f365d6e527397d/"
    "IMG_1423.jpeg"
)

WOMEN_TABLE_IMAGE = (
    "https://raw.githubusercontent.com/"
    "dbmpwddcsj-create/photo/"
    "c0d698287fc20b14c88fb34edbb7401c8856cc1e/"
    "IMG_1424.jpeg"
)

def get_table_for_gender(gender):
    if gender == "female":
        return WOMEN_TABLE
    return MEN_TABLE

def get_table_image_for_gender(gender):
    if gender == "female":
        return WOMEN_TABLE_IMAGE
    return MEN_TABLE_IMAGE

def get_table_category_from_look_type(look_type):
    if not look_type:
        return None
    look_type = str(look_type)
    if look_type.startswith("table:"):
        return look_type.split(":", 1)[1]
    return None

def format_rating_row(rating, target_gender=None):
    if not rating:
        return None
    look_type = rating.get("look_type")
    category = get_table_category_from_look_type(look_type)
    if category:
        return category
    try:
        score = float(rating.get("score", 0))
        return f"{score:g}/10"
    except (TypeError, ValueError):
        return None

# =========================================================
# FSM
# =========================================================

class Registration(StatesGroup):
    age = State()
    gender = State()

class ProfileCreation(StatesGroup):
    photo = State()
    facts = State()
    height = State()
    weight = State()

class ProfileEdit(StatesGroup):
    age = State()
    gender = State()
    photos = State()

class Rating(StatesGroup):
    score = State()
    confirm_change = State()

class Report(StatesGroup):
    reason = State()

class Advice(StatesGroup):
    text = State()

class Broadcast(StatesGroup):
    message = State()

# =========================================================
# MESSAGE HELPERS
# =========================================================

async def safe_delete_message(chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception:
        logger.exception("Failed to delete message")

async def delete_by_ids(chat_id, message_ids):
    for message_id in message_ids or []:
        await safe_delete_message(chat_id, message_id)

async def clear_bot_messages(chat_id, state):
    data = await state.get_data()
    message_ids = data.get("bot_message_ids", [])
    await delete_by_ids(chat_id, message_ids)
    await state.update_data(bot_message_ids=[])

async def remember_bot_message(state, message):
    data = await state.get_data()
    ids = list(data.get("bot_message_ids", []))
    ids.append(message.message_id)
    await state.update_data(bot_message_ids=ids)

# =========================================================
# KEYBOARDS
# =========================================================

def rules_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принимаю правила", callback_data="agree")]
    ])

def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оценивать анкеты", callback_data="menu_rate")],
        [InlineKeyboardButton(text="👤 Моя анкета", callback_data="my_profile")],
        [InlineKeyboardButton(text="➕ Создать анкету", callback_data="create_profile")],
    ])

def rating_mode_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Оценка 1–10", callback_data="rating_mode:score")],
        [InlineKeyboardButton(text="📊 По таблице", callback_data="rating_mode:table")],
        [InlineKeyboardButton(text="🔀 Смешанный режим", callback_data="rating_mode:both")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

def score_keyboard(show_table=False):
    buttons = [
        [
            InlineKeyboardButton(text="1", callback_data="score:1"),
            InlineKeyboardButton(text="2", callback_data="score:2"),
            InlineKeyboardButton(text="3", callback_data="score:3"),
            InlineKeyboardButton(text="4", callback_data="score:4"),
            InlineKeyboardButton(text="5", callback_data="score:5"),
        ],
        [
            InlineKeyboardButton(text="6", callback_data="score:6"),
            InlineKeyboardButton(text="7", callback_data="score:7"),
            InlineKeyboardButton(text="8", callback_data="score:8"),
            InlineKeyboardButton(text="9", callback_data="score:9"),
            InlineKeyboardButton(text="10", callback_data="score:10"),
        ],
    ]
    if show_table:
        buttons.append([InlineKeyboardButton(text="📊 Посмотреть таблицу", callback_data="view_rating_table")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rating")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def table_keyboard(gender):
    table = get_table_for_gender(gender)
    buttons = []
    for index, (name, _) in enumerate(table):
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"table_score:{index}")])
    buttons.append([InlineKeyboardButton(text="📊 Посмотреть таблицу", callback_data="view_rating_table")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rating")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def mixed_rating_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Оценка 1–10", callback_data="mixed_score")],
        [InlineKeyboardButton(text="📊 Оценить по таблице", callback_data="mixed_table")],
        [InlineKeyboardButton(text="📊 Посмотреть таблицу", callback_data="view_rating_table")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rating")],
    ])

def rating_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оценить", callback_data="enter_score")],
        [InlineKeyboardButton(text="❤️ Познакомиться", callback_data="like_current")],
        [InlineKeyboardButton(text="💬 Совет по улучшению внешности", callback_data="add_advice")],
        [InlineKeyboardButton(text="📊 Посмотреть таблицу", callback_data="view_rating_table")],
        [InlineKeyboardButton(text="➡️ Следующая", callback_data="next_profile")],
        [InlineKeyboardButton(text="🚩 Жалоба", callback_data="report_current")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

def score_only_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оценить", callback_data="enter_score")],
        [InlineKeyboardButton(text="➡️ Следующая", callback_data="next_profile")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

def table_only_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Оценить по таблице", callback_data="enter_score")],
        [InlineKeyboardButton(text="📊 Посмотреть таблицу", callback_data="view_rating_table")],
        [InlineKeyboardButton(text="➡️ Следующая", callback_data="next_profile")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

def after_rating_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ Познакомиться", callback_data="like_current")],
        [InlineKeyboardButton(text="💬 Совет по улучшению внешности", callback_data="add_advice")],
        [InlineKeyboardButton(text="➡️ Следующая", callback_data="next_profile")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

def confirm_change_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Изменить оценку", callback_data="confirm_change")],
        [InlineKeyboardButton(text="↩️ Оставить старую", callback_data="cancel_rating")],
    ])

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить анкету", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🗑 Удалить анкету", callback_data="delete_profile")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

def edit_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎂 Изменить возраст", callback_data="edit_age")],
        [InlineKeyboardButton(text="⚧ Изменить пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="📸 Изменить фото", callback_data="edit_photos")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="my_profile")],
    ])

def advice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Посмотреть анкету", callback_data="advice_view_profile")]
    ])

def advice_return_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться к совету", callback_data="advice_back")]
    ])

def report_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_report")]
    ])

# Новая клавиатура для админа при жалобе
def admin_report_keyboard(target_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Посмотреть анкету", callback_data=f"admin_view_profile:{target_id}"),
            InlineKeyboardButton(text="🗑 Удалить анкету", callback_data=f"admin_delete_profile:{target_id}")
        ]
    ])

# =========================================================
# TEXT
# =========================================================

def gender_text(gender):
    if gender == "male":
        return "Мужчина"
    if gender == "female":
        return "Девушка"
    return "Не указан"

def build_profile_text(user, profile, average, count):
    age = user.get("age")
    lines = ["👤 <b>Анкета</b>", ""]
    if age:
        lines.append(f"🎂 Возраст: <b>{age}</b>")
    lines.append(f"⚧ Пол: <b>{gender_text(user.get('gender'))}</b>")
    height = profile.get("height")
    if height:
        lines.append(f"📏 Рост: <b>{height:g} см</b>")
    weight = profile.get("weight")
    if weight:
        lines.append(f"⚖️ Вес: <b>{weight:g} кг</b>")
    facts = profile.get("facts")
    if facts:
        lines.extend(["", "📝 <b>О себе:</b>", html.escape(str(facts))])
    if count:
        lines.extend(["", f"⭐ Рейтинг: <b>{average:.1f}/10</b>", f"👥 Оценок: <b>{count}</b>"])
    return "\n".join(lines)

# =========================================================
# USER / REGISTRATION
# =========================================================

async def ensure_user(message):
    user, is_new = await db.ensure_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    if is_new:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    (
                        "👤 <b>Новый пользователь</b>\n\n"
                        f"ID: <code>{message.from_user.id}</code>\n"
                        f"Username: @{message.from_user.username}"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to notify admin")
    return user

async def is_registered(user_id):
    user = await db.get_user(user_id)
    return bool(user and user.get("accepted_rules"))

async def require_registration(callback):
    if not await is_registered(callback.from_user.id):
        await callback.answer("Сначала пройди регистрацию.", show_alert=True)
        return False
    return True

# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = await ensure_user(message)
    if not user.get("accepted_rules"):
        await message.answer(
            "👋 <b>Добро пожаловать!</b>\n\nПеред использованием бота необходимо принять правила.",
            reply_markup=rules_keyboard(),
            parse_mode="HTML",
        )
        return
    if not user.get("age"):
        await message.answer("🎂 Укажи свой возраст:")
        await state.set_state(Registration.age)
        return
    if not user.get("gender"):
        await message.answer("⚧ Укажи свой пол:\n\nМужчина / Девушка")
        await state.set_state(Registration.gender)
        return
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "agree")
async def agree(callback: CallbackQuery, state: FSMContext):
    await db.update_user(callback.from_user.id, {"accepted_rules": True})
    await callback.message.edit_text("🎂 Укажи свой возраст:")
    await state.set_state(Registration.age)
    await callback.answer()

@dp.message(Registration.age)
async def registration_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("Введи возраст числом.")
        return
    if not 18 <= age <= 100:
        await message.answer("Возраст должен быть от 18 до 100 лет.")
        return
    await db.update_user_age(message.from_user.id, age)
    await message.answer("⚧ Укажи свой пол:\n\nМужчина / Девушка")
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def registration_gender(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    if text in ("мужчина", "мужской", "м", "male"):
        gender = "male"
    elif text in ("девушка", "женщина", "женский", "ж", "female"):
        gender = "female"
    else:
        await message.answer("Напиши: Мужчина или Девушка.")
        return
    await db.update_user_gender(message.from_user.id, gender)
    await state.clear()
    await message.answer("Регистрация завершена.", reply_markup=main_menu_keyboard())

# =========================================================
# MAIN MENU
# =========================================================

@dp.callback_query(F.data == "back_menu")
async def back_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await clear_bot_messages(callback.message.chat.id, state)
    try:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu_keyboard())
    except TelegramBadRequest:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()

# =========================================================
# PROFILE CREATION
# =========================================================

@dp.callback_query(F.data == "create_profile")
async def create_profile_start(callback: CallbackQuery, state: FSMContext):
    if not await require_registration(callback):
        return
    await state.clear()
    await state.update_data(photos=[])
    await state.set_state(ProfileCreation.photo)
    await callback.message.edit_text(
        f"📸 Отправь фотографию для анкеты.\n\nМожно добавить до {MAX_PHOTOS} фотографий.\nКогда закончишь — нажми «Готово».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]
        ]),
    )
    await callback.answer()

@dp.message(ProfileCreation.photo, F.photo)
async def profile_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get("photos", []))
    if len(photos) >= MAX_PHOTOS:
        await message.answer(f"Можно добавить максимум {MAX_PHOTOS} фотографий.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"📸 Фото добавлено: {len(photos)}/{MAX_PHOTOS}\n\nМожешь отправить ещё или нажать «Готово».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]
        ]),
    )

@dp.callback_query(F.data == "photos_done", ProfileCreation.photo)
async def photos_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.answer("Нужно добавить хотя бы одно фото.", show_alert=True)
        return
    await callback.message.edit_text(
        "📝 Напиши несколько фактов о себе.\nДо 500 символов.\n\nМожно написать «пропустить»."
    )
    await state.set_state(ProfileCreation.facts)
    await callback.answer()

@dp.message(ProfileCreation.facts)
async def profile_facts(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() in ("пропустить", "skip"):
        text = None
    elif len(text) > MAX_FACTS_LENGTH:
        await message.answer(f"Максимум {MAX_FACTS_LENGTH} символов.")
        return
    await state.update_data(facts=text)
    await message.answer("📏 Укажи рост в сантиметрах.\nНапример: 180")
    await state.set_state(ProfileCreation.height)

@dp.message(ProfileCreation.height)
async def profile_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.strip().replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Введи рост числом.")
        return
    if not 100 <= height <= 250:
        await message.answer("Рост должен быть от 100 до 250 см.")
        return
    await state.update_data(height=height)
    await message.answer("⚖️ Укажи вес в килограммах.\nНапример: 75")
    await state.set_state(ProfileCreation.weight)

@dp.message(ProfileCreation.weight)
async def profile_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.strip().replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Введи вес числом.")
        return
    if not 30 <= weight <= 300:
        await message.answer("Вес должен быть от 30 до 300 кг.")
        return
    await state.update_data(weight=weight)
    await save_profile_from_state(message, state)

async def save_profile_from_state(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    await db.create_profile(
        telegram_id=message.from_user.id,
        photo_id=photos[0],
        photo_ids=photos,
        facts=data.get("facts"),
        height=data.get("height"),
        weight=data.get("weight"),
    )
    await state.clear()
    await message.answer("✅ Анкета сохранена.", reply_markup=main_menu_keyboard())

# =========================================================
# SEND PROFILE
# =========================================================

async def send_profile(chat_id, user, profile, state=None, public=False, public_return_callback=None):
    average = await db.get_average_rating(user["telegram_id"])
    count = await db.get_rating_count(user["telegram_id"])
    text = build_profile_text(user, profile, average, count)
    photos = await db.get_profile_photos(user["telegram_id"])
    message_ids = []

    if photos:
        if len(photos) == 1:
            msg = await bot.send_photo(chat_id, photos[0], caption=text, parse_mode="HTML")
            message_ids.append(msg.message_id)
        else:
            media = []
            for index, photo_id in enumerate(photos[:MAX_PHOTOS]):
                media.append(
                    InputMediaPhoto(
                        media=photo_id,
                        caption=text if index == 0 else None,
                        parse_mode="HTML" if index == 0 else None,
                    )
                )
            messages = await bot.send_media_group(chat_id, media)
            message_ids.extend(msg.message_id for msg in messages)
    else:
        msg = await bot.send_message(chat_id, text, parse_mode="HTML")
        message_ids.append(msg.message_id)

    if public:
        if public_return_callback:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Вернуться", callback_data=public_return_callback)]
            ])
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")]
            ])
        control = await bot.send_message(chat_id, "👤 Анкета пользователя:", reply_markup=keyboard)
    else:
        control = await bot.send_message(chat_id, "Управление анкетой:", reply_markup=profile_keyboard())

    message_ids.append(control.message_id)
    if state:
        await state.update_data(bot_message_ids=message_ids)
    return message_ids

# =========================================================
# MY PROFILE
# =========================================================

@dp.callback_query(F.data == "my_profile")
async def my_profile(callback: CallbackQuery, state: FSMContext):
    if not await require_registration(callback):
        return
    profile = await db.get_profile(callback.from_user.id)
    if not profile:
        try:
            await callback.message.edit_text(
                "У тебя пока нет анкеты.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Создать анкету", callback_data="create_profile")],
                    [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
                ]),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return
    if profile.get("status") == "deleted":
        try:
            await callback.message.edit_text(
                "Твоя анкета удалена.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="♻️ Восстановить", callback_data="restore_profile")],
                    [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
                ]),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return
    user = await db.get_user(callback.from_user.id)
    await clear_bot_messages(callback.message.chat.id, state)
    await send_profile(callback.message.chat.id, user, profile, state=state)
    await callback.answer()

# =========================================================
# EDIT PROFILE
# =========================================================

@dp.callback_query(F.data == "edit_profile")
async def edit_profile(callback: CallbackQuery):
    await callback.message.edit_text("Что изменить?", reply_markup=edit_profile_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "edit_age")
async def edit_age(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎂 Введи новый возраст:")
    await state.set_state(ProfileEdit.age)
    await callback.answer()

@dp.message(ProfileEdit.age)
async def edit_age_message(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("Введи возраст числом.")
        return
    if not 18 <= age <= 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    await db.update_user_age(message.from_user.id, age)
    await state.clear()
    await message.answer("✅ Возраст изменён.", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "edit_gender")
async def edit_gender(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⚧ Введи новый пол: Мужчина / Девушка")
    await state.set_state(ProfileEdit.gender)
    await callback.answer()

@dp.message(ProfileEdit.gender)
async def edit_gender_message(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    if text in ("мужчина", "мужской", "м", "male"):
        gender = "male"
    elif text in ("девушка", "женщина", "женский", "ж", "female"):
        gender = "female"
    else:
        await message.answer("Напиши: Мужчина или Девушка.")
        return
    await db.update_user_gender(message.from_user.id, gender)
    await state.clear()
    await message.answer("✅ Пол изменён.", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "edit_photos")
async def edit_photos(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await state.set_state(ProfileEdit.photos)
    await callback.message.edit_text(
        f"📸 Отправь новые фотографии.\nМаксимум: {MAX_PHOTOS}.\nПосле этого нажми «Готово».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="edit_photos_done")]
        ]),
    )
    await callback.answer()

@dp.message(ProfileEdit.photos, F.photo)
async def edit_photo_message(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get("photos", []))
    if len(photos) >= MAX_PHOTOS:
        await message.answer(f"Максимум {MAX_PHOTOS} фотографий.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Фото добавлено: {len(photos)}/{MAX_PHOTOS}")

@dp.callback_query(F.data == "edit_photos_done", ProfileEdit.photos)
async def edit_photos_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.answer("Добавь хотя бы одно фото.", show_alert=True)
        return
    await db.update_profile_photos(callback.from_user.id, photos)
    await state.clear()
    await callback.message.edit_text("✅ Фотографии изменены.", reply_markup=main_menu_keyboard())
    await callback.answer()

# =========================================================
# DELETE / RESTORE
# =========================================================

@dp.callback_query(F.data == "delete_profile")
async def delete_profile(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Да, удалить", callback_data="delete_profile_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_profile")],
    ])
    await callback.message.edit_text("Точно удалить анкету?", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "delete_profile_confirm")
async def delete_profile_confirm(callback: CallbackQuery):
    await db.delete_profile(callback.from_user.id)
    await callback.message.edit_text("🗑 Анкета удалена.", reply_markup=main_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "restore_profile")
async def restore_profile(callback: CallbackQuery):
    await db.restore_profile(callback.from_user.id)
    await callback.message.edit_text("♻️ Анкета восстановлена.", reply_markup=main_menu_keyboard())
    await callback.answer()

# =========================================================
# RATING MODE
# =========================================================

@dp.callback_query(F.data == "menu_rate")
async def menu_rate(callback: CallbackQuery, state: FSMContext):
    if not await require_registration(callback):
        return
    profile = await db.get_profile(callback.from_user.id)
    if not profile:
        await callback.message.edit_text(
            "Сначала создай свою анкету.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать анкету", callback_data="create_profile")],
                [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
            ]),
        )
        await callback.answer()
        return
    if profile.get("status") != "active":
        await callback.answer("Твоя анкета удалена.", show_alert=True)
        return
    await clear_bot_messages(callback.message.chat.id, state)
    await state.clear()
    mode = await db.get_rating_mode(callback.from_user.id)
    await state.update_data(rating_mode=mode)
    await callback.message.edit_text("Выбери режим оценивания:", reply_markup=rating_mode_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("rating_mode:"))
async def rating_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    if mode not in ("score", "table", "both"):
        await callback.answer("Ошибка режима.", show_alert=True)
        return
    await db.update_rating_mode(callback.from_user.id, mode)
    await clear_bot_messages(callback.message.chat.id, state)
    await state.clear()
    await state.update_data(rating_mode=mode, seen_profile_ids=[])
    await callback.message.delete()
    await show_next_profile(callback.message.chat.id, callback.from_user.id, state)
    await callback.answer()

# =========================================================
# SHOW NEXT PROFILE
# =========================================================

async def show_next_profile(chat_id, user_id, state):
    data = await state.get_data()
    mode = data.get("rating_mode")
    if mode not in ("score", "table", "both"):
        mode = await db.get_rating_mode(user_id)
    seen = list(data.get("seen_profile_ids", []))
    profile = await db.get_random_unrated_profile(user_id, exclude_ids=seen)
    already_rated = False
    if not profile:
        profile = await db.get_random_rated_profile(user_id, exclude_ids=seen)
        already_rated = True
    if not profile:
        await bot.send_message(chat_id, "😔 Пока нет доступных анкет.\n\nПопробуй позже.", reply_markup=main_menu_keyboard())
        return
    target_id = profile.get("user_id")
    if target_id:
        seen.append(target_id)
    await state.update_data(
        rating_mode=mode,
        rating_profile_user_id=target_id,
        seen_profile_ids=seen,
        already_rated=already_rated,
    )
    target_user = await db.get_user(target_id)
    if not target_user:
        await show_next_profile(chat_id, user_id, state)
        return
    average = await db.get_average_rating(target_id)
    count = await db.get_rating_count(target_id)
    text = build_profile_text(target_user, profile, average, count)
    if already_rated:
        existing = await db.get_rating(user_id, target_id)
        old_rating = format_rating_row(existing, target_user.get("gender"))
        if old_rating:
            text += f"\n\nℹ️ Ты уже оценивал эту анкету: <b>{html.escape(old_rating)}</b>"
    photos = await db.get_profile_photos(target_id)
    message_ids = []
    if photos:
        if len(photos) == 1:
            photo_message = await bot.send_photo(chat_id, photos[0], caption=text, parse_mode="HTML")
            message_ids.append(photo_message.message_id)
        else:
            media = []
            for index, photo_id in enumerate(photos[:MAX_PHOTOS]):
                media.append(
                    InputMediaPhoto(
                        media=photo_id,
                        caption=text if index == 0 else None,
                        parse_mode="HTML" if index == 0 else None,
                    )
                )
            messages = await bot.send_media_group(chat_id, media)
            message_ids.extend(message.message_id for message in messages)
    else:
        profile_message = await bot.send_message(chat_id, text, parse_mode="HTML")
        message_ids.append(profile_message.message_id)
    if mode == "score":
        keyboard = score_only_profile_keyboard()
    elif mode == "table":
        keyboard = table_only_profile_keyboard()
    else:
        keyboard = rating_keyboard()
    action_message = await bot.send_message(chat_id, "Выбери действие:", reply_markup=keyboard)
    message_ids.append(action_message.message_id)
    await state.update_data(bot_message_ids=message_ids)

# =========================================================
# NEXT PROFILE
# =========================================================

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mode = data.get("rating_mode", "both")
    seen = data.get("seen_profile_ids", [])
    await clear_bot_messages(callback.message.chat.id, state)
    await state.clear()
    await state.update_data(rating_mode=mode, seen_profile_ids=seen)
    await show_next_profile(callback.message.chat.id, callback.from_user.id, state)
    await callback.answer()

# =========================================================
# ENTER RATING
# =========================================================

@dp.callback_query(F.data == "enter_score")
async def enter_score(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mode = data.get("rating_mode", "both")
    target_id = data.get("rating_profile_user_id")
    target_user = await db.get_user(target_id)
    if not target_user:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    gender = target_user.get("gender")
    if mode == "table":
        await callback.message.edit_text("📊 <b>Выбери категорию по таблице:</b>", reply_markup=table_keyboard(gender), parse_mode="HTML")
    elif mode == "both":
        await callback.message.edit_text("⭐ <b>Выбери способ оценки:</b>", reply_markup=mixed_rating_keyboard(), parse_mode="HTML")
    else:
        await callback.message.edit_text("⭐ Выбери оценку от 1 до 10:", reply_markup=score_keyboard())
    await state.set_state(Rating.score)
    await callback.answer()

# =========================================================
# MIXED
# =========================================================

@dp.callback_query(F.data == "mixed_score", Rating.score)
async def mixed_score(callback: CallbackQuery):
    await callback.message.edit_text("⭐ Выбери оценку от 1 до 10:", reply_markup=score_keyboard(show_table=True))
    await callback.answer()

@dp.callback_query(F.data == "mixed_table", Rating.score)
async def mixed_table(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    target_user = await db.get_user(target_id)
    if not target_user:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    gender = target_user.get("gender")
    await callback.message.edit_text("📊 <b>Выбери категорию по таблице:</b>", reply_markup=table_keyboard(gender), parse_mode="HTML")
    await callback.answer()

# =========================================================
# SCORE RATING
# =========================================================

@dp.callback_query(F.data.startswith("score:"), Rating.score)
async def receive_score(callback: CallbackQuery, state: FSMContext):
    try:
        score = float(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    if not 1 <= score <= 10:
        await callback.answer("Оценка должна быть от 1 до 10.", show_alert=True)
        return
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await callback.answer("Анкета потеряна.", show_alert=True)
        return
    existing = await db.get_rating(callback.from_user.id, target_id)
    await state.update_data(pending_score=score, pending_table_category=None)
    if existing:
        old_text = format_rating_row(existing)
        await state.set_state(Rating.confirm_change)
        await callback.message.edit_text(
            f"Ты уже оценивал эту анкету: <b>{html.escape(old_text or 'неизвестно')}</b>.\n\nИзменить на <b>{score:g}/10</b>?",
            reply_markup=confirm_change_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await db.save_rating(
        rater_id=callback.from_user.id,
        profile_user_id=target_id,
        score=score,
        look_type="main",
    )
    await finish_rating(callback, state, score_text=f"{score:g}/10")

# =========================================================
# TABLE RATING
# =========================================================

@dp.callback_query(F.data.startswith("table_score:"), Rating.score)
async def receive_table_score(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная категория.", show_alert=True)
        return
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await callback.answer("Анкета потеряна.", show_alert=True)
        return
    target_user = await db.get_user(target_id)
    if not target_user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    table = get_table_for_gender(target_user.get("gender"))
    if index < 0 or index >= len(table):
        await callback.answer("Некорректная категория.", show_alert=True)
        return
    category, score = table[index]
    existing = await db.get_rating(callback.from_user.id, target_id)
    await state.update_data(pending_score=score, pending_table_category=category)
    if existing:
        old_text = format_rating_row(existing, target_user.get("gender"))
        await state.set_state(Rating.confirm_change)
        await callback.message.edit_text(
            f"Ты уже оценивал эту анкету: <b>{html.escape(old_text or 'неизвестно')}</b>.\n\nИзменить на <b>{html.escape(category)}</b>?",
            reply_markup=confirm_change_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await db.save_rating(
        rater_id=callback.from_user.id,
        profile_user_id=target_id,
        score=float(score),
        look_type=f"table:{category}",
    )
    await finish_rating(callback, state, score_text=category)

# =========================================================
# CONFIRM CHANGED RATING
# =========================================================

@dp.callback_query(F.data == "confirm_change", Rating.confirm_change)
async def confirm_rating(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    score = data.get("pending_score")
    category = data.get("pending_table_category")
    if not target_id or score is None:
        await callback.answer("Не удалось изменить оценку.", show_alert=True)
        return
    if category:
        look_type = f"table:{category}"
        score_text = category
    else:
        look_type = "main"
        score_text = f"{float(score):g}/10"
    await db.save_rating(
        rater_id=callback.from_user.id,
        profile_user_id=target_id,
        score=float(score),
        look_type=look_type,
    )
    await finish_rating(callback, state, score_text=score_text)

# =========================================================
# FINISH RATING
# =========================================================

async def finish_rating(callback, state, score_text):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    mode = data.get("rating_mode", "both")
    seen = data.get("seen_profile_ids", [])
    await clear_bot_messages(callback.message.chat.id, state)
    await state.clear()
    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=seen,
        rating_profile_user_id=target_id,
    )
    await callback.message.answer(
        f"✅ Оценка <b>{html.escape(str(score_text))}</b> сохранена.",
        reply_markup=after_rating_keyboard(),
        parse_mode="HTML",
    )
    try:
        await bot.send_message(
            target_id,
            "⭐ Твою анкету кто-то оценил!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👤 Посмотреть анкету",
                        callback_data=f"rated_by:{callback.from_user.id}",
                    ),
                    InlineKeyboardButton(
                        text="⭐ Оценить в ответ",
                        callback_data=f"rate_back:{callback.from_user.id}",
                    ),
                ]
            ]),
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    await callback.answer()

# =========================================================
# NEW: RATE BACK HANDLER
# =========================================================

@dp.callback_query(F.data.startswith("rate_back:"))
async def rate_back(callback: CallbackQuery, state: FSMContext):
    try:
        rater_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    if not await require_registration(callback):
        return
    profile = await db.get_profile(callback.from_user.id)
    if not profile or profile.get("status") != "active":
        await callback.answer("Сначала создай активную анкету.", show_alert=True)
        return
    target_user = await db.get_user(rater_id)
    target_profile = await db.get_profile(rater_id)
    if not target_user or not target_profile or target_profile.get("status") != "active":
        await callback.answer("Анкета больше недоступна.", show_alert=True)
        return
    mode = await db.get_rating_mode(callback.from_user.id)
    await clear_bot_messages(callback.message.chat.id, state)
    await state.update_data(
        rating_mode=mode,
        rating_profile_user_id=rater_id,
        seen_profile_ids=[rater_id],
    )
    average = await db.get_average_rating(rater_id)
    count = await db.get_rating_count(rater_id)
    text = build_profile_text(target_user, target_profile, average, count)
    photos = await db.get_profile_photos(rater_id)
    message_ids = []
    if photos:
        if len(photos) == 1:
            msg = await bot.send_photo(callback.message.chat.id, photos[0], caption=text, parse_mode="HTML")
            message_ids.append(msg.message_id)
        else:
            media = []
            for index, photo_id in enumerate(photos[:MAX_PHOTOS]):
                media.append(
                    InputMediaPhoto(
                        media=photo_id,
                        caption=text if index == 0 else None,
                        parse_mode="HTML" if index == 0 else None,
                    )
                )
            messages = await bot.send_media_group(callback.message.chat.id, media)
            message_ids.extend(msg.message_id for msg in messages)
    else:
        msg = await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")
        message_ids.append(msg.message_id)
    if mode == "score":
        keyboard = score_only_profile_keyboard()
    elif mode == "table":
        keyboard = table_only_profile_keyboard()
    else:
        keyboard = rating_keyboard()
    action_message = await bot.send_message(callback.message.chat.id, "Оцени эту анкету:", reply_markup=keyboard)
    message_ids.append(action_message.message_id)
    await state.update_data(bot_message_ids=message_ids)
    await callback.answer()

# =========================================================
# TABLE IMAGE
# =========================================================

@dp.callback_query(F.data == "view_rating_table")
async def view_rating_table(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    target_user = await db.get_user(target_id)
    if not target_user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    image = get_table_image_for_gender(target_user.get("gender"))
    msg = await callback.message.answer_photo(
        image,
        caption="📊 <b>Таблица оценки</b>\n\nВыбери категорию, которая лучше всего соответствует внешности анкеты.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Закрыть таблицу", callback_data="close_rating_table")]
        ]),
    )
    await state.update_data(rating_table_message_id=msg.message_id)
    await callback.answer()

@dp.callback_query(F.data == "close_rating_table")
async def close_rating_table(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.update_data(rating_table_message_id=None)
    await callback.answer()

# =========================================================
# CANCEL RATING
# =========================================================

@dp.callback_query(F.data == "cancel_rating")
async def cancel_rating(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mode = data.get("rating_mode", "both")
    seen = data.get("seen_profile_ids", [])
    await clear_bot_messages(callback.message.chat.id, state)
    await state.clear()
    await state.update_data(rating_mode=mode, seen_profile_ids=seen)
    await show_next_profile(callback.message.chat.id, callback.from_user.id, state)
    await callback.answer()

# =========================================================
# RATED-BY PROFILE
# =========================================================

@dp.callback_query(F.data.startswith("rated_by:"))
async def rated_by_profile(callback: CallbackQuery):
    try:
        rater_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    user = await db.get_user(rater_id)
    profile = await db.get_profile(rater_id)
    if not user or not profile or profile.get("status") != "active":
        await callback.answer("Анкета больше недоступна.", show_alert=True)
        return
    await send_profile(callback.message.chat.id, user, profile, public=True)
    await callback.answer()

# =========================================================
# LIKES / MATCH
# =========================================================

@dp.callback_query(F.data == "like_current")
async def like_current(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    await db.create_like(callback.from_user.id, target_id)
    mutual = await db.has_mutual_like(callback.from_user.id, target_id)
    if mutual:
        await send_mutual_match(callback.from_user.id, target_id)
        await callback.answer("❤️ У вас взаимная симпатия!", show_alert=True)
    else:
        await callback.answer("❤️ Симпатия отправлена!", show_alert=True)

async def send_mutual_match(user_a, user_b):
    user_a_data = await db.get_user(user_a)
    user_b_data = await db.get_user(user_b)
    username_a = f"@{user_a_data.get('username')}" if user_a_data and user_a_data.get("username") else "пользователь"
    username_b = f"@{user_b_data.get('username')}" if user_b_data and user_b_data.get("username") else "пользователь"
    try:
        await bot.send_message(user_a, f"❤️ <b>Взаимная симпатия!</b>\n\nТвоя симпатия: {html.escape(username_b)}", parse_mode="HTML")
    except Exception:
        pass
    try:
        await bot.send_message(user_b, f"❤️ <b>Взаимная симпатия!</b>\n\nТвоя симпатия: {html.escape(username_a)}", parse_mode="HTML")
    except Exception:
        pass

# =========================================================
# ADVICE
# =========================================================

@dp.callback_query(F.data == "add_advice")
async def add_advice(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    await state.set_state(Advice.text)
    await callback.message.edit_text(
        f"💬 <b>Напиши совет по улучшению внешности.</b>\n\nМаксимум {MAX_ADVICE_LENGTH} символов.",
        reply_markup=advice_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

@dp.callback_query(F.data == "advice_view_profile", Advice.text)
async def advice_view_profile(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    old_ids = data.get("advice_profile_message_ids", [])
    await delete_by_ids(callback.message.chat.id, old_ids)
    user = await db.get_user(target_id)
    profile = await db.get_profile(target_id)
    if not user or not profile or profile.get("status") != "active":
        await callback.answer("Анкета больше недоступна.", show_alert=True)
        return
    await send_profile(
        callback.message.chat.id,
        user,
        profile,
        state=state,
        public=True,
        public_return_callback="advice_back",
    )
    data = await state.get_data()
    profile_ids = data.get("bot_message_ids", [])
    await state.update_data(advice_profile_message_ids=profile_ids, bot_message_ids=[])
    await callback.answer()

@dp.callback_query(F.data == "advice_back", Advice.text)
async def advice_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ids = data.get("advice_profile_message_ids", [])
    await delete_by_ids(callback.message.chat.id, ids)
    await state.update_data(advice_profile_message_ids=[])
    await callback.answer("Можно продолжать писать совет.")

@dp.message(Advice.text)
async def advice_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Напиши текст совета.")
        return
    if len(text) > MAX_ADVICE_LENGTH:
        await message.answer(f"Максимум {MAX_ADVICE_LENGTH} символов.")
        return
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await state.clear()
        await message.answer("Не удалось определить анкету.", reply_markup=main_menu_keyboard())
        return
    profile = await db.get_profile(target_id)
    if not profile:
        await state.clear()
        await message.answer("Анкета больше недоступна.", reply_markup=main_menu_keyboard())
        return
    existing_rating = await db.get_rating(message.from_user.id, target_id)
    score = None
    if existing_rating:
        try:
            score = float(existing_rating.get("score"))
        except (TypeError, ValueError):
            score = None
    await db.create_advice(
        from_user_id=message.from_user.id,
        to_user_id=target_id,
        text=text,
        score=score,
    )
    # Отправляем уведомление с текстом совета (без кнопки)
    try:
        await bot.send_message(
            target_id,
            f"💬 Тебе оставили новый совет по твоей анкете:\n\n{html.escape(text)}",
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    await state.clear()
    await message.answer("✅ Совет отправлен.", reply_markup=main_menu_keyboard())

# =========================================================
# REPORT
# =========================================================

@dp.callback_query(F.data == "report_current")
async def report_current(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🚩 <b>Жалоба</b>\n\nОпиши причину жалобы.",
        reply_markup=report_cancel_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(Report.reason)
    await callback.answer()

@dp.callback_query(F.data == "cancel_report")
async def cancel_report(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено.", reply_markup=main_menu_keyboard())
    await callback.answer()

@dp.message(Report.reason)
async def report_reason(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Напиши причину жалобы.")
        return
    if len(text) > MAX_REPORT_LENGTH:
        await message.answer(f"Максимум {MAX_REPORT_LENGTH} символов.")
        return
    data = await state.get_data()
    target_id = data.get("rating_profile_user_id")
    if not target_id:
        await state.clear()
        await message.answer("Анкета не найдена.", reply_markup=main_menu_keyboard())
        return
    await db.create_report(
        reporter_id=message.from_user.id,
        profile_user_id=target_id,
        reason=text,
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                (
                    "🚩 <b>Новая жалоба</b>\n\n"
                    f"От: <code>{message.from_user.id}</code>\n"
                    f"На: <code>{target_id}</code>\n\n"
                    f"{html.escape(text)}"
                ),
                parse_mode="HTML",
                reply_markup=admin_report_keyboard(target_id),
            )
        except Exception:
            pass
    await state.clear()
    await message.answer("✅ Жалоба отправлена.", reply_markup=main_menu_keyboard())

# =========================================================
# ADMIN ACTIONS FOR REPORTS
# =========================================================

@dp.callback_query(F.data.startswith("admin_view_profile:"))
async def admin_view_profile(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    try:
        target_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    user = await db.get_user(target_id)
    profile = await db.get_profile(target_id)
    if not user or not profile:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    await send_profile(callback.message.chat.id, user, profile, public=True)
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_delete_profile:"))
async def admin_delete_profile(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    try:
        target_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    await db.delete_profile(target_id)
    await callback.answer("Анкета удалена.", show_alert=True)
    # Опционально уведомить владельца
    try:
        await bot.send_message(target_id, "🗑 Твоя анкета была удалена администратором.")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass

# =========================================================
# ADMIN
# =========================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🚩 Жалобы", callback_data="admin_reports")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_menu")],
    ])

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    stats = await db.get_admin_stats()
    await callback.message.edit_text(
        (
            "📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: <b>{stats.get('users', 0)}</b>\n"
            f"👤 Активных анкет: <b>{stats.get('active_profiles', 0)}</b>\n"
            f"🗑 Удалённых анкет: <b>{stats.get('deleted_profiles', 0)}</b>\n"
            f"⭐ Оценок: <b>{stats.get('ratings', 0)}</b>\n"
            f"❤️ Лайков: <b>{stats.get('likes', 0)}</b>\n"
            f"💬 Советов: <b>{stats.get('advice', 0)}</b>\n"
            f"🚩 Открытых жалоб: <b>{stats.get('open_reports', 0)}</b>"
        ),
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_reports")
async def admin_reports(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    reports = await db.get_reports()
    if not reports:
        text = "🚩 Жалоб нет."
    else:
        lines = ["🚩 <b>Последние жалобы</b>", ""]
        for report in reports[:20]:
            lines.append(
                (
                    f"#{report.get('id')} — {report.get('status', 'open')}\n"
                    f"От: <code>{report.get('reporter_id')}</code>\n"
                    f"На: <code>{report.get('profile_user_id')}</code>\n"
                    f"{html.escape(str(report.get('reason', '')))}\n"
                )
            )
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.message.edit_text("📢 Напиши сообщение для рассылки.\n\nОно будет отправлено всем пользователям.")
    await state.set_state(Broadcast.message)
    await callback.answer()

@dp.message(Broadcast.message)
async def broadcast_message(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение не может быть пустым.")
        return
    users = await db.get_all_users()
    sent_count = 0
    failed_count = 0
    await message.answer("📢 Рассылка началась.")
    for user in users:
        user_id = user.get("telegram_id")
        if not user_id:
            continue
        try:
            await bot.send_message(user_id, text)
            sent_count += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(user_id, text)
                sent_count += 1
            except Exception:
                failed_count += 1
        except Exception:
            failed_count += 1
        await asyncio.sleep(0.05)
    await db.create_broadcast(
        admin_id=message.from_user.id,
        message=text,
        sent_count=sent_count,
        failed_count=failed_count,
    )
    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена.\n\nОтправлено: {sent_count}\nОшибок: {failed_count}",
        reply_markup=admin_keyboard(),
    )

# =========================================================
# HEALTH SERVER
# =========================================================

async def health_handler(request):
    return web.Response(text="OK")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Health server started on port %s", PORT)
    return runner

# =========================================================
# ERROR HANDLER
# =========================================================

@dp.errors()
async def global_error_handler(event):
    logger.exception("Unhandled bot error: %s", event.exception)
    return True

# =========================================================
# MAIN
# =========================================================

async def main():
    health_runner = await start_health_server()
    try:
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
