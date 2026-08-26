import asyncio
import logging
import os

from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db import Database


# ============================================================
# CONFIG
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

BOT_TOKEN = os.environ["BOT_TOKEN"]

ADMIN_IDS = {
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip()
}

db = Database()

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# FSM
# ============================================================

class Registration(StatesGroup):
    age = State()
    gender = State()


class ProfileCreation(StatesGroup):
    photo = State()
    facts = State()
    height = State()
    weight = State()


class Rating(StatesGroup):
    custom_score = State()
    advice = State()
    confirm_change = State()


class Report(StatesGroup):
    reason = State()


class Broadcast(StatesGroup):
    message = State()


# ============================================================
# MAIN MENU
# ============================================================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Рейтить",
                    callback_data="menu_rate",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Моя анкета",
                    callback_data="menu_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Создать анкету",
                    callback_data="menu_create",
                )
            ],
        ]
    )


def back_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_menu",
                )
            ]
        ]
    )


def cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel",
                )
            ]
        ]
    )


# ============================================================
# REGISTRATION
# ============================================================

def gender_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨 Мужской",
                    callback_data="gender_male",
                ),
                InlineKeyboardButton(
                    text="👩 Женский",
                    callback_data="gender_female",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel",
                )
            ],
        ]
    )


# ============================================================
# PROFILE
# ============================================================

def profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить анкету",
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
                    text="⬅️ Назад",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def delete_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data="delete_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="delete_cancel",
                )
            ],
        ]
    )


# ============================================================
# RATING
# ============================================================

def rating_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1",
                    callback_data="score:1",
                ),
                InlineKeyboardButton(
                    text="2",
                    callback_data="score:2",
                ),
                InlineKeyboardButton(
                    text="3",
                    callback_data="score:3",
                ),
                InlineKeyboardButton(
                    text="4",
                    callback_data="score:4",
                ),
                InlineKeyboardButton(
                    text="5",
                    callback_data="score:5",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="6",
                    callback_data="score:6",
                ),
                InlineKeyboardButton(
                    text="7",
                    callback_data="score:7",
                ),
                InlineKeyboardButton(
                    text="8",
                    callback_data="score:8",
                ),
                InlineKeyboardButton(
                    text="9",
                    callback_data="score:9",
                ),
                InlineKeyboardButton(
                    text="10",
                    callback_data="score:10",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Другая оценка",
                    callback_data="custom_score",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚩 Пожаловаться",
                    callback_data="report_current",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
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
                    text="💡 Добавить совет",
                    callback_data="add_advice",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Следующая анкета",
                    callback_data="next_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def rating_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, изменить",
                    callback_data="confirm_rating",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_rating_change",
                )
            ],
        ]
    )


# ============================================================
# HELPERS
# ============================================================

async def ensure_user(message: Message):
    user = await db.get_user(
        message.from_user.id
    )

    if not user:
        user = await db.create_user(
            message.from_user.id,
            message.from_user.username,
        )

    return user


async def show_menu(message: Message):
    username = message.from_user.username

    if username:
        name = f"@{username}"
    else:
        name = message.from_user.first_name or "пользователь"

    profile = await db.get_profile(
        message.from_user.id
    )

    if profile and profile.get("status") == "active":
        text = (
            f"👋 Привет, {name}!\n\n"
            "✨ Что хочешь сделать?"
        )
    else:
        text = (
            f"👋 Привет, {name}!\n\n"
            "✨ Здесь ты можешь получить оценку "
            "своей внешности от других пользователей, "
            "оценивать других, получать советы и многое другое.\n\n"
            "💫 Всё бесплатно!\n\n"
            "⚠️ Для использования бота сначала создай анкету.\n\n"
            "Что хочешь сделать?"
        )

    await message.answer(
        text,
        reply_markup=main_menu(),
    )


async def require_profile(
    message: Message,
):
    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile or profile.get("status") != "active":
        await message.answer(
            "❗ Сначала создай анкету.",
            reply_markup=main_menu(),
        )
        return None

    return profile


def parse_number(value: str):
    value = value.strip().replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    user = await ensure_user(message)

    if not user.get("accepted_rules"):
        await message.answer(
            "Перед созданием анкеты\n\n"
            "Ботом можно пользоваться только с 18 лет.\n"
            "Возраст указывается в анкете и виден другим.\n"
            "На фото — ваше настоящее лицо, иначе анкету удалят.\n"
            "В боте работает активная модерация.\n\n"
            "Нажимая «Согласен», вы принимаете правила и политику.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Согласен",
                            callback_data="agree",
                        )
                    ]
                ]
            ),
        )
        return

    await show_menu(message)


# ============================================================
# AGREEMENT
# ============================================================

@dp.callback_query(F.data == "agree")
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

    await callback.message.edit_text(
        "🎂 Укажи свой возраст:",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        Registration.age
    )

    await callback.answer()


# ============================================================
# AGE
# ============================================================

@dp.message(Registration.age)
async def registration_age(
    message: Message,
    state: FSMContext,
):
    value = message.text.strip()

    try:
        age = int(value)
    except ValueError:
        await message.answer(
            "❌ Введи возраст целым числом.",
            reply_markup=cancel_keyboard(),
        )
        return

    if age < 18:
        await message.answer(
            "❌ Бот доступен только с 18 лет.",
            reply_markup=cancel_keyboard(),
        )
        return

    if age > 100:
        await message.answer(
            "❌ Укажи корректный возраст.",
            reply_markup=cancel_keyboard(),
        )
        return

    await db.update_user(
        message.from_user.id,
        {
            "age": age,
        },
    )

    await message.answer(
        "⚧ Выбери пол:",
        reply_markup=gender_keyboard(),
    )

    await state.set_state(
        Registration.gender
    )


# ============================================================
# GENDER
# ============================================================

@dp.callback_query(
    Registration.gender,
    F.data.in_({
        "gender_male",
        "gender_female",
    }),
)
async def registration_gender(
    callback: CallbackQuery,
    state: FSMContext,
):
    gender = (
        "Мужской"
        if callback.data == "gender_male"
        else "Женский"
    )

    await db.update_user(
        callback.from_user.id,
        {
            "gender": gender,
        },
    )

    await state.clear()

    await callback.message.edit_text(
        "✅ Регистрация завершена.\n\n"
        "Теперь создай свою анкету.",
        reply_markup=main_menu(),
    )

    await callback.answer()


# ============================================================
# CANCEL / BACK
# ============================================================

@dp.callback_query(F.data == "cancel")
async def cancel(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.edit_text(
        "❌ Действие отменено.",
        reply_markup=main_menu(),
    )

    await callback.answer()


@dp.callback_query(F.data == "back_menu")
async def back_menu(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.answer(
        "🏠 Главное меню:",
        reply_markup=main_menu(),
    )

    await callback.answer()


# ============================================================
# CREATE PROFILE
# ============================================================

@dp.callback_query(F.data == "menu_create")
async def create_profile_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await db.get_user(
        callback.from_user.id
    )

    if not user or not user.get("accepted_rules"):
        await callback.answer(
            "Сначала пройди регистрацию.",
            show_alert=True,
        )
        return

    await state.clear()

    await callback.message.answer(
        "📸 Отправь фотографию своего лица.\n\n"
        "На фотографии должно быть настоящее лицо.",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        ProfileCreation.photo
    )

    await callback.answer()


@dp.message(
    ProfileCreation.photo,
    F.photo,
)
async def profile_photo(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        photo_id=message.photo[-1].file_id
    )

    await message.answer(
        "📝 Напиши несколько фактов о себе.\n\n"
        "Это необязательно.\n"
        "Если не хочешь указывать — напиши «нет».",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        ProfileCreation.facts
    )


@dp.message(ProfileCreation.photo)
async def invalid_photo(
    message: Message,
):
    await message.answer(
        "❌ Я не получил фотографию.\n\n"
        "Отправь именно фото.",
        reply_markup=cancel_keyboard(),
    )


@dp.message(ProfileCreation.facts)
async def profile_facts(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    if text.lower() in {
        "нет",
        "no",
        "-",
        "пропустить",
    }:
        text = None

    await state.update_data(
        facts=text
    )

    await message.answer(
        "📏 Укажи рост в сантиметрах.\n\n"
        "Например: 180\n"
        "Если не хочешь указывать — напиши «нет».",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        ProfileCreation.height
    )


@dp.message(ProfileCreation.height)
async def profile_height(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    if text.lower() in {
        "нет",
        "no",
        "-",
        "пропустить",
    }:
        height = None
    else:
        height = parse_number(text)

        if height is None:
            await message.answer(
                "❌ Не понял рост.\n\n"
                "Введи число, например: 180\n"
                "Или нажми «Отмена».",
                reply_markup=cancel_keyboard(),
            )
            return

        if height < 100 or height > 250:
            await message.answer(
                "❌ Укажи рост от 100 до 250 см.",
                reply_markup=cancel_keyboard(),
            )
            return

    await state.update_data(
        height=height
    )

    await message.answer(
        "⚖️ Укажи вес в килограммах.\n\n"
        "Можно написать:\n"
        "75\n"
        "75.5\n"
        "75,5\n\n"
        "Если не хочешь указывать — напиши «нет».",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        ProfileCreation.weight
    )


@dp.message(ProfileCreation.weight)
async def profile_weight(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    if text.lower() in {
        "нет",
        "no",
        "-",
        "пропустить",
    }:
        weight = None
    else:
        weight = parse_number(text)

        if weight is None:
            await message.answer(
                "❌ Не понял вес.\n\n"
                "Напиши, например: 75 или 75,5.",
                reply_markup=cancel_keyboard(),
            )
            return

        if weight < 30 or weight > 300:
            await message.answer(
                "❌ Укажи вес от 30 до 300 кг.",
                reply_markup=cancel_keyboard(),
            )
            return

    data = await state.get_data()

    existing = await db.get_profile(
        message.from_user.id
    )

    if existing:
        await db.update_profile(
            message.from_user.id,
            {
                "photo_id": data["photo_id"],
                "facts": data.get("facts"),
                "height": data.get("height"),
                "weight": weight,
                "status": "active",
            },
        )
    else:
        await db.create_profile(
            telegram_id=message.from_user.id,
            photo_id=data["photo_id"],
            facts=data.get("facts"),
            height=data.get("height"),
            weight=weight,
        )

    await state.clear()

    await message.answer(
        "✅ Анкета сохранена!",
        reply_markup=main_menu(),
    )


# ============================================================
# MY PROFILE
# ============================================================

@dp.callback_query(F.data == "menu_profile")
async def my_profile(
    callback: CallbackQuery,
):
    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile or profile.get("status") != "active":
        await callback.message.answer(
            "❗ У тебя пока нет анкеты.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    await send_my_profile(
        callback.message,
        profile,
    )

    await callback.answer()


async def send_my_profile(
    message: Message,
    profile: dict,
):
    average = await db.get_average_rating(
        profile["user_id"]
    )

    count = await db.get_rating_count(
        profile["user_id"]
    )

    user = await db.get_user(
        profile["user_id"]
    )

    username = (
        user.get("username")
        if user
        else None
    )

    text = (
        "👤 Моя анкета\n\n"
        f"@{username if username else 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—') if user else '—'}\n"
        f"⚧ Пол: {user.get('gender', '—') if user else '—'}\n"
        f"⭐ Средняя оценка: {average:.1f}/10\n"
        f"📊 Оценок: {count}\n"
    )

    if profile.get("facts"):
        text += f"\n📝 Факты:\n{profile['facts']}\n"

    if profile.get("height"):
        text += f"\n📏 Рост: {profile['height']} см"

    if profile.get("weight"):
        text += f"\n⚖️ Вес: {profile['weight']} кг"

    await message.answer_photo(
        photo=profile["photo_id"],
        caption=text,
        reply_markup=profile_keyboard(),
    )


# ============================================================
# DELETE PROFILE
# ============================================================

@dp.callback_query(F.data == "delete_profile")
async def delete_profile_question(
    callback: CallbackQuery,
):
    await callback.message.answer(
        "⚠️ Ты действительно хочешь удалить свою анкету?",
        reply_markup=delete_confirm_keyboard(),
    )

    await callback.answer()


@dp.callback_query(F.data == "delete_cancel")
async def delete_cancel(
    callback: CallbackQuery,
):
    await callback.message.edit_text(
        "Удаление отменено."
    )

    await callback.answer()


@dp.callback_query(F.data == "delete_confirm")
async def delete_confirm(
    callback: CallbackQuery,
):
    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile:
        await callback.message.answer(
            "Анкета уже удалена.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    await db.delete_profile(
        callback.from_user.id
    )

    await callback.message.answer(
        "🗑 Анкета удалена.",
        reply_markup=main_menu(),
    )

    await callback.answer()


# ============================================================
# EDIT PROFILE
# ============================================================

@dp.callback_query(F.data == "edit_profile")
async def edit_profile(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.answer(
        "📸 Отправь новую фотографию.",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        ProfileCreation.photo
    )

    await callback.answer()


# ============================================================
# RATING
# ============================================================

@dp.callback_query(F.data == "menu_rate")
async def start_rating(
    callback: CallbackQuery,
    state: FSMContext,
):
    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile or profile.get("status") != "active":
        await callback.message.answer(
            "❗ Сначала создай анкету.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    await state.clear()

    await show_next_rating_profile(
        callback.message,
        callback.from_user.id,
    )

    await callback.answer()


@dp.callback_query(F.data == "next_profile")
async def next_profile(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await show_next_rating_profile(
        callback.message,
        callback.from_user.id,
    )

    await callback.answer()


async def show_next_rating_profile(
    message: Message,
    user_id: int,
):
    profile = await db.get_random_unrated_profile(
        user_id
    )

    if profile:
        await send_rating_profile(
            message,
            profile,
            repeated=False,
        )
        return

    profile = await db.get_random_rated_profile(
        user_id
    )

    if profile:
        rating = await db.get_rating(
            user_id,
            profile["user_id"],
        )

        previous = (
            float(rating["score"])
            if rating
            else None
        )

        await message.answer(
            "⚠️ Ты уже оценил все доступные анкеты.\n\n"
            "Теперь будут показаны анкеты, которые "
            "ты уже оценивал.\n\n"
            f"Твоя предыдущая оценка: "
            f"{previous:.1f}/10"
            if previous is not None
            else
            "⚠️ Ты уже оценил все доступные анкеты.\n\n"
            "Теперь будут показаны анкеты, которые "
            "ты уже оценивал.",
        )

        await send_rating_profile(
            message,
            profile,
            repeated=True,
            previous_score=previous,
        )

        return

    await message.answer(
        "😔 Сейчас нет доступных анкет.",
        reply_markup=main_menu(),
    )


async def send_rating_profile(
    message: Message,
    profile: dict,
    repeated: bool = False,
    previous_score: float | None = None,
):
    user = await db.get_user(
        profile["user_id"]
    )

    if not user:
        return

    username = user.get("username")

    text = (
        f"👤 @{username if username else 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—')}\n"
        f"⚧ Пол: {user.get('gender', '—')}\n"
    )

    if profile.get("facts"):
        text += f"\n📝 Факты:\n{profile['facts']}\n"

    if profile.get("height"):
        text += f"\n📏 Рост: {profile['height']} см"

    if profile.get("weight"):
        text += f"\n⚖️ Вес: {profile['weight']} кг"

    if repeated and previous_score is not None:
        text += (
            f"\n\n⚠️ Ты уже оценивал эту анкету "
            f"на {previous_score:.1f}/10."
        )

    await message.answer_photo(
        photo=profile["photo_id"],
        caption=text,
        reply_markup=rating_keyboard(),
    )


# ============================================================
# SCORE
# ============================================================

@dp.callback_query(F.data.startswith("score:"))
async def score(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.split(":")[1]

    score_value = float(value)

    await save_score_for_current_profile(
        callback.message,
        callback.from_user.id,
        score_value,
        state,
    )

    await callback.answer()


@dp.callback_query(F.data == "custom_score")
async def custom_score_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.answer(
        "✏️ Введи оценку от 1 до 10.\n\n"
        "Можно использовать десятичные значения:\n"
        "5.6\n"
        "7.25\n"
        "8,4",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        Rating.custom_score
    )

    await callback.answer()


@dp.message(Rating.custom_score)
async def custom_score_input(
    message: Message,
    state: FSMContext,
):
    score_value = parse_number(
        message.text or ""
    )

    if score_value is None:
        await message.answer(
            "❌ Не понял оценку.\n\n"
            "Введи число от 1 до 10, например 5.6.",
            reply_markup=cancel_keyboard(),
        )
        return

    if score_value < 1 or score_value > 10:
        await message.answer(
            "❌ Оценка должна быть от 1 до 10.",
            reply_markup=cancel_keyboard(),
        )
        return

    await save_score_for_current_profile(
        message,
        message.from_user.id,
        score_value,
        state,
    )


async def save_score_for_current_profile(
    message: Message,
    rater_id: int,
    score_value: float,
    state: FSMContext,
):
    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    if not profile_user_id:
        await message.answer(
            "❌ Анкета для оценки больше недоступна.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    existing = await db.get_rating(
        rater_id,
        profile_user_id,
    )

    if existing:
        previous = float(
            existing["score"]
        )

        await state.update_data(
            pending_score=score_value,
        )

        await message.answer(
            f"⚠️ Ты уже оценивал эту анкету "
            f"на {previous:.1f}/10.\n\n"
            f"Ты хочешь изменить оценку на "
            f"{score_value:.1f}/10?",
            reply_markup=rating_confirm_keyboard(),
        )

        await state.set_state(
            Rating.confirm_change
        )

        return

    await db.save_rating(
        rater_id,
        profile_user_id,
        score_value,
    )

    await notify_rating(
        profile_user_id,
        rater_id,
        score_value,
    )

    await message.answer(
        f"✅ Ты поставил {score_value:.1f}/10.",
        reply_markup=after_rating_keyboard(),
    )

    await state.clear()


# ============================================================
# CONFIRM CHANGE
# ============================================================

@dp.callback_query(F.data == "confirm_rating")
async def confirm_rating(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    score_value = data.get(
        "pending_score"
    )

    if not profile_user_id or score_value is None:
        await callback.message.answer(
            "❌ Не удалось изменить оценку."
        )
        await state.clear()
        await callback.answer()
        return

    await db.save_rating(
        callback.from_user.id,
        profile_user_id,
        float(score_value),
    )

    await notify_rating(
        profile_user_id,
        callback.from_user.id,
        float(score_value),
    )

    await callback.message.answer(
        f"✅ Оценка изменена на "
        f"{float(score_value):.1f}/10.",
        reply_markup=after_rating_keyboard(),
    )

    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "cancel_rating_change")
async def cancel_rating_change(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.answer(
        "❌ Изменение оценки отменено.",
        reply_markup=main_menu(),
    )

    await callback.answer()


# ============================================================
# SAVE CURRENT PROFILE IN FSM
# ============================================================

async def store_rating_profile(
    state: FSMContext,
    profile_user_id: int,
):
    await state.update_data(
        rating_profile_user_id=profile_user_id
    )


# ============================================================
# IMPORTANT:
# We intercept profile photo messages and store current
# rating profile when showing it.
# ============================================================

_original_send_rating_profile = send_rating_profile


# ============================================================
# NOTIFICATION
# ============================================================

async def notify_rating(
    profile_user_id: int,
    rater_id: int,
    score_value: float,
):
    try:
        average = await db.get_average_rating(
            profile_user_id
        )

        await bot.send_message(
            profile_user_id,
            "⭐ Твою анкету оценили!\n\n"
            f"Оценка: {score_value:.1f}/10\n"
            f"Средняя оценка: {average:.1f}/10",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть оценившего",
                            callback_data=(
                                f"view_rater:{rater_id}"
                            ),
                        )
                    ]
                ]
            ),
        )

    except Exception:
        logging.exception(
            "Failed to send rating notification"
        )


# ============================================================
# VIEW RATER
# ============================================================

@dp.callback_query(
    F.data.startswith("view_rater:")
)
async def view_rater(
    callback: CallbackQuery,
):
    user_id = int(
        callback.data.split(":")[1]
    )

    profile = await db.get_public_profile(
        user_id
    )

    if not profile:
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    user = await db.get_user(
        user_id
    )

    if not user:
        await callback.answer(
            "Пользователь недоступен.",
            show_alert=True,
        )
        return

    average = await db.get_average_rating(
        user_id
    )

    text = (
        f"👤 @{user.get('username') or 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—')}\n"
        f"⚧ Пол: {user.get('gender', '—')}\n"
        f"⭐ Средняя оценка: {average:.1f}/10\n"
    )

    if profile.get("facts"):
        text += f"\n📝 Факты:\n{profile['facts']}\n"

    if profile.get("height"):
        text += f"\n📏 Рост: {profile['height']} см"

    if profile.get("weight"):
        text += f"\n⚖️ Вес: {profile['weight']} кг"

    await callback.message.answer_photo(
        profile["photo_id"],
        caption=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐ Оценить",
                        callback_data=(
                            f"rate_user:{user_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back_menu",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ============================================================
# RATE USER FROM NOTIFICATION
# ============================================================

@dp.callback_query(
    F.data.startswith("rate_user:")
)
async def rate_user_from_notification(
    callback: CallbackQuery,
    state: FSMContext,
):
    user_id = int(
        callback.data.split(":")[1]
    )

    profile = await db.get_public_profile(
        user_id
    )

    if not profile:
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    await state.update_data(
        rating_profile_user_id=user_id
    )

    await callback.message.answer_photo(
        profile["photo_id"],
        caption="⭐ Выбери оценку от 1 до 10.",
        reply_markup=rating_keyboard(),
    )

    await callback.answer()


# ============================================================
# ADVICE
# ============================================================

@dp.callback_query(F.data == "add_advice")
async def advice_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    if not data.get("rating_profile_user_id"):
        await callback.answer(
            "Анкета для совета не найдена.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "💡 Напиши совет для этого пользователя.\n\n"
        "Например: совет по стилю, причёске или фотографии.",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        Rating.advice
    )

    await callback.answer()


@dp.message(Rating.advice)
async def advice_received(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    if not text:
        await message.answer(
            "❌ Совет не может быть пустым.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()

    to_user_id = data.get(
        "rating_profile_user_id"
    )

    if not to_user_id:
        await message.answer(
            "❌ Не удалось определить пользователя."
        )
        await state.clear()
        return

    score = None

    existing = await db.get_rating(
        message.from_user.id,
        to_user_id,
    )

    if existing:
        score = float(
            existing["score"]
        )

    await db.create_advice(
        from_user_id=message.from_user.id,
        to_user_id=to_user_id,
        text=text,
        score=score,
    )

    try:
        await bot.send_message(
            to_user_id,
            "💡 Тебе оставили совет по внешности!\n\n"
            f"{text}",
        )
    except Exception:
        logging.exception(
            "Failed to send advice notification"
        )

    await message.answer(
        "✅ Совет отправлен.",
        reply_markup=main_menu(),
    )

    await state.clear()


# ============================================================
# REPORT
# ============================================================

@dp.callback_query(F.data == "report_current")
async def report_current(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    if not profile_user_id:
        await callback.answer(
            "Не удалось определить анкету.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "🚩 Напиши причину жалобы.",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        Report.reason
    )

    await callback.answer()


@dp.message(Report.reason)
async def report_reason(
    message: Message,
    state: FSMContext,
):
    reason = (message.text or "").strip()

    if not reason:
        await message.answer(
            "❌ Напиши причину жалобы.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    if not profile_user_id:
        await message.answer(
            "❌ Анкета не найдена."
        )
        await state.clear()
        return

    await db.create_report(
        reporter_id=message.from_user.id,
        profile_user_id=profile_user_id,
        reason=reason,
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚩 НОВАЯ ЖАЛОБА\n\n"
                f"От: {message.from_user.id}\n"
                f"На: {profile_user_id}\n"
                f"Причина: {reason}",
            )
        except Exception:
            logging.exception(
                "Failed to notify admin"
            )

    await message.answer(
        "✅ Жалоба отправлена модераторам.",
        reply_markup=main_menu(),
    )

    await state.clear()


# ============================================================
# ADMIN
# ============================================================

def is_admin(user_id: int):
    return user_id in ADMIN_IDS


@dp.message(Command("admin"))
async def admin_menu(
    message: Message,
):
    if not is_admin(message.from_user.id):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
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

    await message.answer(
        "🛠 Админ-панель",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data == "admin_reports")
async def admin_reports(
    callback: CallbackQuery,
):
    if not is_admin(callback.from_user.id):
        return

    reports = await db.get_reports()

    if not reports:
        await callback.message.answer(
            "🚩 Жалоб нет."
        )
        await callback.answer()
        return

    for report in reports[:20]:
        await callback.message.answer(
            f"🚩 Жалоба #{report['id']}\n\n"
            f"От: {report['reporter_id']}\n"
            f"На: {report['profile_user_id']}\n"
            f"Причина: {report['reason']}"
        )

    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.answer(
        "📢 Отправь сообщение для рассылки.",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        Broadcast.message
    )

    await callback.answer()


@dp.message(Broadcast.message)
async def broadcast_message(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    users = await db.get_all_users()

    sent = 0
    failed = 0

    for user in users or []:
        telegram_id = user["telegram_id"]

        try:
            await bot.copy_message(
                chat_id=telegram_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )

            sent += 1

        except Exception:
            failed += 1

        await asyncio.sleep(0.05)

    await db.create_broadcast(
        admin_id=message.from_user.id,
        message=message.text or "[медиа]",
        sent_count=sent,
        failed_count=failed,
    )

    await message.answer(
        f"📢 Рассылка завершена.\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=main_menu(),
    )

    await state.clear()


@dp.callback_query(F.data == "admin_broadcasts")
async def admin_broadcasts(
    callback: CallbackQuery,
):
    if not is_admin(callback.from_user.id):
        return

    broadcasts = await db.get_broadcasts()

    if not broadcasts:
        await callback.message.answer(
            "📜 История рассылок пуста."
        )
        await callback.answer()
        return

    for item in broadcasts[:20]:
        await callback.message.answer(
            f"📢 Рассылка #{item['id']}\n\n"
            f"Дата: {item.get('created_at', '—')}\n"
            f"Отправлено: {item.get('sent_count', 0)}\n"
            f"Ошибок: {item.get('failed_count', 0)}\n\n"
            f"{(item.get('message') or '')[:500]}"
        )

    await callback.answer()


# ============================================================
# RENDER WEB SERVICE
# ============================================================

async def health(request):
    return web.Response(
        text="OK",
        status=200,
    )


async def start_web_server():
    app = web.Application()

    app.router.add_get(
        "/",
        health,
    )

    app.router.add_get(
        "/health",
        health,
    )

    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logging.info(
        f"HTTP server listening on 0.0.0.0:{port}"
    )


# ============================================================
# FIX: store profile when sending rating profile
# ============================================================

async def show_next_rating_profile(
    message: Message,
    user_id: int,
):
    profile = await db.get_random_unrated_profile(
        user_id
    )

    if profile:
        await send_rating_profile_and_store(
            message,
            user_id,
            profile,
            False,
        )
        return

    profile = await db.get_random_rated_profile(
        user_id
    )

    if profile:
        rating = await db.get_rating(
            user_id,
            profile["user_id"],
        )

        previous = (
            float(rating["score"])
            if rating
            else None
        )

        warning = (
            "⚠️ Ты уже оценил все доступные новые анкеты.\n\n"
            "Теперь показываем анкеты, которые ты уже оценивал.\n\n"
            f"Твоя предыдущая оценка: {previous:.1f}/10"
            if previous is not None
            else
            "⚠️ Ты уже оценил все доступные новые анкеты.\n\n"
            "Теперь показываем анкеты, которые ты уже оценивал."
        )

        await message.answer(warning)

        await send_rating_profile_and_store(
            message,
            user_id,
            profile,
            True,
            previous,
        )

        return

    await message.answer(
        "😔 Сейчас нет доступных анкет.",
        reply_markup=main_menu(),
    )


async def send_rating_profile_and_store(
    message: Message,
    user_id: int,
    profile: dict,
    repeated: bool = False,
    previous_score: float | None = None,
):
    state = dp.fsm.get_context(
        bot=bot,
        chat_id=message.chat.id,
        user_id=user_id,
    )

    await state.update_data(
        rating_profile_user_id=profile["user_id"]
    )

    user = await db.get_user(
        profile["user_id"]
    )

    if not user:
        return

    text = (
        f"👤 @{user.get('username') or 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—')}\n"
        f"⚧ Пол: {user.get('gender', '—')}\n"
    )

    if profile.get("facts"):
        text += f"\n📝 Факты:\n{profile['facts']}\n"

    if profile.get("height"):
        text += f"\n📏 Рост: {profile['height']} см"

    if profile.get("weight"):
        text += f"\n⚖️ Вес: {profile['weight']} кг"

    if repeated and previous_score is not None:
        text += (
            f"\n\n⚠️ Предыдущая оценка: "
            f"{previous_score:.1f}/10"
        )

    await message.answer_photo(
        profile["photo_id"],
        caption=text,
        reply_markup=rating_keyboard(),
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    await start_web_server()

    logging.info("Bot starting...")

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    me = await bot.get_me()

    logging.info(
        f"Telegram bot connected: "
        f"@{me.username} (id={me.id})"
    )

    logging.info("Starting polling...")

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
