import os
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
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

from db import DB


logging.basicConfig(level=logging.INFO)


BOT_TOKEN = os.environ["BOT_TOKEN"]

ADMIN_IDS = {
    int(x.strip())
    for x in os.environ["ADMIN_IDS"].split(",")
    if x.strip()
}

SUPABASE_URL = os.environ["SUPABASE_URL"]

SUPABASE_SERVICE_ROLE_KEY = os.environ[
    "SUPABASE_SERVICE_ROLE_KEY"
]


bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    ),
)

dp = Dispatcher()

db = DB(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)


# =========================
# STATES
# =========================

class RegistrationFSM(StatesGroup):
    age = State()


class ProfileFSM(StatesGroup):
    photo = State()
    facts = State()
    height = State()
    weight = State()


class RatingFSM(StatesGroup):
    score = State()
    advice = State()


class ReportFSM(StatesGroup):
    reason = State()
    comment = State()


class BroadcastFSM(StatesGroup):
    message = State()


# =========================
# KEYBOARDS
# =========================

def language_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇷🇺 Русский",
                    callback_data="lang:ru",
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English",
                    callback_data="lang:en",
                ),
            ]
        ]
    )


def rules_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Согласен",
                    callback_data="agree",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Правила",
                    callback_data="rules",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔒 Политика конфиденциальности",
                    callback_data="privacy",
                )
            ],
        ]
    )


def gender_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨 Мужчина",
                    callback_data="gender:male",
                ),
                InlineKeyboardButton(
                    text="👩 Женщина",
                    callback_data="gender:female",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚪ Другое",
                    callback_data="gender:other",
                )
            ],
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
                KeyboardButton(text="✏️ Изменить анкету"),
                KeyboardButton(text="📊 Моя статистика"),
            ],
            [
                KeyboardButton(text="🗑 Удалить анкету"),
            ],
        ],
        resize_keyboard=True,
    )


def create_profile_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="👤 Создать анкету"
                )
            ]
        ],
        resize_keyboard=True,
    )


def profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Оценить",
                    callback_data="rate_current",
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
                    text="➡️ Следующая",
                    callback_data="next_profile",
                )
            ],
        ]
    )


def score_keyboard():
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
                    text="🔢 Ввести число",
                    callback_data="score:custom",
                )
            ],
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚨 Жалобы",
                    callback_data="admin:reports",
                ),
                InlineKeyboardButton(
                    text="🛡 Модерация",
                    callback_data="admin:moderation",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📢 Рассылка",
                    callback_data="admin:broadcast",
                ),
                InlineKeyboardButton(
                    text="📜 История",
                    callback_data="admin:history",
                ),
            ],
        ]
    )


# =========================
# HELPERS
# =========================

async def send_rules(message: Message):
    await message.answer(
        "Перед созданием анкеты:\n\n"
        "Ботом можно пользоваться с 18 лет.\n"
        "Возраст указывается в анкете и виден другим пользователям.\n"
        "На фото — ваше настоящее лицо, иначе анкету удалят.\n"
        "В боте работает активная модерация.\n\n"
        "Нажимая «Согласен», вы принимаете правила и политику.",
        reply_markup=rules_keyboard(),
    )


async def send_profile(chat_id: int, user_id: int):
    profile = await db.get_public_profile(user_id)

    if not profile:
        return False

    gender = {
        "male": "Мужчина",
        "female": "Женщина",
        "other": "Другое",
    }.get(
        profile.get("gender"),
        profile.get("gender"),
    )

    text = (
        f"👤 @{profile.get('username') or 'пользователь'}\n\n"
        f"🎂 {profile.get('age')} лет\n"
        f"⚧ {gender}\n"
    )

    if profile.get("height") is not None:
        text += f"📏 {profile['height']} см\n"

    if profile.get("weight") is not None:
        text += f"⚖️ {profile['weight']} кг\n"

    if profile.get("facts"):
        text += f"\n📝 {profile['facts']}\n"

    average = profile.get("average")

    if average is not None:
        text += (
            f"\n⭐ Средняя оценка: "
            f"{float(average):.1f}/10"
        )

    await bot.send_photo(
        chat_id,
        profile["photo_id"],
        caption=text,
        reply_markup=profile_keyboard(),
    )

    return True


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    user = await db.get_user(
        message.from_user.id
    )

    if not user:
        await db.create_user(
            message.from_user.id,
            message.from_user.username,
        )

        await message.answer(
            "Выберите язык / Choose language:",
            reply_markup=language_keyboard(),
        )

        return

    await db.update_user(
        message.from_user.id,
        username=message.from_user.username,
    )

    if not user.get("language"):
        await message.answer(
            "Выберите язык / Choose language:",
            reply_markup=language_keyboard(),
        )
        return

    if not user.get("accepted_rules"):
        await send_rules(message)
        return

    if not user.get("gender"):
        await message.answer(
            "Выберите пол:",
            reply_markup=gender_keyboard(),
        )
        return

    if not user.get("age"):
        await message.answer(
            "Введите ваш возраст (18+):"
        )
        await state.set_state(
            RegistrationFSM.age
        )
        return

    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile or profile.get("status") == "deleted":
        await message.answer(
            "Сначала создайте анкету.",
            reply_markup=create_profile_keyboard(),
        )
        return

    await message.answer(
        f"👋 Привет, "
        f"{message.from_user.mention_html()}!\n\n"
        "✨ Здесь ты можешь получить оценку "
        "своей внешности от других пользователей, "
        "оценивать других, получать советы и "
        "многое другое.\n\n"
        "💫 Всё бесплатно!\n\n"
        "Что хочешь сделать?",
        reply_markup=main_keyboard(),
    )


# =========================
# LANGUAGE
# =========================

@dp.callback_query(F.data.startswith("lang:"))
async def language(call: CallbackQuery):
    language = call.data.split(":")[1]

    await db.update_user(
        call.from_user.id,
        language=language,
    )

    await call.message.edit_text(
        "Перед созданием анкеты:\n\n"
        "Ботом можно пользоваться с 18 лет.\n"
        "Возраст указывается в анкете и виден другим пользователям.\n"
        "На фото — ваше настоящее лицо, иначе анкету удалят.\n"
        "В боте работает активная модерация.\n\n"
        "Нажимая «Согласен», вы принимаете правила и политику.",
        reply_markup=rules_keyboard(),
    )

    await call.answer()


# =========================
# RULES
# =========================

@dp.callback_query(F.data == "rules")
async def rules(call: CallbackQuery):
    await call.answer()

    await call.message.answer(
        "Правила:\n\n"
        "• Бот предназначен для пользователей 18+.\n"
        "• На фото должно быть ваше настоящее лицо.\n"
        "• Запрещены чужие фотографии.\n"
        "• Работает активная модерация.\n"
        "• Нарушающие правила анкеты могут быть удалены."
    )


@dp.callback_query(F.data == "privacy")
async def privacy(call: CallbackQuery):
    await call.answer()

    await call.message.answer(
        "Политика конфиденциальности:\n\n"
        "Бот хранит данные, необходимые для работы "
        "анкет, рейтингов, советов, жалоб и модерации."
    )


@dp.callback_query(F.data == "agree")
async def agree(call: CallbackQuery):
    await db.update_user(
        call.from_user.id,
        accepted_rules=True,
    )

    await call.message.edit_text(
        "Выберите пол:",
        reply_markup=gender_keyboard(),
    )

    await call.answer()


# =========================
# GENDER / AGE
# =========================

@dp.callback_query(F.data.startswith("gender:"))
async def gender(
    call: CallbackQuery,
    state: FSMContext,
):
    value = call.data.split(":")[1]

    await db.update_user(
        call.from_user.id,
        gender=value,
    )

    await call.message.answer(
        "Введите ваш возраст (18+):"
    )

    await state.set_state(
        RegistrationFSM.age
    )

    await call.answer()


@dp.message(RegistrationFSM.age)
async def age(
    message: Message,
    state: FSMContext,
):
    try:
        value = int(message.text.strip())
    except ValueError:
        await message.answer(
            "Введите возраст целым числом."
        )
        return

    if value < 18:
        await message.answer(
            "Ботом можно пользоваться с 18 лет."
        )
        return

    if value > 100:
        await message.answer(
            "Введите корректный возраст."
        )
        return

    await db.update_user(
        message.from_user.id,
        age=value,
    )

    await state.clear()

    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile:
        await message.answer(
            "Теперь создадим анкету.\n\n"
            "Отправьте ваше настоящее фото лица."
        )

        await state.set_state(
            ProfileFSM.photo
        )
    else:
        await message.answer(
            "Готово.",
            reply_markup=main_keyboard(),
        )


# =========================
# CREATE PROFILE
# =========================

@dp.message(F.text == "👤 Создать анкету")
async def create_profile(
    message: Message,
    state: FSMContext,
):
    await message.answer(
        "Отправьте фото для анкеты.\n\n"
        "На фото должно быть ваше настоящее лицо."
    )

    await state.set_state(
        ProfileFSM.photo
    )


@dp.message(ProfileFSM.photo, F.photo)
async def photo_received(
    message: Message,
    state: FSMContext,
):
    photo_id = message.photo[-1].file_id

    await state.update_data(
        photo_id=photo_id
    )

    await message.answer(
        "Напишите факты о себе.\n"
        "Можно отправить «-», чтобы пропустить."
    )

    await state.set_state(
        ProfileFSM.facts
    )


@dp.message(ProfileFSM.photo)
async def wrong_photo(message: Message):
    await message.answer(
        "Нужно отправить фотографию."
    )


@dp.message(ProfileFSM.facts)
async def facts_received(
    message: Message,
    state: FSMContext,
):
    facts = message.text.strip()

    if facts == "-":
        facts = None

    await state.update_data(
        facts=facts
    )

    await message.answer(
        "Введите рост в см.\n"
        "Или отправьте «-», чтобы пропустить."
    )

    await state.set_state(
        ProfileFSM.height
    )


@dp.message(ProfileFSM.height)
async def height_received(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    if text == "-":
        height = None
    else:
        try:
            height = float(text)
        except ValueError:
            await message.answer(
                "Введите рост числом."
            )
            return

    await state.update_data(
        height=height
    )

    await message.answer(
        "Введите вес в кг.\n"
        "Или отправьте «-», чтобы пропустить."
    )

    await state.set_state(
        ProfileFSM.weight
    )


@dp.message(ProfileFSM.weight)
async def weight_received(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    if text == "-":
        weight = None
    else:
        try:
            weight = float(text)
        except ValueError:
            await message.answer(
                "Введите вес числом."
            )
            return

    data = await state.get_data()

    await db.upsert_profile(
        message.from_user.id,
        photo_id=data["photo_id"],
        facts=data.get("facts"),
        height=data.get("height"),
        weight=weight,
        status="pending",
    )

    await state.clear()

    await message.answer(
        "Анкета отправлена на модерацию.",
        reply_markup=main_keyboard(),
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🛡 Новая анкета на модерации.\n"
                f"Пользователь: {message.from_user.id}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🛡 Открыть модерацию",
                                callback_data="admin:moderation",
                            )
                        ]
                    ]
                ),
            )
        except Exception:
            pass


# =========================
# RATING
# =========================

@dp.message(F.text == "⭐ Рейтить")
async def rate_start(message: Message):
    profile = await db.get_profile(
        message.from_user.id
    )

    if not profile:
        await message.answer(
            "Сначала создайте анкету."
        )
        return

    target = await db.next_unrated(
        message.from_user.id
    )

    repeated = False

    if not target:
        target = await db.next_already_rated(
            message.from_user.id
        )
        repeated = True

    if not target:
        await message.answer(
            "Анкет больше нет."
        )
        return

    await db.set_current_target(
        message.from_user.id,
        target["user_id"],
    )

    if repeated:
        await message.answer(
            "⚠️ Ты уже оценивал доступные анкеты.\n\n"
            "Сейчас будут показаны анкеты, которые "
            "ты уже оценивал.\n"
            "Новая оценка заменит предыдущую."
        )

    await send_profile(
        message.chat.id,
        target["user_id"],
    )


@dp.callback_query(F.data == "next_profile")
async def next_profile(call: CallbackQuery):
    target = await db.next_unrated(
        call.from_user.id
    )

    repeated = False

    if not target:
        target = await db.next_already_rated(
            call.from_user.id
        )
        repeated = True

    if not target:
        await call.answer(
            "Анкет больше нет.",
            show_alert=True,
        )
        return

    await db.set_current_target(
        call.from_user.id,
        target["user_id"],
    )

    if repeated:
        await call.message.answer(
            "⚠️ Ты уже оценивал доступные анкеты.\n"
            "Предыдущая оценка будет заменена."
        )

    await send_profile(
        call.message.chat.id,
        target["user_id"],
    )

    await call.answer()


@dp.callback_query(F.data == "rate_current")
async def rate_current(
    call: CallbackQuery,
    state: FSMContext,
):
    target = await db.get_current_target(
        call.from_user.id
    )

    if not target:
        await call.answer(
            "Анкета не выбрана.",
            show_alert=True,
        )
        return

    old = await db.get_rating(
        call.from_user.id,
        target,
    )

    if old:
        await call.message.answer(
            "⚠️ Ты уже оценивал этого пользователя.\n\n"
            f"Предыдущая оценка: {old['score']}/10\n\n"
            "Новая оценка заменит предыдущую."
        )

    await call.message.answer(
        "Выбери оценку от 1 до 10:",
        reply_markup=score_keyboard(),
    )

    await state.set_state(
        RatingFSM.score
    )

    await call.answer()


@dp.callback_query(
    RatingFSM.score,
    F.data.startswith("score:")
)
async def score_button(
    call: CallbackQuery,
    state: FSMContext,
):
    value = call.data.split(":")[1]

    if value == "custom":
        await call.message.answer(
            "Введите число от 1.0 до 10.0.\n"
            "Например: 5.6"
        )
        return

    await save_score(
        call,
        float(value),
        state,
    )


@dp.message(RatingFSM.score)
async def score_text(
    message: Message,
    state: FSMContext,
):
    try:
        score = float(
            message.text.replace(",", ".")
        )
    except ValueError:
        await message.answer(
            "Введите число от 1.0 до 10.0."
        )
        return

    await save_score(
        message,
        score,
        state,
    )


async def save_score(
    event,
    score: float,
    state: FSMContext,
):
    if score < 1 or score > 10:
        msg = (
            event.message
            if isinstance(event, CallbackQuery)
            else event
        )

        await msg.answer(
            "Оценка должна быть от 1.0 до 10.0."
        )
        return

    score = round(score, 1)

    user_id = event.from_user.id

    target_id = await db.get_current_target(
        user_id
    )

    if not target_id:
        return

    await db.upsert_rating(
        user_id,
        target_id,
        score,
    )

    await state.update_data(
        target_id=target_id,
        score=score,
    )

    msg = (
        event.message
        if isinstance(event, CallbackQuery)
        else event
    )

    await msg.answer(
        f"⭐ Твоя оценка: {score:.1f}/10\n\n"
        "Хочешь оставить совет?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Оставить совет",
                        callback_data="advice:yes",
                    ),
                    InlineKeyboardButton(
                        text="➡️ Пропустить",
                        callback_data="advice:no",
                    ),
                ]
            ]
        ),
    )

    await state.set_state(
        RatingFSM.advice
    )

    try:
        await event.answer()
    except Exception:
        pass

    await bot.send_message(
        target_id,
        f"⭐ Тебя оценили: {score:.1f}/10",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👤 Посмотреть оценившего",
                        callback_data=f"rater:{user_id}",
                    )
                ]
            ]
        ),
    )


# =========================
# ADVICE
# =========================

@dp.callback_query(
    RatingFSM.advice,
    F.data == "advice:no",
)
async def advice_no(
    call: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await call.message.answer(
        "Готово.",
        reply_markup=main_keyboard(),
    )

    await call.answer()


@dp.callback_query(
    RatingFSM.advice,
    F.data == "advice:yes",
)
async def advice_yes(call: CallbackQuery):
    await call.message.answer(
        "Напиши совет:"
    )

    await call.answer()


@dp.message(RatingFSM.advice)
async def advice_text(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    target_id = data.get("target_id")
    score = data.get("score")

    if target_id:
        await db.add_advice(
            message.from_user.id,
            target_id,
            score,
            message.text.strip(),
        )

        await bot.send_message(
            target_id,
            "💬 Тебе оставили совет:\n\n"
            f"{message.text.strip()}",
        )

    await state.clear()

    await message.answer(
        "Совет отправлен.",
        reply_markup=main_keyboard(),
    )


# =========================
# RATER PROFILE
# =========================

@dp.callback_query(F.data.startswith("rater:"))
async def show_rater(call: CallbackQuery):
    user_id = int(
        call.data.split(":")[1]
    )

    await send_profile(
        call.message.chat.id,
        user_id,
    )

    await call.answer()


# =========================
# REPORTS
# =========================

@dp.callback_query(F.data == "report_current")
async def report_current(
    call: CallbackQuery,
    state: FSMContext,
):
    target = await db.get_current_target(
        call.from_user.id
    )

    if not target:
        await call.answer(
            "Анкета не выбрана.",
            show_alert=True,
        )
        return

    await state.update_data(
        target_id=target
    )

    await call.message.answer(
        "Причина жалобы:\n\n"
        "1 — Запрещённый контент\n"
        "2 — Чужое фото\n"
        "3 — Фейковый профиль\n"
        "4 — Несоответствие возрасту\n"
        "5 — Оскорбления\n"
        "6 — Другое"
    )

    await state.set_state(
        ReportFSM.reason
    )

    await call.answer()


@dp.message(ReportFSM.reason)
async def report_reason(
    message: Message,
    state: FSMContext,
):
    reasons = {
        "1": "Запрещённый контент",
        "2": "Чужое фото",
        "3": "Фейковый профиль",
        "4": "Несоответствие возрасту",
        "5": "Оскорбления",
        "6": "Другое",
    }

    reason = reasons.get(
        message.text.strip(),
        message.text.strip(),
    )

    await state.update_data(
        reason=reason
    )

    await message.answer(
        "Опиши проблему или отправь «-», "
        "чтобы пропустить:"
    )

    await state.set_state(
        ReportFSM.comment
    )


@dp.message(ReportFSM.comment)
async def report_comment(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    comment = message.text.strip()

    if comment == "-":
        comment = ""

    report_id = await db.add_report(
        message.from_user.id,
        data["target_id"],
        data["reason"],
        comment,
    )

    await state.clear()

    await message.answer(
        "🚩 Жалоба отправлена администрации.",
        reply_markup=main_keyboard(),
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🚨 Новая жалоба #{report_id}\n\n"
                f"Анкета: {data['target_id']}\n"
                f"Причина: {data['reason']}\n"
                f"Комментарий: {comment or '-'}",
            )
        except Exception:
            pass


# =========================
# MY PROFILE
# =========================

@dp.message(F.text == "👤 Моя анкета")
async def my_profile(message: Message):
    profile = await db.get_public_profile(
        message.from_user.id
    )

    if not profile:
        await message.answer(
            "Анкета ещё не создана."
        )
        return

    await send_profile(
        message.chat.id,
        message.from_user.id,
    )


# =========================
# STATS
# =========================

@dp.message(F.text == "📊 Моя статистика")
async def statistics(message: Message):
    stats = await db.stats(
        message.from_user.id
    )

    await message.answer(
        "📊 Твоя статистика\n\n"
        f"⭐ Средняя оценка: "
        f"{float(stats['average']):.1f}/10\n"
        f"📥 Получено оценок: "
        f"{stats['received']}\n"
        f"📤 Оценено пользователей: "
        f"{stats['given']}\n"
        f"💬 Оставлено советов: "
        f"{stats['advice']}"
    )


# =========================
# DELETE
# =========================

@dp.message(F.text == "🗑 Удалить анкету")
async def delete_profile(message: Message):
    await db.delete_profile(
        message.from_user.id
    )

    await message.answer(
        "🗑 Анкета удалена.",
        reply_markup=create_profile_keyboard(),
    )


# =========================
# EDIT PROFILE
# =========================

@dp.message(F.text == "✏️ Изменить анкету")
async def edit_profile(
    message: Message,
    state: FSMContext,
):
    await message.answer(
        "Отправьте новое фото."
    )

    await state.set_state(
        ProfileFSM.photo
    )


# =========================
# ADMIN
# =========================

@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        "🛠 Админ-панель",
        reply_markup=admin_keyboard(),
    )


@dp.callback_query(F.data == "admin:reports")
async def admin_reports(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    reports = await db.open_reports()

    if not reports:
        await call.answer(
            "Жалоб нет.",
            show_alert=True,
        )
        return

    for report in reports[:10]:
        await call.message.answer(
            f"🚨 Жалоба #{report['id']}\n\n"
            f"Анкета: {report['profile_user_id']}\n"
            f"Причина: {report['reason']}\n"
            f"Комментарий: "
            f"{report.get('comment') or '-'}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🗑 Удалить анкету",
                            callback_data=(
                                f"admin:delete:"
                                f"{report['profile_user_id']}"
                            ),
                        ),
                        InlineKeyboardButton(
                            text="✅ Закрыть",
                            callback_data=(
                                f"admin:close:"
                                f"{report['id']}"
                            ),
                        ),
                    ]
                ]
            ),
        )

    await call.answer()


@dp.callback_query(
    F.data.startswith("admin:delete:")
)
async def admin_delete(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    user_id = int(
        call.data.split(":")[2]
    )

    await db.delete_profile(user_id)

    await call.message.answer(
        f"🗑 Анкета {user_id} удалена."
    )

    await call.answer()


@dp.callback_query(
    F.data.startswith("admin:close:")
)
async def admin_close(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    report_id = int(
        call.data.split(":")[2]
    )

    await db.close_report(
        report_id,
        call.from_user.id,
    )

    await call.answer(
        "Жалоба закрыта."
    )


# =========================
# MODERATION
# =========================

@dp.callback_query(
    F.data == "admin:moderation"
)
async def moderation(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    profiles = await db.pending_profiles()

    if not profiles:
        await call.answer(
            "Очередь пуста.",
            show_alert=True,
        )
        return

    for profile in profiles[:10]:
        await call.message.answer_photo(
            profile["photo_id"],
            caption=(
                "🛡 Модерация\n\n"
                f"Пользователь: "
                f"{profile['user_id']}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Одобрить",
                            callback_data=(
                                f"approve:"
                                f"{profile['user_id']}"
                            ),
                        ),
                        InlineKeyboardButton(
                            text="🗑 Удалить",
                            callback_data=(
                                f"reject:"
                                f"{profile['user_id']}"
                            ),
                        ),
                    ]
                ]
            ),
        )

    await call.answer()


@dp.callback_query(
    F.data.startswith("approve:")
)
async def approve(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    user_id = int(
        call.data.split(":")[1]
    )

    await db.set_profile_status(
        user_id,
        "active",
    )

    await bot.send_message(
        user_id,
        "✅ Твоя анкета одобрена и теперь "
        "доступна для оценивания.",
    )

    await call.answer("Одобрено.")


@dp.callback_query(
    F.data.startswith("reject:")
)
async def reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    user_id = int(
        call.data.split(":")[1]
    )

    await db.delete_profile(
        user_id
    )

    await bot.send_message(
        user_id,
        "🗑 Твоя анкета удалена модерацией.",
    )

    await call.answer("Удалено.")


# =========================
# BROADCAST
# =========================

@dp.callback_query(
    F.data == "admin:broadcast"
)
async def broadcast_start(
    call: CallbackQuery,
    state: FSMContext,
):
    if call.from_user.id not in ADMIN_IDS:
        return

    await call.message.answer(
        "Отправь сообщение для рассылки.\n"
        "Можно отправить текст, фото или другое сообщение."
    )

    await state.set_state(
        BroadcastFSM.message
    )

    await call.answer()


@dp.message(BroadcastFSM.message)
async def broadcast_send(
    message: Message,
    state: FSMContext,
):
    if message.from_user.id not in ADMIN_IDS:
        return

    users = await db.all_user_ids()

    sent = 0
    failed = 0

    for user_id in users:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )

            sent += 1

        except Exception:
            failed += 1

        await asyncio.sleep(0.04)

    await db.add_broadcast(
        message.from_user.id,
        message.text or "[медиа]",
        sent,
        failed,
    )

    await state.clear()

    await message.answer(
        "📢 Рассылка завершена.\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}",
        reply_markup=admin_keyboard(),
    )


# =========================
# BROADCAST HISTORY
# =========================

@dp.callback_query(
    F.data == "admin:history"
)
async def broadcast_history(
    call: CallbackQuery,
):
    if call.from_user.id not in ADMIN_IDS:
        return

    rows = await db.broadcast_history()

    if not rows:
        await call.answer(
            "История пуста.",
            show_alert=True,
        )
        return

    text = "📜 История рассылок\n\n"

    for row in rows[:20]:
        text += (
            f"#{row['id']}\n"
            f"Дата: {row['created_at']}\n"
            f"Отправлено: {row['sent_count']}\n"
            f"Ошибок: {row['failed_count']}\n"
            f"Сообщение: "
            f"{(row.get('message') or '')[:100]}\n\n"
        )

    await call.message.answer(text)

    await call.answer()


# =========================
# RUN
# =========================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
