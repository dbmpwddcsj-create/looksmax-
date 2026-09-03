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

logger = logging.getLogger(
    "dating_bot"
)

db = Database()

bot = Bot(
    BOT_TOKEN
)

dp = Dispatcher()

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
# MESSAGE CLEANUP
# =========================================================

async def safe_delete_message(
    message: Message | None,
):
    if not message:
        return

    try:
        await message.delete()
    except (
        TelegramBadRequest,
        TelegramForbiddenError,
    ):
        pass
    except Exception:
        logger.exception(
            "Failed to delete message"
        )


async def delete_by_ids(
    chat_id: int,
    message_ids: list[int] | None,
):
    for message_id in (
        message_ids or []
    ):
        try:
            await bot.delete_message(
                chat_id,
                message_id,
            )
        except (
            TelegramBadRequest,
            TelegramForbiddenError,
        ):
            pass
        except Exception:
            logger.exception(
                "Failed deleting message %s",
                message_id,
            )


async def clear_bot_messages(
    state: FSMContext,
    chat_id: int,
):
    data = await state.get_data()

    message_ids = data.get(
        "bot_message_ids",
        [],
    )

    await delete_by_ids(
        chat_id,
        message_ids,
    )

    await state.update_data(
        bot_message_ids=[]
    )


async def remember_bot_message(
    state: FSMContext,
    message: Message,
):
    data = await state.get_data()

    ids = data.get(
        "bot_message_ids",
        [],
    )

    ids.append(
        message.message_id
    )

    await state.update_data(
        bot_message_ids=ids
    )


# =========================================================
# KEYBOARDS
# =========================================================

def rules_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принимаю правила",
                    callback_data="agree",
                )
            ]
        ]
    )


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Оценивать анкеты",
                    callback_data="menu_rate",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Моя анкета",
                    callback_data="my_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Создать анкету",
                    callback_data="create_profile",
                )
            ],
        ]
    )


def rating_mode_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔢 Оценка 1–10",
                    callback_data="rating_mode:score",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 По таблице",
                    callback_data="rating_mode:table",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔀 Смешанный режим",
                    callback_data="rating_mode:both",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def score_keyboard():
    buttons = []

    row = []

    for i in range(1, 11):
        row.append(
            InlineKeyboardButton(
                text=str(i),
                callback_data=f"score:{i}",
            )
        )

        if len(row) == 5:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_rating",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def rating_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Оценить",
                    callback_data="enter_score",
                ),
                InlineKeyboardButton(
                    text="❤️ Познакомиться",
                    callback_data="like_current",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Следующая",
                    callback_data="next_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Совет по улучшению внешности",
                    callback_data="add_advice",
                ),
                InlineKeyboardButton(
                    text="🚩 Жалоба",
                    callback_data="report_current",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def score_only_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Оценить",
                    callback_data="enter_score",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Следующая",
                    callback_data="next_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def table_only_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Оценить по таблице",
                    callback_data="enter_score",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Следующая",
                    callback_data="next_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def after_rating_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Познакомиться",
                    callback_data="like_current",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Совет по улучшению внешности",
                    callback_data="add_advice",
                ),
                InlineKeyboardButton(
                    text="➡️ Следующая",
                    callback_data="next_profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def confirm_change_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Изменить оценку",
                    callback_data="confirm_rating",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Оставить старую",
                    callback_data="cancel_rating",
                )
            ],
        ]
    )


def profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="edit_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить анкету",
                    callback_data="delete_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def deleted_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="♻️ Восстановить",
                    callback_data="restore_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def edit_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎂 Возраст",
                    callback_data="edit_age",
                ),
                InlineKeyboardButton(
                    text="⚧ Пол",
                    callback_data="edit_gender",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📸 Фотографии",
                    callback_data="edit_photos",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="my_profile",
                )
            ],
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin_stats",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Новые пользователи",
                    callback_data="admin_new_users",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚩 Жалобы",
                    callback_data="admin_reports",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Рассылка",
                    callback_data="admin_broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 История рассылок",
                    callback_data="admin_broadcasts",
                )
            ],
        ]
    )


# =========================================================
# TEXT HELPERS
# =========================================================

def gender_text(
    gender: str | None,
):
    if gender == "male":
        return "Мужчина"

    if gender == "female":
        return "Женщина"

    return "Не указан"


def build_profile_text(
    user: dict,
    profile: dict,
    average: float,
    count: int,
):
    age = user.get(
        "age"
    )

    gender = gender_text(
        user.get("gender")
    )

    text = (
        "👤 <b>Анкета</b>\n\n"
        f"🎂 Возраст: <b>{age or '—'}</b>\n"
        f"⚧ Пол: <b>{gender}</b>\n"
    )

    height = profile.get(
        "height"
    )

    weight = profile.get(
        "weight"
    )

    if height is not None:
        text += (
            f"📏 Рост: <b>{height:g} см</b>\n"
            if isinstance(height, float)
            else f"📏 Рост: <b>{height} см</b>\n"
        )

    if weight is not None:
        text += (
            f"⚖️ Вес: <b>{weight:g} кг</b>\n"
            if isinstance(weight, float)
            else f"⚖️ Вес: <b>{weight} кг</b>\n"
        )

    facts = profile.get(
        "facts"
    )

    if facts:
        text += (
            "\n📝 <b>О себе:</b>\n"
            f"{html.escape(str(facts))}\n"
        )

    text += (
        "\n⭐ Рейтинг: "
        f"<b>{average:.1f}/10</b>"
        f" ({count})"
    )

    return text


# =========================================================
# REGISTRATION
# =========================================================

async def ensure_user(
    message: Message,
):
    user, is_new = await db.ensure_user(
        message.from_user.id,
        message.from_user.username,
    )

    if (
        is_new
        and user
    ):
        await notify_admins_new_user(
            user
        )

    return user


async def is_registered(
    user: dict | None,
):
    if not user:
        return False

    return bool(
        user.get("accepted_rules")
        and user.get("age")
        and user.get("gender")
    )


async def require_registration(
    callback: CallbackQuery,
):
    user = await db.get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True,
        )
        return None

    if not user.get(
        "accepted_rules"
    ):
        await callback.answer(
            "Сначала прими правила",
            show_alert=True,
        )
        return None

    if not user.get("age"):
        await callback.answer(
            "Укажи возраст",
            show_alert=True,
        )
        return None

    if not user.get("gender"):
        await callback.answer(
            "Укажи пол",
            show_alert=True,
        )
        return None

    return user


@dp.message(
    CommandStart()
)
async def start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    user = await ensure_user(
        message
    )

    if not user:
        await message.answer(
            "Не удалось создать пользователя."
        )
        return

    if not user.get(
        "accepted_rules"
    ):
        await message.answer(
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Перед началом работы необходимо "
            "принять правила.",
            reply_markup=rules_keyboard(),
        )
        return

    if not user.get("age"):
        await state.set_state(
            Registration.age
        )

        await message.answer(
            "🎂 Введи свой возраст "
            "(от 18 до 100):"
        )
        return

    if not user.get("gender"):
        await state.set_state(
            Registration.gender
        )

        await message.answer(
            "⚧ Укажи пол:\n\n"
            "Напиши <b>м</b> или <b>мужчина</b>, "
            "либо <b>ж</b> или <b>женщина</b>."
        )
        return

    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(),
    )


@dp.callback_query(
    F.data == "agree"
)
async def agree(
    callback: CallbackQuery,
    state: FSMContext,
):
    await db.update_user(
        callback.from_user.id,
        {
            "accepted_rules": True,
        },
    )

    await state.set_state(
        Registration.age
    )

    await callback.message.edit_text(
        "🎂 Введи свой возраст "
        "(от 18 до 100):"
    )

    await callback.answer()


@dp.message(
    Registration.age
)
async def registration_age(
    message: Message,
    state: FSMContext,
):
    try:
        age = int(
            message.text.strip()
        )
    except (
        ValueError,
        AttributeError,
    ):
        await message.answer(
            "Введи возраст числом, "
            "например: 25."
        )
        return

    if not 18 <= age <= 100:
        await message.answer(
            "Возраст должен быть "
            "от 18 до 100 лет."
        )
        return

    await db.update_user_age(
        message.from_user.id,
        age,
    )

    await state.set_state(
        Registration.gender
    )

    await message.answer(
        "⚧ Теперь укажи пол:\n\n"
        "Напиши <b>м</b> или <b>мужчина</b>, "
        "либо <b>ж</b> или <b>женщина</b>."
    )


@dp.message(
    Registration.gender
)
async def registration_gender(
    message: Message,
    state: FSMContext,
):
    value = (
        message.text
        .strip()
        .lower()
    )

    if value in (
        "м",
        "муж",
        "мужчина",
        "male",
    ):
        gender = "male"

    elif value in (
        "ж",
        "жен",
        "женщина",
        "female",
    ):
        gender = "female"

    else:
        await message.answer(
            "Напиши «м» или «мужчина», "
            "либо «ж» или «женщина»."
        )
        return

    await db.update_user_gender(
        message.from_user.id,
        gender,
    )

    await state.clear()

    await message.answer(
        "✅ Регистрация завершена!",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# MENU
# =========================================================

@dp.callback_query(
    F.data == "back_menu"
)
async def back_menu(
    callback: CallbackQuery,
    state: FSMContext,
):
    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    await safe_delete_message(
        callback.message
    )

    await bot.send_message(
        callback.from_user.id,
        "Главное меню:",
        reply_markup=main_menu_keyboard(),
    )

    await callback.answer()


# =========================================================
# PROFILE CREATION
# =========================================================

@dp.callback_query(
    F.data == "create_profile"
)
async def create_profile_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await require_registration(
        callback
    )

    if not user:
        return

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()
    await state.update_data(
        photos=[]
    )

    await state.set_state(
        ProfileCreation.photo
    )

    await callback.message.edit_text(
        "📸 Отправь от 1 до 5 фотографий.\n\n"
        "После отправки нажми «Готово».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Готово",
                        callback_data="photos_done",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Меню",
                        callback_data="back_menu",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.message(
    ProfileCreation.photo,
    F.photo
)
async def receive_profile_photo(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    photos = data.get(
        "photos",
        [],
    )

    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"Можно добавить максимум "
            f"{MAX_PHOTOS} фотографий."
        )
        return

    photos.append(
        message.photo[-1].file_id
    )

    await state.update_data(
        photos=photos
    )

    await message.answer(
        f"📸 Фото добавлено: "
        f"{len(photos)}/{MAX_PHOTOS}\n\n"
        "Можешь отправить ещё или нажать "
        "«Готово».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Готово",
                        callback_data="photos_done",
                    )
                ]
            ]
        ),
    )


@dp.callback_query(
    F.data == "photos_done",
    ProfileCreation.photo,
)
async def profile_photos_done(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    photos = data.get(
        "photos",
        [],
    )

    if not photos:
        await callback.answer(
            "Добавь хотя бы одну фотографию.",
            show_alert=True,
        )
        return

    await state.set_state(
        ProfileCreation.facts
    )

    await callback.message.edit_text(
        "📝 Напиши несколько фактов о себе.\n\n"
        "Можно написать «пропустить»."
    )

    await callback.answer()


@dp.message(
    ProfileCreation.facts
)
async def profile_facts(
    message: Message,
    state: FSMContext,
):
    text = (
        message.text or ""
    ).strip()

    if text.lower() in (
        "пропустить",
        "-",
        "нет",
    ):
        facts = None
    else:
        if len(text) > MAX_FACTS_LENGTH:
            await message.answer(
                f"Максимум "
                f"{MAX_FACTS_LENGTH} символов."
            )
            return

        facts = text

    await state.update_data(
        facts=facts
    )

    await state.set_state(
        ProfileCreation.height
    )

    await message.answer(
        "📏 Введи рост в сантиметрах.\n\n"
        "Можно написать «пропустить»."
    )


@dp.message(
    ProfileCreation.height
)
async def profile_height(
    message: Message,
    state: FSMContext,
):
    text = (
        message.text or ""
    ).strip().lower()

    if text in (
        "пропустить",
        "-",
        "нет",
    ):
        height = None
    else:
        try:
            height = float(
                text.replace(
                    ",",
                    ".",
                )
            )
        except ValueError:
            await message.answer(
                "Введи рост числом, "
                "например 180."
            )
            return

        if not 100 <= height <= 250:
            await message.answer(
                "Рост должен быть "
                "от 100 до 250 см."
            )
            return

    await state.update_data(
        height=height
    )

    await state.set_state(
        ProfileCreation.weight
    )

    await message.answer(
        "⚖️ Введи вес в килограммах.\n\n"
        "Можно написать «пропустить»."
    )


@dp.message(
    ProfileCreation.weight
)
async def profile_weight(
    message: Message,
    state: FSMContext,
):
    text = (
        message.text or ""
    ).strip().lower()

    if text in (
        "пропустить",
        "-",
        "нет",
    ):
        weight = None
    else:
        try:
            weight = float(
                text.replace(
                    ",",
                    ".",
                )
            )
        except ValueError:
            await message.answer(
                "Введи вес числом, "
                "например 75."
            )
            return

        if not 30 <= weight <= 300:
            await message.answer(
                "Вес должен быть "
                "от 30 до 300 кг."
            )
            return

    await state.update_data(
        weight=weight
    )

    await save_profile_from_state(
        message,
        state,
    )


async def save_profile_from_state(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    photos = data.get(
        "photos",
        [],
    )

    if not photos:
        await message.answer(
            "Не найдены фотографии."
        )
        await state.clear()
        return

    try:
        await db.create_profile(
            telegram_id=message.from_user.id,
            photo_id=photos[0],
            photo_ids=photos,
            facts=data.get("facts"),
            height=data.get("height"),
            weight=data.get("weight"),
        )
    except Exception:
        logger.exception(
            "Profile creation failed"
        )

        await message.answer(
            "❌ Не удалось сохранить анкету. "
            "Попробуй ещё раз."
        )
        return

    await state.clear()

    await message.answer(
        "✅ Анкета сохранена!",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# MY PROFILE
# =========================================================

async def send_profile(
    chat_id: int,
    user: dict,
    profile: dict,
    state: FSMContext | None = None,
):
    average = await db.get_average_rating(
        user["telegram_id"]
    )

    count = await db.get_rating_count(
        user["telegram_id"]
    )

    text = build_profile_text(
        user,
        profile,
        average,
        count,
    )

    photos = await db.get_profile_photos(
        user["telegram_id"]
    )

    if not photos:
        return []

    message_ids = []

    if len(photos) == 1:
        sent = await bot.send_photo(
            chat_id,
            photos[0],
            caption=text,
            parse_mode="HTML",
        )

        message_ids.append(
            sent.message_id
        )

    else:
        media = []

        for index, photo_id in enumerate(
            photos[:MAX_PHOTOS]
        ):
            media.append(
                InputMediaPhoto(
                    media=photo_id,
                    caption=(
                        text
                        if index == 0
                        else None
                    ),
                    parse_mode=(
                        "HTML"
                        if index == 0
                        else None
                    ),
                )
            )

        sent_messages = (
            await bot.send_media_group(
                chat_id,
                media,
            )
        )

        message_ids.extend(
            m.message_id
            for m in sent_messages
        )

    control = await bot.send_message(
        chat_id,
        "Управление анкетой:",
        reply_markup=profile_keyboard(),
    )

    message_ids.append(
        control.message_id
    )

    if state:
        await state.update_data(
            bot_message_ids=message_ids
        )

    return message_ids


@dp.callback_query(
    F.data == "my_profile"
)
async def my_profile(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await require_registration(
        callback
    )

    if not user:
        return

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile:
        await callback.message.edit_text(
            "У тебя пока нет анкеты.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать анкету",
                            callback_data="create_profile",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Меню",
                            callback_data="back_menu",
                        )
                    ],
                ]
            ),
        )

        await callback.answer()
        return

    if profile.get(
        "status"
    ) != "active":
        await callback.message.edit_text(
            "🗑 Твоя анкета сейчас удалена.",
            reply_markup=deleted_profile_keyboard(),
        )

        await callback.answer()
        return

    await safe_delete_message(
        callback.message
    )

    await send_profile(
        callback.from_user.id,
        user,
        profile,
        state,
    )

    await callback.answer()


# =========================================================
# EDIT PROFILE
# =========================================================

@dp.callback_query(
    F.data == "edit_profile"
)
async def edit_profile(
    callback: CallbackQuery,
):
    await callback.message.edit_text(
        "Что хочешь изменить?",
        reply_markup=edit_profile_keyboard(),
    )

    await callback.answer()


@dp.callback_query(
    F.data == "edit_age"
)
async def edit_age_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(
        ProfileEdit.age
    )

    await callback.message.edit_text(
        "🎂 Введи новый возраст "
        "(18–100):"
    )

    await callback.answer()


@dp.message(
    ProfileEdit.age
)
async def edit_age(
    message: Message,
    state: FSMContext,
):
    try:
        age = int(
            message.text.strip()
        )
    except (
        ValueError,
        AttributeError,
    ):
        await message.answer(
            "Введи возраст числом."
        )
        return

    if not 18 <= age <= 100:
        await message.answer(
            "Возраст должен быть "
            "от 18 до 100."
        )
        return

    await db.update_user_age(
        message.from_user.id,
        age,
    )

    await state.clear()

    await message.answer(
        "✅ Возраст изменён.",
        reply_markup=main_menu_keyboard(),
    )


@dp.callback_query(
    F.data == "edit_gender"
)
async def edit_gender_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(
        ProfileEdit.gender
    )

    await callback.message.edit_text(
        "⚧ Введи новый пол:\n\n"
        "м / мужчина\n"
        "ж / женщина"
    )

    await callback.answer()


@dp.message(
    ProfileEdit.gender
)
async def edit_gender(
    message: Message,
    state: FSMContext,
):
    value = (
        message.text
        .strip()
        .lower()
    )

    if value in (
        "м",
        "муж",
        "мужчина",
        "male",
    ):
        gender = "male"

    elif value in (
        "ж",
        "жен",
        "женщина",
        "female",
    ):
        gender = "female"

    else:
        await message.answer(
            "Используй м/мужчина "
            "или ж/женщина."
        )
        return

    await db.update_user_gender(
        message.from_user.id,
        gender,
    )

    await state.clear()

    await message.answer(
        "✅ Пол изменён.",
        reply_markup=main_menu_keyboard(),
    )


@dp.callback_query(
    F.data == "edit_photos"
)
async def edit_photos_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await state.update_data(
        photos=[]
    )

    await state.set_state(
        ProfileEdit.photos
    )

    await callback.message.edit_text(
        "📸 Отправь новые фотографии "
        "(от 1 до 5).\n\n"
        "После отправки нажми «Готово».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Готово",
                        callback_data="edit_photos_done",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Меню",
                        callback_data="back_menu",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.message(
    ProfileEdit.photos,
    F.photo,
)
async def edit_photo_receive(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    photos = data.get(
        "photos",
        [],
    )

    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"Максимум {MAX_PHOTOS} фото."
        )
        return

    photos.append(
        message.photo[-1].file_id
    )

    await state.update_data(
        photos=photos
    )

    await message.answer(
        f"Добавлено: "
        f"{len(photos)}/{MAX_PHOTOS}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Готово",
                        callback_data="edit_photos_done",
                    )
                ]
            ]
        ),
    )


@dp.callback_query(
    F.data == "edit_photos_done",
    ProfileEdit.photos,
)
async def edit_photos_done(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    photos = data.get(
        "photos",
        [],
    )

    if not photos:
        await callback.answer(
            "Добавь хотя бы одно фото.",
            show_alert=True,
        )
        return

    await db.update_profile_photos(
        callback.from_user.id,
        photos,
    )

    await state.clear()

    await callback.message.edit_text(
        "✅ Фотографии обновлены.",
        reply_markup=main_menu_keyboard(),
    )

    await callback.answer()


# =========================================================
# DELETE / RESTORE PROFILE
# =========================================================

@dp.callback_query(
    F.data == "delete_profile"
)
async def delete_profile(
    callback: CallbackQuery,
):
    await db.delete_profile(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "🗑 Анкета удалена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="♻️ Восстановить",
                        callback_data="restore_profile",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Меню",
                        callback_data="back_menu",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.callback_query(
    F.data == "restore_profile"
)
async def restore_profile(
    callback: CallbackQuery,
):
    await db.restore_profile(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "♻️ Анкета восстановлена.",
        reply_markup=main_menu_keyboard(),
    )

    await callback.answer()


# =========================================================
# RATING
# =========================================================

@dp.callback_query(
    F.data == "menu_rate"
)
async def menu_rate(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await require_registration(
        callback
    )

    if not user:
        return

    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile:
        await callback.message.edit_text(
            "Сначала создай свою анкету.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать",
                            callback_data="create_profile",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Меню",
                            callback_data="back_menu",
                        )
                    ],
                ]
            ),
        )

        await callback.answer()
        return

    if profile.get(
        "status"
    ) != "active":
        await callback.message.edit_text(
            "Сначала восстанови свою анкету.",
            reply_markup=deleted_profile_keyboard(),
        )

        await callback.answer()
        return

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    current_mode = await db.get_rating_mode(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "⭐ Выбери режим оценки:",
        reply_markup=rating_mode_keyboard(),
    )

    await state.update_data(
        rating_mode=current_mode
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("rating_mode:")
)
async def rating_mode(
    callback: CallbackQuery,
    state: FSMContext,
):
    mode = callback.data.split(
        ":",
        1,
    )[1]

    if mode not in (
        "score",
        "table",
        "both",
    ):
        await callback.answer(
            "Неизвестный режим.",
            show_alert=True,
        )
        return

    await db.update_rating_mode(
        callback.from_user.id,
        mode,
    )

    await state.clear()

    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=[],
    )

    await safe_delete_message(
        callback.message
    )

    await show_next_profile(
        callback.from_user.id,
        state,
    )

    await callback.answer()


async def show_next_profile(
    user_id: int,
    state: FSMContext,
):
    data = await state.get_data()

    mode = data.get(
        "rating_mode"
    )

    if mode not in (
        "score",
        "table",
        "both",
    ):
        mode = await db.get_rating_mode(
            user_id
        )

    seen = data.get(
        "seen_profile_ids",
        [],
    )

    profile = await db.get_random_unrated_profile(
        user_id,
        exclude_ids=seen,
    )

    already_rated = False

    if not profile:
        profile = await db.get_random_rated_profile(
            user_id,
            exclude_ids=seen,
        )
        already_rated = bool(profile)

    if not profile:
        await state.clear()

        await bot.send_message(
            user_id,
            "✅ Ты посмотрел все доступные анкеты.",
            reply_markup=main_menu_keyboard(),
        )
        return

    target_id = profile[
        "user_id"
    ]

    if target_id not in seen:
        seen.append(target_id)

    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=seen,
        rating_profile_user_id=target_id,
        already_rated=already_rated,
    )

    target_user = await db.get_user(
        target_id
    )

    if not target_user:
        await show_next_profile(
            user_id,
            state,
        )
        return

    average = await db.get_average_rating(
        target_id
    )

    count = await db.get_rating_count(
        target_id
    )

    text = build_profile_text(
        target_user,
        profile,
        average,
        count,
    )

    if already_rated:
        rating = await db.get_rating(
            user_id,
            target_id,
        )

        if rating:
            text += (
                "\n\n"
                f"ℹ️ Ты уже оценивал эту анкету: "
                f"<b>{float(rating['score']):g}/10</b>"
            )

    photos = await db.get_profile_photos(
        target_id
    )

    if not photos:
        await show_next_profile(
            user_id,
            state,
        )
        return

    message_ids = []

    if len(photos) == 1:
        sent = await bot.send_photo(
            user_id,
            photos[0],
            caption=text,
            parse_mode="HTML",
        )

        message_ids.append(
            sent.message_id
        )

    else:
        media = []

        for index, photo_id in enumerate(
            photos[:MAX_PHOTOS]
        ):
            media.append(
                InputMediaPhoto(
                    media=photo_id,
                    caption=(
                        text
                        if index == 0
                        else None
                    ),
                    parse_mode=(
                        "HTML"
                        if index == 0
                        else None
                    ),
                )
            )

        sent_messages = (
            await bot.send_media_group(
                user_id,
                media,
            )
        )

        message_ids.extend(
            m.message_id
            for m in sent_messages
        )

    if mode == "score":
        keyboard = score_only_profile_keyboard()

    elif mode == "table":
        keyboard = table_only_profile_keyboard()

    else:
        keyboard = rating_keyboard()

    control = await bot.send_message(
        user_id,
        "Выбери действие:",
        reply_markup=keyboard,
    )

    message_ids.append(
        control.message_id
    )

    await state.update_data(
        bot_message_ids=message_ids
    )


@dp.callback_query(
    F.data == "next_profile"
)
async def next_profile(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    seen = data.get(
        "seen_profile_ids",
        [],
    )

    if target_id and target_id not in seen:
        seen.append(target_id)

    mode = data.get(
        "rating_mode"
    )

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=seen,
    )

    await show_next_profile(
        callback.from_user.id,
        state,
    )

    await callback.answer()


@dp.callback_query(
    F.data == "enter_score"
)
async def enter_score(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    mode = data.get(
        "rating_mode",
        "both",
    )

    if mode == "table":
        try:
            await callback.message.edit_reply_markup(
                reply_markup=score_keyboard()
            )
        except TelegramBadRequest:
            pass
    else:
        try:
            await callback.message.edit_text(
                "⭐ Выбери оценку от 1 до 10:",
                reply_markup=score_keyboard(),
            )
        except TelegramBadRequest:
            pass

    await state.set_state(
        Rating.score
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("score:"),
    Rating.score,
)
async def receive_score(
    callback: CallbackQuery,
    state: FSMContext,
):
    try:
        score = float(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except ValueError:
        await callback.answer(
            "Некорректная оценка.",
            show_alert=True,
        )
        return

    if not 1 <= score <= 10:
        await callback.answer(
            "Оценка должна быть от 1 до 10.",
            show_alert=True,
        )
        return

    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    if not target_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    existing = await db.get_rating(
        callback.from_user.id,
        target_id,
    )

    await state.update_data(
        pending_score=score
    )

    if existing:
        await state.set_state(
            Rating.confirm_change
        )

        await callback.message.edit_text(
            f"Ты уже ставил "
            f"<b>{float(existing['score']):g}/10</b>.\n\n"
            f"Изменить на "
            f"<b>{score:g}/10</b>?",
            reply_markup=confirm_change_keyboard(),
            parse_mode="HTML",
        )

        await callback.answer()
        return

    try:
        await db.save_rating(
            rater_id=callback.from_user.id,
            profile_user_id=target_id,
            score=float(score),
            look_type="main",
        )
    except Exception:
        logger.exception(
            "Failed saving rating"
        )

        await callback.answer(
            "Не удалось сохранить оценку.",
            show_alert=True,
        )
        return

    seen = data.get(
        "seen_profile_ids",
        [],
    )

    if target_id not in seen:
        seen.append(target_id)

    mode = data.get(
        "rating_mode",
        "both",
    )

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=seen,
        rating_profile_user_id=target_id,
    )

    await bot.send_message(
        callback.from_user.id,
        f"✅ Оценка <b>{float(score):g}/10</b> сохранена.",
        reply_markup=after_rating_keyboard(),
        parse_mode="HTML",
    )

    try:
        await bot.send_message(
            target_id,
            "⭐ Твою анкету кто-то оценил!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть анкету",
                            callback_data=(
                                f"rated_by:{callback.from_user.id}"
                            ),
                        )
                    ]
                ]
            ),
        )
    except (
        TelegramForbiddenError,
        TelegramBadRequest,
    ):
        pass
    except Exception:
        logger.exception(
            "Failed rating notification"
        )

    await callback.answer(
        "Оценка сохранена!"
    )


@dp.callback_query(
    F.data == "confirm_rating",
    Rating.confirm_change,
)
async def confirm_rating(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    score = data.get(
        "pending_score"
    )

    if not target_id or score is None:
        await callback.answer(
            "Ошибка данных оценки.",
            show_alert=True,
        )
        return

    try:
        await db.save_rating(
            rater_id=callback.from_user.id,
            profile_user_id=target_id,
            score=float(score),
            look_type="main",
        )
    except Exception:
        logger.exception(
            "Failed saving rating"
        )

        await callback.answer(
            "Не удалось сохранить оценку.",
            show_alert=True,
        )
        return

    seen = data.get(
        "seen_profile_ids",
        [],
    )

    if target_id not in seen:
        seen.append(target_id)

    mode = data.get(
        "rating_mode",
        "both",
    )

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=seen,
        rating_profile_user_id=target_id,
    )

    await bot.send_message(
        callback.from_user.id,
        f"✅ Оценка <b>{float(score):g}/10</b> сохранена.",
        reply_markup=after_rating_keyboard(),
        parse_mode="HTML",
    )

    try:
        await bot.send_message(
            target_id,
            "⭐ Твою анкету кто-то оценил!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть анкету",
                            callback_data=(
                                f"rated_by:{callback.from_user.id}"
                            ),
                        )
                    ]
                ]
            ),
        )
    except (
        TelegramForbiddenError,
        TelegramBadRequest,
    ):
        pass
    except Exception:
        logger.exception(
            "Failed rating notification"
        )

    await callback.answer(
        "Оценка изменена!"
    )


@dp.callback_query(
    F.data == "cancel_rating"
)
async def cancel_rating(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    mode = data.get(
        "rating_mode"
    )

    seen = data.get(
        "seen_profile_ids",
        [],
    )

    if target_id and target_id not in seen:
        seen.append(target_id)

    await clear_bot_messages(
        state,
        callback.from_user.id,
    )

    await state.clear()

    await state.update_data(
        rating_mode=mode,
        seen_profile_ids=seen,
    )

    await show_next_profile(
        callback.from_user.id,
        state,
    )

    await callback.answer()


# =========================================================
# RATED PROFILE
# =========================================================

@dp.callback_query(
    F.data.startswith("rated_by:")
)
async def rated_by_profile(
    callback: CallbackQuery,
):
    try:
        rater_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except ValueError:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    user = await db.get_user(
        rater_id
    )

    profile = await db.get_profile(
        rater_id
    )

    if (
        not user
        or not profile
        or profile.get("status") != "active"
    ):
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    average = await db.get_average_rating(
        rater_id
    )

    count = await db.get_rating_count(
        rater_id
    )

    text = build_profile_text(
        user,
        profile,
        average,
        count,
    )

    photos = await db.get_profile_photos(
        rater_id
    )

    if not photos:
        await callback.answer(
            "Фотографии анкеты недоступны.",
            show_alert=True,
        )
        return

    await safe_delete_message(
        callback.message
    )

    if len(photos) == 1:
        await bot.send_photo(
            callback.from_user.id,
            photos[0],
            caption=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Меню",
                            callback_data="back_menu",
                        )
                    ]
                ]
            ),
        )

    else:
        media = []

        for index, photo_id in enumerate(
            photos[:MAX_PHOTOS]
        ):
            media.append(
                InputMediaPhoto(
                    media=photo_id,
                    caption=(
                        text
                        if index == 0
                        else None
                    ),
                    parse_mode=(
                        "HTML"
                        if index == 0
                        else None
                    ),
                )
            )

        await bot.send_media_group(
            callback.from_user.id,
            media,
        )

        await bot.send_message(
            callback.from_user.id,
            "👤 Анкета пользователя",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Меню",
                            callback_data="back_menu",
                        )
                    ]
                ]
            ),
        )

    await callback.answer()


# =========================================================
# LIKE / MATCH
# =========================================================

@dp.callback_query(
    F.data == "like_current"
)
async def like_current(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    if not target_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    if target_id == callback.from_user.id:
        await callback.answer(
            "Нельзя поставить лайк себе.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        target_id
    )

    if (
        not profile
        or profile.get("status")
        != "active"
    ):
        await callback.answer(
            "Эта анкета недоступна.",
            show_alert=True,
        )
        return

    await db.create_like(
        callback.from_user.id,
        target_id,
    )

    mutual = await db.has_mutual_like(
        callback.from_user.id,
        target_id,
    )

    if mutual:
        await send_mutual_match(
            callback.from_user.id,
            target_id,
        )

        await callback.answer(
            "❤️ Взаимная симпатия!"
        )
    else:
        await callback.answer(
            "❤️ Лайк отправлен!"
        )


async def send_mutual_match(
    user_a: int,
    user_b: int,
):
    a = await db.get_user(
        user_a
    )

    b = await db.get_user(
        user_b
    )

    if not a or not b:
        return

    username_a = a.get(
        "username"
    )

    username_b = b.get(
        "username"
    )

    contact_a = (
        f"@{username_a}"
        if username_a
        else "Пользователь без username"
    )

    contact_b = (
        f"@{username_b}"
        if username_b
        else "Пользователь без username"
    )

    keyboard_a = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Открыть профиль",
                    callback_data=f"match:{user_b}",
                )
            ]
        ]
    )

    keyboard_b = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Открыть профиль",
                    callback_data=f"match:{user_a}",
                )
            ]
        ]
    )

    try:
        await bot.send_message(
            user_a,
            "❤️ <b>Взаимная симпатия!</b>\n\n"
            f"Тебе понравился: {contact_b}",
            reply_markup=keyboard_a,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Match notification A failed"
        )

    try:
        await bot.send_message(
            user_b,
            "❤️ <b>Взаимная симпатия!</b>\n\n"
            f"Тебе понравился: {contact_a}",
            reply_markup=keyboard_b,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Match notification B failed"
        )


@dp.callback_query(
    F.data.startswith("match:")
)
async def match_profile(
    callback: CallbackQuery,
):
    try:
        target_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except ValueError:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        target_id
    )

    user = await db.get_user(
        target_id
    )

    if (
        not profile
        or not user
        or profile.get("status")
        != "active"
    ):
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    await safe_delete_message(
        callback.message
    )

    await send_profile(
        callback.from_user.id,
        user,
        profile,
    )

    await callback.answer()


# =========================================================
# ADVICE
# =========================================================

@dp.callback_query(
    F.data == "add_advice"
)
async def add_advice(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    if not target_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    await state.set_state(
        Advice.text
    )

    await callback.message.edit_text(
        "💬 Напиши совет для владельца анкеты.\n\n"
        f"Максимум {MAX_ADVICE_LENGTH} символов."
    )

    await callback.answer()


@dp.message(
    Advice.text
)
async def advice_text(
    message: Message,
    state: FSMContext,
):
    text = (
        message.text or ""
    ).strip()

    if not text:
        await message.answer(
            "Совет не может быть пустым."
        )
        return

    if len(text) > MAX_ADVICE_LENGTH:
        await message.answer(
            f"Максимум "
            f"{MAX_ADVICE_LENGTH} символов."
        )
        return

    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    if not target_id:
        await state.clear()
        await message.answer(
            "Анкета не найдена.",
            reply_markup=main_menu_keyboard(),
        )
        return

    profile = await db.get_profile(
        target_id
    )

    if (
        not profile
        or profile.get("status")
        != "active"
    ):
        await state.clear()
        await message.answer(
            "Анкета недоступна.",
            reply_markup=main_menu_keyboard(),
        )
        return

    rating = await db.get_rating(
        message.from_user.id,
        target_id,
    )

    score = (
        float(rating["score"])
        if rating
        and rating.get("score")
        is not None
        else None
    )

    await db.create_advice(
        from_user_id=message.from_user.id,
        to_user_id=target_id,
        text=text,
        score=score,
    )

    try:
        await bot.send_message(
            target_id,
            "💬 Тебе оставили новый совет "
            "по твоей анкете!",
        )
    except (
        TelegramForbiddenError,
        TelegramBadRequest,
    ):
        pass
    except Exception:
        logger.exception(
            "Advice notification failed"
        )

    await state.clear()

    await message.answer(
        "✅ Совет отправлен.",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# REPORTS
# =========================================================

@dp.callback_query(
    F.data == "report_current"
)
async def report_current(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    if not target_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    await state.set_state(
        Report.reason
    )

    await callback.message.edit_text(
        "🚩 Опиши причину жалобы.\n\n"
        f"Максимум {MAX_REPORT_LENGTH} символов."
    )

    await callback.answer()


@dp.message(
    Report.reason
)
async def report_reason(
    message: Message,
    state: FSMContext,
):
    reason = (
        message.text or ""
    ).strip()

    if not reason:
        await message.answer(
            "Причина не может быть пустой."
        )
        return

    if len(reason) > MAX_REPORT_LENGTH:
        await message.answer(
            f"Максимум "
            f"{MAX_REPORT_LENGTH} символов."
        )
        return

    data = await state.get_data()

    target_id = data.get(
        "rating_profile_user_id"
    )

    if not target_id:
        await state.clear()
        await message.answer(
            "Анкета не найдена.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if target_id == message.from_user.id:
        await state.clear()
        await message.answer(
            "Нельзя пожаловаться на себя.",
            reply_markup=main_menu_keyboard(),
        )
        return

    profile = await db.get_profile(
        target_id
    )

    if (
        not profile
        or profile.get("status")
        != "active"
    ):
        await state.clear()
        await message.answer(
            "Анкета недоступна.",
            reply_markup=main_menu_keyboard(),
        )
        return

    report = await db.create_report(
        reporter_id=message.from_user.id,
        profile_user_id=target_id,
        reason=reason,
    )

    await state.clear()

    if not report:
        await message.answer(
            "Не удалось создать жалобу.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "🚩 Жалоба отправлена администрации.",
        reply_markup=main_menu_keyboard(),
    )

    report_id = report.get(
        "id"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚩 <b>Новая жалоба</b>\n\n"
                f"ID жалобы: <b>{report_id}</b>\n"
                f"От: <code>{message.from_user.id}</code>\n"
                f"На: <code>{target_id}</code>\n\n"
                f"{html.escape(reason)}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🚩 Открыть",
                                callback_data=(
                                    f"admin_report:{report_id}"
                                ),
                            )
                        ]
                    ]
                ),
            )
        except Exception:
            logger.exception(
                "Failed notifying admin"
            )


# =========================================================
# ADMIN
# =========================================================

def is_admin(
    user_id: int,
):
    return user_id in ADMIN_IDS


@dp.message(
    Command("admin")
)
async def admin(
    message: Message,
):
    if not is_admin(
        message.from_user.id
    ):
        return

    await message.answer(
        "🛠 <b>Админ-панель</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(
    F.data == "admin_stats"
)
async def admin_stats(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    stats = await db.get_admin_stats()

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👤 Пользователей: "
        f"<b>{stats.get('users', 0)}</b>\n"
        f"🟢 Активных анкет: "
        f"<b>{stats.get('active_profiles', 0)}</b>\n"
        f"🟡 Ожидающих анкет: "
        f"<b>{stats.get('pending_profiles', 0)}</b>\n"
        f"🔴 Удалённых анкет: "
        f"<b>{stats.get('deleted_profiles', 0)}</b>\n\n"
        f"⭐ Оценок: "
        f"<b>{stats.get('ratings', 0)}</b>\n"
        f"❤️ Лайков: "
        f"<b>{stats.get('likes', 0)}</b>\n"
        f"💬 Советов: "
        f"<b>{stats.get('advice', 0)}</b>\n"
        f"🚩 Открытых жалоб: "
        f"<b>{stats.get('open_reports', 0)}</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin_back",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data == "admin_new_users"
)
async def admin_new_users(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    enabled = (
        await db.new_user_notifications_enabled()
    )

    status = (
        "🟢 Включены"
        if enabled
        else "🔴 Выключены"
    )

    button_text = (
        "🔴 Выключить"
        if enabled
        else "🟢 Включить"
    )

    await callback.message.edit_text(
        "👤 <b>Уведомления о новых пользователях</b>\n\n"
        f"Статус: <b>{status}</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=(
                            "admin_toggle_new_users"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin_back",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data == "admin_toggle_new_users"
)
async def admin_toggle_new_users(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    current = (
        await db.new_user_notifications_enabled()
    )

    await db.set_new_user_notifications(
        not current
    )

    await callback.answer(
        "Настройка изменена."
    )

    await admin_new_users(
        callback
    )


async def notify_admins_new_user(
    user: dict,
):
    if not ADMIN_IDS:
        return

    try:
        enabled = (
            await db.new_user_notifications_enabled()
        )
    except Exception:
        logger.exception(
            "Failed reading notification setting"
        )
        return

    if not enabled:
        return

    telegram_id = user.get(
        "telegram_id"
    )

    username = user.get(
        "username"
    )

    username_text = (
        f"@{username}"
        if username
        else "без username"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "👤 <b>Новый пользователь</b>\n\n"
                f"Telegram ID: "
                f"<code>{telegram_id}</code>\n"
                f"Username: {html.escape(username_text)}",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Failed new user notification"
            )


@dp.callback_query(
    F.data == "admin_reports"
)
async def admin_reports(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    reports = await db.get_reports()

    if not reports:
        await callback.message.edit_text(
            "🚩 Жалоб нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="admin_back",
                        )
                    ]
                ]
            ),
        )

        await callback.answer()
        return

    buttons = []

    for report in reports[:30]:
        status = report.get(
            "status",
            "open",
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"#{report.get('id')} "
                        f"— {status}"
                    ),
                    callback_data=(
                        f"admin_report:{report.get('id')}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="admin_back",
            )
        ]
    )

    await callback.message.edit_text(
        "🚩 <b>Жалобы</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        ),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("admin_report:")
)
async def admin_report(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    try:
        report_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except ValueError:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    report = await db.get_report(
        report_id
    )

    if not report:
        await callback.answer(
            "Жалоба не найдена.",
            show_alert=True,
        )
        return

    reason = html.escape(
        str(
            report.get(
                "reason",
                "",
            )
        )
    )

    text = (
        "🚩 <b>Жалоба</b>\n\n"
        f"ID: <code>{report_id}</code>\n"
        f"Статус: <b>"
        f"{html.escape(str(report.get('status', '')))}"
        f"</b>\n"
        f"Репортёр: "
        f"<code>{report.get('reporter_id')}</code>\n"
        f"Анкета: "
        f"<code>{report.get('profile_user_id')}</code>\n\n"
        f"<b>Причина:</b>\n{reason}"
    )

    target_id = report.get(
        "profile_user_id"
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Удалить анкету",
                        callback_data=(
                            f"admin_delete_profile:"
                            f"{report_id}:{target_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Закрыть",
                        callback_data=(
                            f"admin_close_report:"
                            f"{report_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin_reports",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("admin_delete_profile:")
)
async def admin_delete_profile(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    parts = callback.data.split(
        ":"
    )

    if len(parts) != 3:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    try:
        report_id = int(parts[1])
        target_id = int(parts[2])
    except ValueError:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    await db.delete_profile(
        target_id
    )

    await db.resolve_report(
        report_id
    )

    try:
        await bot.send_message(
            target_id,
            "⚠️ Твоя анкета была удалена "
            "администрацией после рассмотрения жалобы.",
        )
    except (
        TelegramForbiddenError,
        TelegramBadRequest,
    ):
        pass
    except Exception:
        logger.exception(
            "Failed moderation notification"
        )

    await callback.message.edit_text(
        "✅ Анкета удалена, жалоба закрыта.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Жалобы",
                        callback_data="admin_reports",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🛠 Админ-панель",
                        callback_data="admin_back",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("admin_close_report:")
)
async def admin_close_report(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    try:
        report_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except ValueError:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    await db.close_report(
        report_id
    )

    await callback.message.edit_text(
        "✅ Жалоба закрыта.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Жалобы",
                        callback_data="admin_reports",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🛠 Админ-панель",
                        callback_data="admin_back",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.callback_query(
    F.data == "admin_back"
)
async def admin_back(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# =========================================================
# BROADCAST
# =========================================================

@dp.callback_query(
    F.data == "admin_broadcast"
)
async def admin_broadcast(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    await state.set_state(
        Broadcast.message
    )

    await callback.message.edit_text(
        "📢 Отправь сообщение для рассылки.\n\n"
        "Можно отправить текст, фото, видео, "
        "документ и другое сообщение."
    )

    await callback.answer()


@dp.message(
    Broadcast.message
)
async def broadcast_message(
    message: Message,
    state: FSMContext,
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    users = await db.get_all_users()

    sent_count = 0
    failed_count = 0

    history_text = (
        message.text
        or message.caption
        or message.content_type
        or "Сообщение"
    )

    for row in users:
        user_id = row.get(
            "telegram_id"
        )

        if not user_id:
            continue

        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )

            sent_count += 1

            await asyncio.sleep(
                0.04
            )

        except TelegramRetryAfter as exc:
            await asyncio.sleep(
                exc.retry_after
            )

            try:
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )

                sent_count += 1

            except Exception:
                failed_count += 1

        except (
            TelegramForbiddenError,
            TelegramBadRequest,
        ):
            failed_count += 1

        except Exception:
            failed_count += 1
            logger.exception(
                "Broadcast error for %s",
                user_id,
            )

    try:
        await db.create_broadcast(
            admin_id=message.from_user.id,
            message=history_text[:2000],
            sent_count=sent_count,
            failed_count=failed_count,
        )
    except Exception:
        logger.exception(
            "Failed saving broadcast history"
        )

    await state.clear()

    await message.answer(
        "📢 <b>Рассылка завершена</b>\n\n"
        f"✅ Отправлено: <b>{sent_count}</b>\n"
        f"❌ Ошибок: <b>{failed_count}</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(
    F.data == "admin_broadcasts"
)
async def admin_broadcasts(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    broadcasts = await db.get_broadcasts()

    if not broadcasts:
        await callback.message.edit_text(
            "📜 История рассылок пуста.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="admin_back",
                        )
                    ]
                ]
            ),
        )

        await callback.answer()
        return

    lines = [
        "📜 <b>Последние рассылки</b>\n"
    ]

    for item in broadcasts[:10]:
        created = item.get(
            "created_at",
            "",
        )

        sent = item.get(
            "sent_count",
            0,
        )

        failed = item.get(
            "failed_count",
            0,
        )

        message_text = html.escape(
            str(
                item.get(
                    "message",
                    "",
                )
            )[:100]
        )

        lines.append(
            f"\n<b>{created}</b>\n"
            f"✅ {sent} | ❌ {failed}\n"
            f"{message_text}\n"
        )

    await callback.message.edit_text(
        "".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin_back",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )

    await callback.answer()


# =========================================================
# GLOBAL ERROR HANDLER
# =========================================================

@dp.errors()
async def global_error_handler(
    event,
):
    logger.exception(
        "Unhandled bot error: %s",
        event.exception,
    )


# =========================================================
# HEALTH SERVER
# =========================================================

async def health(
    request: web.Request,
):
    return web.Response(
        text="OK"
    )


async def start_health_server():
    app = web.Application()

    app.router.add_get(
        "/",
        health,
    )

    app.router.add_get(
        "/health",
        health,
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT,
    )

    await site.start()

    logger.info(
        "Health server started on port %s",
        PORT,
    )

    return runner


# =========================================================
# MAIN
# =========================================================

async def main():
    runner = await start_health_server()

    try:
        await bot.delete_webhook(
            drop_pending_updates=True
        )

        me = await bot.get_me()

        logger.info(
            "Bot started: @%s",
            me.username,
        )

        await dp.start_polling(
            bot
        )

    finally:
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(
        main()
    )
