import asyncio
import logging
import os
import re

from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
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
    language = State()
    accepted = State()
    age = State()
    gender = State()


class ProfileCreation(StatesGroup):
    photo = State()
    facts = State()
    height = State()
    weight = State()


class Rating(StatesGroup):
    score = State()
    advice = State()


class Report(StatesGroup):
    reason = State()


class Broadcast(StatesGroup):
    message = State()


# ============================================================
# KEYBOARDS
# ============================================================

def language_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇷🇺 Русский",
                    callback_data="lang_ru",
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English",
                    callback_data="lang_en",
                ),
            ]
        ]
    )


def agreement_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Согласен",
                    callback_data="agree",
                )
            ]
        ]
    )


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
            ]
        ]
    )


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="⭐ Рейтить"),
                KeyboardButton(text="👤 Моя анкета"),
            ],
            [
                KeyboardButton(text="➕ Создать анкету"),
            ],
        ],
        resize_keyboard=True,
    )


def rating_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1",
                    callback_data="score_1",
                ),
                InlineKeyboardButton(
                    text="2",
                    callback_data="score_2",
                ),
                InlineKeyboardButton(
                    text="3",
                    callback_data="score_3",
                ),
                InlineKeyboardButton(
                    text="4",
                    callback_data="score_4",
                ),
                InlineKeyboardButton(
                    text="5",
                    callback_data="score_5",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="6",
                    callback_data="score_6",
                ),
                InlineKeyboardButton(
                    text="7",
                    callback_data="score_7",
                ),
                InlineKeyboardButton(
                    text="8",
                    callback_data="score_8",
                ),
                InlineKeyboardButton(
                    text="9",
                    callback_data="score_9",
                ),
                InlineKeyboardButton(
                    text="10",
                    callback_data="score_10",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Другая оценка",
                    callback_data="score_custom",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚩 Пожаловаться",
                    callback_data="report",
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
                    callback_data="advice",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Следующая анкета",
                    callback_data="next_profile",
                )
            ],
        ]
    )


# ============================================================
# HELPERS
# ============================================================

async def require_profile(
    message: Message,
):
    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile or profile.get("status") != "active":
        await message.answer(
            "❗ Сначала создай анкету.",
            reply_markup=main_keyboard(),
        )
        return None

    return profile


async def show_profile(
    message: Message,
    profile: dict,
    show_rating: bool = True,
):
    average = await db.get_average_rating(
        profile["user_id"]
    )

    username = profile.get("username") or "без username"

    text = (
        f"👤 @{username}\n"
        f"🎂 Возраст: {profile.get('age', '—')}\n"
        f"⚧ Пол: {profile.get('gender', '—')}\n"
    )

    if profile.get("height"):
        text += f"📏 Рост: {profile['height']} см\n"

    if profile.get("weight"):
        text += f"⚖️ Вес: {profile['weight']} кг\n"

    if profile.get("facts"):
        text += f"\n📝 Факты:\n{profile['facts']}\n"

    if show_rating:
        text += f"\n⭐ Средняя оценка: {average:.1f}/10"

    await message.answer_photo(
        photo=profile["photo_id"],
        caption=text,
        reply_markup=rating_keyboard(),
    )


async def send_next_profile(
    message: Message,
):
    profile = await db.next_unrated_profile(
        message.from_user.id
    )

    if profile:
        await show_profile(message, profile)
        return

    old_profile = await db.next_rated_profile(
        message.from_user.id
    )

    if old_profile:
        await message.answer(
            "⚠️ Ты уже оценил все доступные анкеты.\n\n"
            "Сейчас будут показаны анкеты, которые "
            "ты уже оценивал.\n\n"
            "Если изменишь оценку, предыдущая будет заменена."
        )

        old_rating = await db.get_rating(
            message.from_user.id,
            old_profile["user_id"],
        )

        await show_profile(
            message,
            old_profile,
        )

        if old_rating:
            await message.answer(
                f"Твоя предыдущая оценка: "
                f"{float(old_rating['score']):.1f}/10"
            )

        return

    await message.answer(
        "😔 Пока нет доступных анкет.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    user = await db.get_user(
        message.from_user.id
    )

    if not user:
        await db.create_user(
            message.from_user.id,
            message.from_user.username,
        )

    user = await db.get_user(
        message.from_user.id
    )

    if not user.get("language"):
        await message.answer(
            "🌍 Выбери язык / Choose language:",
            reply_markup=language_keyboard(),
        )

        await state.set_state(
            Registration.language
        )
        return

    if not user.get("accepted_rules"):
        await message.answer(
            "Перед созданием анкеты\n\n"
            "Ботом можно пользоваться только с 18 лет.\n"
            "Возраст указывается в анкете и виден другим.\n"
            "На фото — ваше настоящее лицо, иначе анкету удалят.\n"
            "В боте работает активная модерация.\n\n"
            "Нажимая «Согласен», вы принимаете "
            "правила и политику.",
            reply_markup=agreement_keyboard(),
        )

        await state.set_state(
            Registration.accepted
        )
        return

    await show_home(message)


async def show_home(message: Message):
    username = message.from_user.username

    if username:
        name = f"@{username}"
    else:
        name = message.from_user.first_name or "пользователь"

    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile:
        await message.answer(
            f"👋 Привет, {name}!\n\n"
            "✨ Здесь ты можешь получить оценку "
            "своей внешности от других пользователей, "
            "оценивать других, получать советы и многое другое.\n\n"
            "💫 Всё бесплатно!\n\n"
            "Что хочешь сделать?\n\n"
            "⚠️ Для использования бота необходимо создать анкету.",
            reply_markup=main_keyboard(),
        )
    else:
        await message.answer(
            f"👋 Привет, {name}!\n\n"
            "✨ Что хочешь сделать?",
            reply_markup=main_keyboard(),
        )


# ============================================================
# LANGUAGE
# ============================================================

@dp.callback_query(F.data.in_({"lang_ru", "lang_en"}))
async def language_selected(
    callback: CallbackQuery,
    state: FSMContext,
):
    language = (
        "ru"
        if callback.data == "lang_ru"
        else "en"
    )

    await db.update_user(
        callback.from_user.id,
        {
            "language": language,
        },
    )

    await callback.message.edit_text(
        "Перед созданием анкеты\n\n"
        "Ботом можно пользоваться только с 18 лет.\n"
        "Возраст указывается в анкете и виден другим.\n"
        "На фото — ваше настоящее лицо, иначе анкету удалят.\n"
        "В боте работает активная модерация.\n\n"
        "Нажимая «Согласен», вы принимаете "
        "правила и политику.",
        reply_markup=agreement_keyboard(),
    )

    await state.set_state(
        Registration.accepted
    )

    await callback.answer()


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

    await callback.message.answer(
        "🎂 Укажи свой возраст:"
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
    try:
        age = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Введи возраст числом."
        )
        return

    if age < 18 or age > 100:
        await message.answer(
            "❌ Бот доступен только с 18 лет.\n"
            "Укажи корректный возраст."
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

    await callback.message.answer(
        "👋 Отлично!\n\n"
        "Теперь можно создать анкету.\n"
        "Нажми «Создать анкету».",
        reply_markup=main_keyboard(),
    )

    await state.clear()
    await callback.answer()


# ============================================================
# CREATE PROFILE
# ============================================================

@dp.message(F.text == "➕ Создать анкету")
async def create_profile_start(
    message: Message,
    state: FSMContext,
):
    user = await db.get_user(
        message.from_user.id
    )

    if not user or not user.get("accepted_rules"):
        await message.answer(
            "❗ Сначала пройди регистрацию через /start."
        )
        return

    await message.answer(
        "📸 Отправь фотографию своего лица.\n\n"
        "На фотографии должно быть настоящее лицо."
    )

    await state.set_state(
        ProfileCreation.photo
    )


@dp.message(
    ProfileCreation.photo,
    F.photo,
)
async def profile_photo(
    message: Message,
    state: FSMContext,
):
    photo_id = message.photo[-1].file_id

    await state.update_data(
        photo_id=photo_id
    )

    await message.answer(
        "📝 Напиши несколько фактов о себе.\n\n"
        "Это необязательно.\n"
        "Если не хочешь добавлять факты — напиши «нет»."
    )

    await state.set_state(
        ProfileCreation.facts
    )


@dp.message(ProfileCreation.photo)
async def profile_photo_invalid(
    message: Message,
):
    await message.answer(
        "❌ Отправь именно фотографию."
    )


@dp.message(ProfileCreation.facts)
async def profile_facts(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    if text.lower() in {
        "нет",
        "no",
        "-",
    }:
        text = None

    await state.update_data(
        facts=text
    )

    await message.answer(
        "📏 Укажи рост в сантиметрах.\n"
        "Например: 180\n\n"
        "Если не хочешь указывать — напиши «нет»."
    )

    await state.set_state(
        ProfileCreation.height
    )


@dp.message(ProfileCreation.height)
async def profile_height(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    height = None

    if text.lower() not in {
        "нет",
        "no",
        "-",
    }:
        try:
            height = float(text)
        except ValueError:
            await message.answer(
                "❌ Введи рост числом."
            )
            return

        if height < 100 or height > 250:
            await message.answer(
                "❌ Укажи реальный рост."
            )
            return

    await state.update_data(
        height=height
    )

    await message.answer(
        "⚖️ Укажи вес в килограммах.\n"
        "Например: 75\n\n"
        "Если не хочешь указывать — напиши «нет»."
    )

    await state.set_state(
        ProfileCreation.weight
    )


@dp.message(ProfileCreation.weight)
async def profile_weight(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    weight = None

    if text.lower() not in {
        "нет",
        "no",
        "-",
    }:
        try:
            weight = float(text)
        except ValueError:
            await message.answer(
                "❌ Введи вес числом."
            )
            return

        if weight < 30 or weight > 300:
            await message.answer(
                "❌ Укажи реальный вес."
            )
            return

    data = await state.get_data()

    await db.create_profile(
        telegram_id=message.from_user.id,
        photo_id=data["photo_id"],
        facts=data.get("facts"),
        height=data.get("height"),
        weight=weight,
    )

    await state.clear()

    await message.answer(
        "✅ Анкета создана!",
        reply_markup=main_keyboard(),
    )

    await message.answer(
        "Теперь другие пользователи смогут "
        "оценивать твою анкету."
    )


# ============================================================
# MY PROFILE
# ============================================================

@dp.message(F.text == "👤 Моя анкета")
async def my_profile(
    message: Message,
):
    profile = await require_profile(message)

    if not profile:
        return

    average = await db.get_average_rating(
        message.from_user.id
    )

    received = await db.get_received_ratings_count(
        message.from_user.id
    )

    text = (
        f"👤 Твоя анкета\n\n"
        f"⭐ Средняя оценка: {average:.1f}/10\n"
        f"📊 Оценок получено: {received}\n\n"
    )

    if profile.get("facts"):
        text += f"📝 Факты: {profile['facts']}\n"

    if profile.get("height"):
        text += f"📏 Рост: {profile['height']} см\n"

    if profile.get("weight"):
        text += f"⚖️ Вес: {profile['weight']} кг\n"

    await message.answer_photo(
        profile["photo_id"],
        caption=text,
    )


# ============================================================
# RATE
# ============================================================

@dp.message(F.text == "⭐ Рейтить")
async def rate_start(
    message: Message,
):
    profile = await require_profile(message)

    if not profile:
        return

    await send_next_profile(message)


@dp.callback_query(F.data == "next_profile")
async def next_profile(
    callback: CallbackQuery,
):
    await callback.message.delete()

    await send_next_profile(
        callback.message
    )

    await callback.answer()


# ============================================================
# SCORE
# ============================================================

@dp.callback_query(
    F.data.startswith("score_")
)
async def score_selected(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.replace(
        "score_",
        "",
    )

    if value == "custom":
        await callback.message.answer(
            "✏️ Введи оценку от 1 до 10.\n"
            "Можно использовать десятичные значения.\n"
            "Например: 5.6"
        )

        await state.set_state(
            Rating.score
        )

        await callback.answer()
        return

    score = float(value)

    await process_score(
        callback,
        state,
        score,
    )


@dp.message(Rating.score)
async def custom_score(
    message: Message,
    state: FSMContext,
):
    try:
        score = float(
            message.text.replace(",", ".")
        )
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Введи число от 1 до 10."
        )
        return

    if score < 1 or score > 10:
        await message.answer(
            "❌ Оценка должна быть от 1 до 10."
        )
        return

    profile = await db.next_unrated_profile(
        message.from_user.id
    )

    if not profile:
        profile = await db.next_rated_profile(
            message.from_user.id
        )

    if not profile:
        await message.answer(
            "Анкета больше недоступна."
        )
        await state.clear()
        return

    existing = await db.get_rating(
        message.from_user.id,
        profile["user_id"],
    )

    if existing:
        await message.answer(
            f"⚠️ Ты уже оценивал эту анкету "
            f"на {float(existing['score']):.1f}/10.\n\n"
            f"Ты уверен, что хочешь изменить оценку "
            f"на {score:.1f}/10?\n\n"
            "Новая оценка заменит старую."
        )

        await state.update_data(
            profile_user_id=profile["user_id"],
            new_score=score,
        )

        await message.answer(
            "Напиши «да», чтобы изменить оценку."
        )

        await state.set_state(
            Rating.score
        )

        return

    await db.create_rating(
        message.from_user.id,
        profile["user_id"],
        score,
    )

    await notify_profile_owner(
        profile["user_id"],
        message.from_user.id,
        score,
    )

    await message.answer(
        f"✅ Ты поставил оценку {score:.1f}/10.",
        reply_markup=after_rating_keyboard(),
    )

    await state.clear()


async def process_score(
    callback: CallbackQuery,
    state: FSMContext,
    score: float,
):
    profile = await db.next_unrated_profile(
        callback.from_user.id
    )

    if not profile:
        profile = await db.next_rated_profile(
            callback.from_user.id
        )

    if not profile:
        await callback.message.answer(
            "Анкет больше нет."
        )
        await state.clear()
        await callback.answer()
        return

    existing = await db.get_rating(
        callback.from_user.id,
        profile["user_id"],
    )

    if existing:
        await callback.message.answer(
            f"⚠️ Ты уже оценивал эту анкету "
            f"на {float(existing['score']):.1f}/10.\n\n"
            "Ты уверен, что хочешь изменить оценку?\n"
            "Новая оценка заменит предыдущую."
        )

        await state.update_data(
            profile_user_id=profile["user_id"],
            new_score=score,
        )

        await callback.message.answer(
            "Напиши «да», чтобы подтвердить."
        )

        await state.set_state(
            Rating.score
        )

        await callback.answer()
        return

    await db.create_rating(
        callback.from_user.id,
        profile["user_id"],
        score,
    )

    await notify_profile_owner(
        profile["user_id"],
        callback.from_user.id,
        score,
    )

    await callback.message.answer(
        f"✅ Оценка {score:.1f}/10 сохранена.",
        reply_markup=after_rating_keyboard(),
    )

    await callback.answer()


@dp.message(Rating.score)
async def confirm_change(
    message: Message,
    state: FSMContext,
):
    if message.text.lower().strip() not in {
        "да",
        "yes",
    }:
        await message.answer(
            "❌ Изменение отменено."
        )
        await state.clear()
        return

    data = await state.get_data()

    profile_user_id = data.get(
        "profile_user_id"
    )

    score = data.get(
        "new_score"
    )

    if not profile_user_id or score is None:
        await message.answer(
            "❌ Не удалось изменить оценку."
        )
        await state.clear()
        return

    await db.create_rating(
        message.from_user.id,
        profile_user_id,
        float(score),
    )

    await notify_profile_owner(
        profile_user_id,
        message.from_user.id,
        float(score),
    )

    await message.answer(
        f"✅ Оценка изменена на {float(score):.1f}/10.",
        reply_markup=after_rating_keyboard(),
    )

    await state.clear()


# ============================================================
# NOTIFICATION
# ============================================================

async def notify_profile_owner(
    profile_user_id: int,
    rater_id: int,
    score: float,
):
    try:
        average = await db.get_average_rating(
            profile_user_id
        )

        await bot.send_message(
            profile_user_id,
            f"⭐ Твою анкету оценили!\n\n"
            f"Оценка: {score:.1f}/10\n"
            f"Твоя средняя оценка: {average:.1f}/10",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть оценившего",
                            callback_data=(
                                f"rater:{rater_id}"
                            ),
                        )
                    ]
                ]
            ),
        )

    except Exception:
        logging.exception(
            "Could not notify profile owner"
        )


# ============================================================
# VIEW RATER
# ============================================================

@dp.callback_query(
    F.data.startswith("rater:")
)
async def view_rater(
    callback: CallbackQuery,
):
    user_id = int(
        callback.data.split(":")[1]
    )

    profile = await db.get_profile(
        user_id
    )

    if not profile:
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    average = await db.get_average_rating(
        user_id
    )

    username = profile.get("username") or "без username"

    text = (
        f"👤 @{username}\n"
        f"🎂 Возраст: {profile.get('age', '—')}\n"
        f"⚧ Пол: {profile.get('gender', '—')}\n"
        f"⭐ Средняя оценка: {average:.1f}/10\n"
    )

    if profile.get("facts"):
        text += f"\n📝 {profile['facts']}\n"

    if profile.get("height"):
        text += f"📏 Рост: {profile['height']} см\n"

    if profile.get("weight"):
        text += f"⚖️ Вес: {profile['weight']} кг\n"

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
                ]
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
async def rate_user(
    callback: CallbackQuery,
):
    user_id = int(
        callback.data.split(":")[1]
    )

    profile = await db.get_profile(
        user_id
    )

    if not profile:
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    await callback.message.answer_photo(
        profile["photo_id"],
        caption=(
            "⭐ Выбери оценку от 1 до 10."
        ),
        reply_markup=rating_keyboard(),
    )

    await callback.answer()


# ============================================================
# ADVICE
# ============================================================

@dp.callback_query(F.data == "advice")
async def advice_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.answer(
        "💡 Напиши совет, который поможет "
        "улучшить внешность.\n\n"
        "Совет должен быть адекватным и без оскорблений."
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
    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Совет не может быть пустым."
        )
        return

    await message.answer(
        "💡 Чтобы отправить совет, "
        "сначала выбери анкету для оценки."
    )

    await state.clear()


# ============================================================
# REPORT
# ============================================================

@dp.callback_query(F.data == "report")
async def report_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.answer(
        "🚩 Почему ты хочешь пожаловаться?\n\n"
        "Напиши причину одним сообщением."
    )

    await state.set_state(
        Report.reason
    )

    await callback.answer()


@dp.message(Report.reason)
async def report_received(
    message: Message,
    state: FSMContext,
):
    reason = message.text.strip()

    profile = await db.next_unrated_profile(
        message.from_user.id
    )

    if not profile:
        profile = await db.next_rated_profile(
            message.from_user.id
        )

    if not profile:
        await message.answer(
            "❌ Не удалось определить анкету."
        )
        await state.clear()
        return

    await db.create_report(
        reporter_id=message.from_user.id,
        profile_user_id=profile["user_id"],
        reason=reason,
    )

    await message.answer(
        "✅ Жалоба отправлена модераторам."
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚩 НОВАЯ ЖАЛОБА\n\n"
                f"От: {message.from_user.id}\n"
                f"На: {profile['user_id']}\n"
                f"Причина: {reason}",
            )
        except Exception:
            logging.exception(
                "Could not notify admin"
            )

    await state.clear()


# ============================================================
# DELETE PROFILE
# ============================================================

@dp.message(Command("delete_profile"))
async def delete_profile(
    message: Message,
):
    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile:
        await message.answer(
            "У тебя нет анкеты."
        )
        return

    await db.delete_profile(
        message.from_user.id
    )

    await message.answer(
        "🗑 Анкета удалена.",
        reply_markup=main_keyboard(),
    )


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
            "Жалоб нет."
        )
        await callback.answer()
        return

    for report in reports[:20]:
        await callback.message.answer(
            f"🚩 Жалоба #{report['id']}\n\n"
            f"От: {report['reporter_id']}\n"
            f"На: {report['profile_user_id']}\n"
            f"Причина: {report['reason']}\n"
            f"Статус: {report['status']}"
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
        "📢 Отправь сообщение для рассылки."
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
        f"❌ Ошибок: {failed}"
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
            "История рассылок пуста."
        )
        await callback.answer()
        return

    for item in broadcasts[:20]:
        await callback.message.answer(
            f"📢 Рассылка #{item['id']}\n\n"
            f"Дата: {item['created_at']}\n"
            f"Отправлено: {item['sent_count']}\n"
            f"Ошибок: {item['failed_count']}\n\n"
            f"{item['message'][:500]}"
        )

    await callback.answer()


# ============================================================
# HTTP SERVER FOR RENDER
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
        host="0.0.0.0",
        port=port,
    )

    await site.start()

    logging.info(
        f"HTTP server listening on 0.0.0.0:{port}"
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    await start_web_server()

    logging.info(
        "Bot started"
    )

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
