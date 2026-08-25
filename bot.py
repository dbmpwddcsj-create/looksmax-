import asyncio
import logging
import re

from statistics import median

from aiohttp import web

from aiogram import Bot, Dispatcher, F

from aiogram.client.default import DefaultBotProperties

from aiogram.enums import ParseMode

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError
)

from aiogram.filters import (
    Command,
    CommandStart
)

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import (
    State,
    StatesGroup
)

from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update
)

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    DATABASE_URL,
    RENDER_EXTERNAL_URL,
    WEBHOOK_SECRET,
    PORT
)

from database import Database


logging.basicConfig(
    level=logging.INFO
)


bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher(
    storage=MemoryStorage()
)

db = Database(
    DATABASE_URL
)


mailing_task = None
mailing_stop = asyncio.Event()


# ============================================================
# ТАБЛИЦЫ
# ============================================================

GIRL_TABLE_TYPES = [
    ("sub 3", "sub3"),
    ("sub 5", "sub5"),
    ("ltb", "ltb"),
    ("mtb", "mtb"),
    ("htb", "htb"),
    ("stacy", "stacy"),
    ("true eve", "true_eve")
]

BOY_TABLE_TYPES = [
    ("sub 3", "sub3"),
    ("sub 5", "sub5"),
    ("ltn", "ltn"),
    ("mtn", "mtn"),
    ("htn", "htn"),
    ("chad", "chad"),
    ("true adam", "true_adam")
]


# ============================================================
# СОСТОЯНИЯ
# ============================================================

class ProfileStates(StatesGroup):

    name = State()
    age = State()
    gender = State()
    photo = State()
    facts = State()


class EditStates(StatesGroup):

    name = State()
    age = State()
    gender = State()
    photo = State()
    facts = State()


class RatingStates(StatesGroup):

    score = State()
    table_type = State()
    advice = State()


class MailingStates(StatesGroup):

    content = State()
    button_text = State()
    button_url = State()


# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def kb(rows):

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def main_kb():

    return kb([

        [
            InlineKeyboardButton(
                text="⭐ Оценить внешность",
                callback_data="rate_people"
            )
        ],

        [
            InlineKeyboardButton(
                text="👤 Создать анкету",
                callback_data="create_profile"
            )
        ],

        [
            InlineKeyboardButton(
                text="📋 Моя анкета",
                callback_data="my_profile"
            )
        ],

        [
            InlineKeyboardButton(
                text="✏️ Изменить анкету",
                callback_data="edit_profile"
            )
        ]

    ])


def profile_kb(user_id):

    return kb([

        [
            InlineKeyboardButton(
                text="⭐ Оценить этого пользователя",
                callback_data=f"rate:{user_id}"
            )
        ],

        [
            InlineKeyboardButton(
                text="➡️ Следующая анкета",
                callback_data="rate_people"
            )
        ]

    ])


def edit_kb():

    return kb([

        [
            InlineKeyboardButton(
                text="✏️ Имя",
                callback_data="edit:name"
            ),

            InlineKeyboardButton(
                text="🎂 Возраст",
                callback_data="edit:age"
            )
        ],

        [
            InlineKeyboardButton(
                text="📸 Фото",
                callback_data="edit:photo"
            ),

            InlineKeyboardButton(
                text="⚧ Пол",
                callback_data="edit:gender"
            )
        ],

        [
            InlineKeyboardButton(
                text="📝 Факты",
                callback_data="edit:facts"
            )
        ],

        [
            InlineKeyboardButton(
                text="🗑 Удалить анкету",
                callback_data="delete_profile"
            )
        ],

        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="main"
            )
        ]

    ])


def table_kb(gender):

    types = (
        GIRL_TABLE_TYPES
        if gender == "female"
        else BOY_TABLE_TYPES
    )

    rows = []

    for name, value in types:

        rows.append([

            InlineKeyboardButton(
                text=name,
                callback_data=f"table:{value}"
            )

        ])

    rows.append([

        InlineKeyboardButton(
            text="⏭ Пропустить",
            callback_data="table:skip"
        )

    ])

    return kb(rows)


# ============================================================
# РЕЙТИНГ
# ============================================================

def format_average(scores):

    values = [
        float(x["score"])
        for x in scores
    ]

    if not values:
        return None

    if len(values) < 3:

        return (
            sum(values)
            / len(values)
        )

    med = median(values)

    deviations = [
        abs(x - med)
        for x in values
    ]

    candidates = []

    for i, x in enumerate(values):

        if deviations[i] >= 2.0:

            candidates.append(
                (
                    deviations[i],
                    i,
                    x
                )
            )

    if candidates:

        _, index, _ = max(
            candidates
        )

        filtered = (
            values[:index]
            +
            values[index + 1:]
        )

        if len(filtered) >= 2:

            return (
                sum(filtered)
                / len(filtered)
            )

    return (
        sum(values)
        / len(values)
    )


async def stats_text(user_id):

    scores = await db.get_scores(
        user_id
    )

    if not scores:

        return "⭐ Оценок пока нет"

    average = format_average(
        scores
    )

    return (
        f"⭐ Средняя оценка: "
        f"<b>{average:.1f}/10</b>\n"
        f"👥 Оценок: "
        f"<b>{len(scores)}</b>"
    )


def gender_name(gender):

    if gender == "male":
        return "Мужской"

    return "Женский"


async def profile_text(user):

    text = (

        f"👤 <b>{user['name']}</b>\n"

        f"🎂 Возраст: "
        f"<b>{user['age']}</b>\n"

        f"⚧ Пол: "
        f"<b>{gender_name(user['gender'])}</b>\n"

    )

    if user["username"]:

        text += (
            f"🔗 Username: "
            f"@{user['username']}\n"
        )

    if user["facts"]:

        text += (
            "\n📝 <b>О себе:</b>\n"
            f"{user['facts']}\n"
        )

    text += (
        "\n"
        +
        await stats_text(
            user["telegram_id"]
        )
    )

    return text


async def send_profile_message(
    message,
    user,
    own=False
):

    text = await profile_text(
        user
    )

    markup = (
        edit_kb()
        if own
        else profile_kb(
            user["telegram_id"]
        )
    )

    await message.answer_photo(

        user["photo_file_id"],

        caption=text,

        reply_markup=markup

    )


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(message: Message):

    await db.upsert_user(

        message.from_user.id,

        message.from_user.username

    )

    await message.answer(

        f"👋 Привет, "
        f"<b>{message.from_user.first_name}</b>!\n\n"

        "✨ Здесь ты можешь получить "
        "оценку своей внешности от других "
        "пользователей, оценивать других, "
        "получать советы и многое другое.\n\n"

        "💫 Всё бесплатно!\n\n"

        "<b>Что хочешь сделать?</b>",

        reply_markup=main_kb()

    )


# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================

@dp.callback_query(F.data == "main")
async def main_menu(
    call: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await call.answer()

    await call.message.answer(

        "🏠 <b>Главное меню</b>",

        reply_markup=main_kb()

    )


# ============================================================
# СОЗДАНИЕ АНКЕТЫ
# ============================================================

@dp.callback_query(F.data == "create_profile")
async def create_profile(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    await state.set_state(
        ProfileStates.name
    )

    await call.message.answer(

        "👤 <b>Создание анкеты</b>\n\n"

        "Напиши своё имя:"

    )


@dp.message(ProfileStates.name)
async def profile_name(
    message: Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not 2 <= len(value) <= 40:

        await message.answer(
            "❌ Имя должно быть "
            "от 2 до 40 символов."
        )

        return

    await state.update_data(
        name=value
    )

    await state.set_state(
        ProfileStates.age
    )

    await message.answer(
        "🎂 Напиши возраст.\n\n"
        "<b>Минимальный возраст — 13 лет.</b>"
    )


@dp.message(ProfileStates.age)
async def profile_age(
    message: Message,
    state: FSMContext
):

    try:

        age = int(
            (message.text or "").strip()
        )

    except ValueError:

        await message.answer(
            "❌ Введи возраст числом."
        )

        return

    if not 13 <= age <= 100:

        await message.answer(
            "❌ Использование своей "
            "анкеты доступно с 13 лет."
        )

        return

    await state.update_data(
        age=age
    )

    await state.set_state(
        ProfileStates.gender
    )

    await message.answer(

        "⚧ Выбери пол:",

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="👨 Мужской",
                    callback_data="gender:male"
                ),

                InlineKeyboardButton(
                    text="👩 Женский",
                    callback_data="gender:female"
                )

            ]

        ])

    )


@dp.callback_query(
    ProfileStates.gender,
    F.data.startswith("gender:")
)
async def profile_gender(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    gender = (
        call.data.split(":")[1]
    )

    await state.update_data(
        gender=gender
    )

    await state.set_state(
        ProfileStates.photo
    )

    await call.message.answer(
        "📸 Отправь фотографию "
        "для анкеты."
    )


@dp.message(ProfileStates.photo)
async def profile_photo(
    message: Message,
    state: FSMContext
):

    if not message.photo:

        await message.answer(
            "❌ Отправь именно фотографию."
        )

        return

    await state.update_data(

        photo_file_id=
        message.photo[-1].file_id

    )

    await state.set_state(
        ProfileStates.facts
    )

    await message.answer(

        "📝 Напиши несколько "
        "фактов о себе.\n\n"

        "Это необязательно.",

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="facts:skip"
                )

            ]

        ])

    )


@dp.callback_query(
    ProfileStates.facts,
    F.data == "facts:skip"
)
async def profile_skip_facts(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    await finish_profile(
        call.message,
        call.from_user.id,
        state,
        ""
    )


@dp.message(ProfileStates.facts)
async def profile_facts(
    message: Message,
    state: FSMContext
):

    facts = (
        message.text or ""
    ).strip()

    if len(facts) > 1000:

        await message.answer(
            "❌ Максимум 1000 символов."
        )

        return

    await finish_profile(
        message,
        message.from_user.id,
        state,
        facts
    )


async def finish_profile(
    message,
    user_id,
    state,
    facts
):

    data = await state.get_data()

    await db.save_profile(

        user_id,

        data["name"],

        data["age"],

        data["gender"],

        data["photo_file_id"],

        facts

    )

    await state.clear()

    await message.answer(

        "🎉 <b>Анкета создана!</b>\n\n"

        "Теперь её смогут видеть "
        "и оценивать другие пользователи.",

        reply_markup=main_kb()

    )


# ============================================================
# МОЯ АНКЕТА
# ============================================================

@dp.callback_query(F.data == "my_profile")
async def my_profile(
    call: CallbackQuery
):

    await call.answer()

    user = await db.get_profile(
        call.from_user.id
    )

    if not user:

        await call.message.answer(

            "❌ Анкета ещё не создана.",

            reply_markup=main_kb()

        )

        return

    await send_profile_message(
        call.message,
        user,
        own=True
    )


# ============================================================
# РЕДАКТИРОВАНИЕ
# ============================================================

@dp.callback_query(F.data == "edit_profile")
async def edit_profile(
    call: CallbackQuery
):

    await call.answer()

    user = await db.get_profile(
        call.from_user.id
    )

    if not user:

        await call.message.answer(
            "❌ Сначала создай анкету."
        )

        return

    await call.message.answer(

        "✏️ <b>Что изменить?</b>",

        reply_markup=edit_kb()

    )


@dp.callback_query(F.data.startswith("edit:"))
async def edit_field(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    field = (
        call.data.split(":")[1]
    )

    mapping = {

        "name": (
            EditStates.name,
            "👤 Напиши новое имя:"
        ),

        "age": (
            EditStates.age,
            "🎂 Напиши новый возраст (13+):"
        ),

        "photo": (
            EditStates.photo,
            "📸 Отправь новое фото:"
        ),

        "facts": (
            EditStates.facts,
            "📝 Напиши новые факты:"
        )

    }

    if field == "gender":

        await state.set_state(
            EditStates.gender
        )

        await call.message.answer(

            "⚧ Выбери новый пол:",

            reply_markup=kb([

                [

                    InlineKeyboardButton(
                        text="👨 Мужской",
                        callback_data="editgender:male"
                    ),

                    InlineKeyboardButton(
                        text="👩 Женский",
                        callback_data="editgender:female"
                    )

                ]

            ])

        )

        return

    if field not in mapping:
        return

    state_value, prompt = mapping[field]

    await state.set_state(
        state_value
    )

    await call.message.answer(
        prompt
    )


@dp.callback_query(
    EditStates.gender,
    F.data.startswith("editgender:")
)
async def edit_gender(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    await db.update_field(

        call.from_user.id,

        "gender",

        call.data.split(":")[1]

    )

    await state.clear()

    await call.message.answer(
        "✅ Пол изменён.",
        reply_markup=main_kb()
    )


@dp.message(EditStates.name)
async def edit_name(
    message: Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not 2 <= len(value) <= 40:

        await message.answer(
            "❌ Имя должно быть "
            "от 2 до 40 символов."
        )

        return

    await db.update_field(
        message.from_user.id,
        "name",
        value
    )

    await state.clear()

    await message.answer(
        "✅ Имя изменено.",
        reply_markup=main_kb()
    )


@dp.message(EditStates.age)
async def edit_age(
    message: Message,
    state: FSMContext
):

    try:

        age = int(
            (message.text or "").strip()
        )

    except ValueError:

        await message.answer(
            "❌ Введи возраст числом."
        )

        return

    if not 13 <= age <= 100:

        await message.answer(
            "❌ Возраст должен быть "
            "от 13 до 100."
        )

        return

    await db.update_field(
        message.from_user.id,
        "age",
        age
    )

    await state.clear()

    await message.answer(
        "✅ Возраст изменён.",
        reply_markup=main_kb()
    )


@dp.message(EditStates.photo)
async def edit_photo(
    message: Message,
    state: FSMContext
):

    if not message.photo:

        await message.answer(
            "❌ Отправь фотографию."
        )

        return

    await db.update_field(

        message.from_user.id,

        "photo_file_id",

        message.photo[-1].file_id

    )

    await state.clear()

    await message.answer(
        "✅ Фото изменено.",
        reply_markup=main_kb()
    )


@dp.message(EditStates.facts)
async def edit_facts(
    message: Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if len(value) > 1000:

        await message.answer(
            "❌ Максимум 1000 символов."
        )

        return

    await db.update_field(

        message.from_user.id,

        "facts",

        value

    )

    await state.clear()

    await message.answer(
        "✅ Факты изменены.",
        reply_markup=main_kb()
    )


# ============================================================
# УДАЛЕНИЕ АНКЕТЫ
# ============================================================

@dp.callback_query(F.data == "delete_profile")
async def delete_profile_confirm(
    call: CallbackQuery
):

    await call.answer()

    user = await db.get_profile(
        call.from_user.id
    )

    if not user:

        await call.message.answer(
            "❌ У тебя нет анкеты.",
            reply_markup=main_kb()
        )

        return

    await call.message.answer(

        "⚠️ <b>Удаление анкеты</b>\n\n"

        "Ты действительно хочешь удалить "
        "свою анкету?\n\n"

        "Будут удалены:\n"
        "• имя\n"
        "• возраст\n"
        "• пол\n"
        "• фотография\n"
        "• факты\n"
        "• твои оценки других пользователей\n"
        "• оценки твоей анкеты\n\n"

        "<b>Это действие нельзя отменить.</b>",

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data="delete_profile:yes"
                )

            ],

            [

                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="delete_profile:no"
                )

            ]

        ])

    )


@dp.callback_query(
    F.data == "delete_profile:no"
)
async def delete_profile_no(
    call: CallbackQuery
):

    await call.answer()

    await call.message.answer(
        "❌ Удаление отменено.",
        reply_markup=main_kb()
    )


@dp.callback_query(
    F.data == "delete_profile:yes"
)
async def delete_profile_yes(
    call: CallbackQuery
):

    await call.answer()

    await db.delete_profile(
        call.from_user.id
    )

    await call.message.answer(

        "🗑 <b>Анкета удалена.</b>\n\n"

        "Ты можешь создать новую анкету "
        "в любое время.",

        reply_markup=main_kb()

    )


# ============================================================
# ПОКАЗ АНКЕТЫ
# ============================================================

async def show_rating_profile(
    message,
    user,
    state
):

    await state.clear()

    rated_id = user["telegram_id"]

    await state.update_data(
        rated_user_id=rated_id
    )

    existing_rating = await db.get_rating(
        message.chat.id,
        rated_id
    )

    await message.answer_photo(

        user["photo_file_id"],

        caption=await profile_text(user)

    )

    if existing_rating:

        await state.update_data(
            existing_rating_id=existing_rating["id"]
        )

        await message.answer(

            "⚠️ <b>Ты уже оценивал этого пользователя.</b>\n\n"

            f"Твоя текущая оценка: "
            f"<b>{float(existing_rating['score']):.1f}/10</b>\n\n"

            "Хочешь изменить свою оценку?",

            reply_markup=kb([

                [

                    InlineKeyboardButton(
                        text="✏️ Изменить оценку",
                        callback_data="rating:change"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="➡️ Следующая анкета",
                        callback_data="rate_people"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="rating:cancel"
                    )

                ]

            ])

        )

        return

    await message.answer(

        "⭐ <b>Оцени внешность</b>\n\n"

        "Напиши число от "
        "<b>1 до 10</b>.\n\n"

        "Можно использовать "
        "одну цифру после точки "
        "или запятой:\n\n"

        "<code>8.5</code>\n"
        "<code>8,5</code>",

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="rate_people"
                )

            ]

        ])

    )

    await state.set_state(
        RatingStates.score
    )


# ============================================================
# ПОКАЗ СЛУЧАЙНОЙ АНКЕТЫ
# ============================================================

@dp.callback_query(F.data == "rate_people")
async def rate_people(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    await state.clear()

    user = await db.random_profile(
        call.from_user.id
    )

    if not user:

        await call.message.answer(

            "😔 Сейчас нет доступных "
            "анкет для оценки.",

            reply_markup=main_kb()

        )

        return

    await show_rating_profile(

        call.message,

        user,

        state

    )


# ============================================================
# ОЦЕНКА КОНКРЕТНОГО ПОЛЬЗОВАТЕЛЯ
# ============================================================

@dp.callback_query(F.data.startswith("rate:"))
async def rate_specific(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    target = int(
        call.data.split(":")[1]
    )

    if target == call.from_user.id:

        await call.message.answer(
            "❌ Нельзя оценивать себя."
        )

        return

    user = await db.get_profile(
        target
    )

    if not user:

        await call.message.answer(
            "❌ Анкета недоступна."
        )

        return

    await show_rating_profile(
        call.message,
        user,
        state
    )


# ============================================================
# ИЗМЕНЕНИЕ ОЦЕНКИ
# ============================================================

@dp.callback_query(F.data == "rating:change")
async def rating_change(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    data = await state.get_data()

    if not data.get("existing_rating_id"):

        await call.message.answer(
            "❌ Не удалось найти старую оценку."
        )

        await state.clear()

        return

    await state.set_state(
        RatingStates.score
    )

    await call.message.answer(

        "✏️ <b>Изменение оценки</b>\n\n"

        "Напиши новую оценку "
        "от <b>1 до 10</b>.\n\n"

        "Например: <code>9.2</code>"

    )


@dp.callback_query(F.data == "rating:cancel")
async def rating_cancel(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    await state.clear()

    await call.message.answer(

        "❌ Изменение оценки отменено.",

        reply_markup=main_kb()

    )


# ============================================================
# ПОЛУЧЕНИЕ ОЦЕНКИ
# ============================================================

@dp.message(RatingStates.score)
async def receive_score(
    message: Message,
    state: FSMContext
):

    raw = (
        message.text or ""
    ).strip().replace(",", ".")

    if not re.fullmatch(
        r"(?:[1-9](?:\.\d)?|10(?:\.0)?)",
        raw
    ):

        await message.answer(

            "❌ Оценка должна быть "
            "от 1 до 10.\n\n"

            "Например: "
            "<code>7.5</code>"

        )

        return

    score = float(raw)

    data = await state.get_data()

    rated_id = data.get(
        "rated_user_id"
    )

    if not rated_id:

        await state.clear()

        await message.answer(
            "❌ Произошла ошибка. "
            "Начни оценивание заново.",
            reply_markup=main_kb()
        )

        return

    if rated_id == message.from_user.id:

        await state.clear()

        await message.answer(
            "❌ Нельзя оценивать себя.",
            reply_markup=main_kb()
        )

        return

    existing_rating_id = data.get(
        "existing_rating_id"
    )

    if existing_rating_id:

        rating = await db.update_rating(

            existing_rating_id,

            score

        )

        if not rating:

            await state.clear()

            await message.answer(
                "❌ Не удалось изменить оценку.",
                reply_markup=main_kb()
            )

            return

        changed = True

    else:

        # На всякий случай проверяем базу.
        # Это защищает от повторной оценки,
        # если состояние бота сбилось.

        existing = await db.get_rating(

            message.from_user.id,

            rated_id

        )

        if existing:

            await state.update_data(

                existing_rating_id=
                existing["id"]

            )

            await message.answer(

                "⚠️ <b>Ты уже оценивал этого пользователя.</b>\n\n"

                f"Твоя текущая оценка: "
                f"<b>{float(existing['score']):.1f}/10</b>\n\n"

                "Хочешь изменить её?",

                reply_markup=kb([

                    [

                        InlineKeyboardButton(
                            text="✏️ Изменить оценку",
                            callback_data="rating:change"
                        )

                    ],

                    [

                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="rating:cancel"
                        )

                    ]

                ])

            )

            return

        rating = await db.add_rating(

            message.from_user.id,

            rated_id,

            score

        )

        changed = False

    await state.update_data(

        rating_id=rating["id"],

        score=score,

        existing_rating_id=None

    )

    user = await db.get_profile(
        rated_id
    )

    await state.set_state(
        RatingStates.table_type
    )

    if changed:

        title = "✏️ <b>Оценка изменена!</b>"

    else:

        title = "✅ <b>Оценка сохранена!</b>"

    await message.answer(

        f"{title}\n\n"

        f"⭐ Новая оценка: "
        f"<b>{score:.1f}/10</b>\n\n"

        "📊 <b>Дополнительная "
        "оценка по таблице</b>\n\n"

        "Это необязательно.\n"
        "Выбери подходящий тип "
        "или пропусти.",

        reply_markup=table_kb(
            user["gender"]
        )

    )


# ============================================================
# ТАБЛИЦА
# ============================================================

@dp.callback_query(
    RatingStates.table_type,
    F.data.startswith("table:")
)
async def table_type(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    value = (
        call.data.split(":", 1)[1]
    )

    data = await state.get_data()

    if value != "skip":

        await db.add_table_type(

            data["rating_id"],

            value

        )

        await state.update_data(
            table_type=value
        )

    else:

        await state.update_data(
            table_type=None
        )

    await state.set_state(
        RatingStates.advice
    )

    await call.message.answer(

        "💬 <b>Хочешь оставить совет?</b>\n\n"

        "Это необязательно.",

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="💬 Написать совет",
                    callback_data="advice:write"
                )

            ],

            [

                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="advice:skip"
                )

            ]

        ])

    )


# ============================================================
# СОВЕТ
# ============================================================

@dp.callback_query(
    RatingStates.advice,
    F.data == "advice:write"
)
async def advice_write(
    call: CallbackQuery
):

    await call.answer()

    await call.message.answer(

        "💬 Напиши свой совет.\n\n"

        "Пожалуйста, оставайся "
        "корректным и уважительным."

    )


@dp.callback_query(
    RatingStates.advice,
    F.data == "advice:skip"
)
async def advice_skip(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    data = await state.get_data()

    await state.clear()

    await notify_rating(

        data["rated_user_id"],

        call.from_user.id,

        data["score"],

        data.get("table_type"),

        None

    )

    await call.message.answer(

        "✅ Оценка отправлена!",

        reply_markup=main_kb()

    )


@dp.message(RatingStates.advice)
async def advice_receive(
    message: Message,
    state: FSMContext
):

    advice = (
        message.text or ""
    ).strip()

    if len(advice) > 1000:

        await message.answer(
            "❌ Максимум 1000 символов."
        )

        return

    data = await state.get_data()

    await db.add_advice(

        data["rating_id"],

        advice

    )

    await state.clear()

    await notify_rating(

        data["rated_user_id"],

        message.from_user.id,

        data["score"],

        data.get("table_type"),

        advice

    )

    await message.answer(

        "✅ Оценка и совет отправлены!",

        reply_markup=main_kb()

    )


# ============================================================
# УВЕДОМЛЕНИЕ
# ============================================================

async def notify_rating(
    rated_id,
    rater_id,
    score,
    table_type,
    advice
):

    text = (

        "🔔 <b>Твою анкету оценили!</b>\n\n"

        f"⭐ Оценка: "
        f"<b>{score:.1f}/10</b>\n"

    )

    if table_type:

        text += (

            f"📊 Табличный тип: "
            f"<b>{table_type}</b>\n"

        )

    if advice:

        text += (

            "\n💬 <b>Совет:</b>\n"

            f"{advice}\n"

        )

    text += (

        "\n👤 Ты можешь посмотреть "
        "полную анкету оценившего."

    )

    try:

        await bot.send_message(

            rated_id,

            text,

            reply_markup=kb([

                [

                    InlineKeyboardButton(

                        text="👤 Посмотреть профиль",

                        callback_data=
                        f"view_rater:{rater_id}"

                    )

                ]

            ])

        )

    except Exception:

        logging.exception(
            "Failed to notify rated user"
        )


# ============================================================
# ПРОФИЛЬ ОЦЕНИВШЕГО
# ============================================================

@dp.callback_query(
    F.data.startswith("view_rater:")
)
async def view_rater(
    call: CallbackQuery
):

    await call.answer()

    rater = int(
        call.data.split(":")[1]
    )

    user = await db.get_profile(
        rater
    )

    if not user:

        await call.message.answer(

            "❌ Анкета больше "
            "недоступна."

        )

        return

    await send_profile_message(

        call.message,

        user,

        own=False

    )


# ============================================================
# АДМИНКА
# ============================================================

@dp.message(Command("admin"))
async def admin(
    message: Message
):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(

        "🛠 <b>Админ-панель</b>\n\n"

        "/mailing — создать рекламную рассылку\n"

        "/stopmailing — остановить текущую рассылку\n"

        "/mailings — история рассылок"

    )


# ============================================================
# СОЗДАНИЕ РАССЫЛКИ
# ============================================================

@dp.message(Command("mailing"))
async def mailing(
    message: Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    await state.set_state(
        MailingStates.content
    )

    await message.answer(

        "📢 <b>Создание рекламной рассылки</b>\n\n"

        "Отправь рекламный материал:\n\n"

        "📝 текст\n"
        "🖼 фото\n"
        "🎥 видео"

    )


@dp.message(MailingStates.content)
async def mailing_content(
    message: Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    if message.text:

        data = {

            "type": "text",

            "text": message.text,

            "file_id": None,

            "caption": None

        }

    elif message.photo:

        data = {

            "type": "photo",

            "text": None,

            "file_id":
            message.photo[-1].file_id,

            "caption":
            message.caption or ""

        }

    elif message.video:

        data = {

            "type": "video",

            "text": None,

            "file_id":
            message.video.file_id,

            "caption":
            message.caption or ""

        }

    else:

        await message.answer(

            "❌ Поддерживаются "
            "текст, фото и видео."

        )

        return

    await state.update_data(
        **data
    )

    await message.answer(

        "🔘 Добавить рекламную кнопку?",

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="🔘 Добавить кнопку",
                    callback_data="mailing:add_button"
                )

            ],

            [

                InlineKeyboardButton(
                    text="➡️ Без кнопки",
                    callback_data="mailing:no_button"
                )

            ],

            [

                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="mailing:cancel"
                )

            ]

        ])

    )


@dp.callback_query(
    F.data == "mailing:add_button"
)
async def mailing_add_button(
    call: CallbackQuery,
    state: FSMContext
):

    if call.from_user.id != ADMIN_ID:
        return

    await call.answer()

    await state.set_state(
        MailingStates.button_text
    )

    await call.message.answer(

        "🔘 Напиши текст кнопки.\n\n"

        "Например:\n"
        "<code>Перейти</code>"

    )


@dp.message(MailingStates.button_text)
async def mailing_button_text(
    message: Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    value = (
        message.text or ""
    ).strip()

    if not 1 <= len(value) <= 64:

        await message.answer(

            "❌ Текст кнопки должен "
            "быть от 1 до 64 символов."

        )

        return

    await state.update_data(
        button_text=value
    )

    await state.set_state(
        MailingStates.button_url
    )

    await message.answer(

        "🔗 Теперь отправь ссылку.\n\n"

        "Она должна начинаться с:\n"
        "<code>https://</code>"

    )


@dp.message(MailingStates.button_url)
async def mailing_button_url(
    message: Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    url = (
        message.text or ""
    ).strip()

    if not re.match(
        r"^https://\S+$",
        url
    ):

        await message.answer(

            "❌ Нужна корректная "
            "HTTPS-ссылка."

        )

        return

    await state.update_data(
        button_url=url
    )

    await confirm_mailing(
        message,
        state
    )


@dp.callback_query(
    F.data == "mailing:no_button"
)
async def mailing_no_button(
    call: CallbackQuery,
    state: FSMContext
):

    if call.from_user.id != ADMIN_ID:
        return

    await call.answer()

    await state.update_data(

        button_text=None,

        button_url=None

    )

    await confirm_mailing(
        call.message,
        state
    )


async def confirm_mailing(
    message,
    state
):

    data = await state.get_data()

    preview = (

        data.get("text")
        or
        data.get("caption")
        or
        "[медиа]"

    )

    await message.answer(

        "📢 <b>Предпросмотр рекламы</b>\n\n"

        f"{preview}\n\n"

        "Отправить всем активным "
        "пользователям?",

        reply_markup=kb([

            [

                InlineKeyboardButton(

                    text="🚀 Запустить",

                    callback_data="mailing:start"

                )

            ],

            [

                InlineKeyboardButton(

                    text="❌ Отмена",

                    callback_data="mailing:cancel"

                )

            ]

        ])

    )


@dp.callback_query(
    F.data == "mailing:cancel"
)
async def mailing_cancel(
    call: CallbackQuery,
    state: FSMContext
):

    if call.from_user.id != ADMIN_ID:
        return

    await call.answer()

    await state.clear()

    await call.message.answer(
        "❌ Рассылка отменена."
    )


# ============================================================
# ЗАПУСК РАССЫЛКИ
# ============================================================

@dp.callback_query(
    F.data == "mailing:start"
)
async def mailing_start(
    call: CallbackQuery,
    state: FSMContext
):

    global mailing_task

    if call.from_user.id != ADMIN_ID:
        return

    if (
        mailing_task
        and not mailing_task.done()
    ):

        await call.answer(

            "Уже идёт другая рассылка.",

            show_alert=True

        )

        return

    data = await state.get_data()

    await state.clear()

    mailing_stop.clear()

    users = await db.get_active_users()

    record = await db.create_mailing(

        ADMIN_ID,

        data["type"],

        data.get("text")
        or
        data.get("caption"),

        data.get("button_text"),

        data.get("button_url"),

        len(users)

    )

    mailing_task = asyncio.create_task(

        run_mailing(

            record["id"],

            users,

            data

        )

    )

    await call.answer()

    await call.message.answer(

        f"🚀 Рассылка "
        f"<b>#{record['id']}</b> запущена.\n\n"

        f"👥 Получателей: "
        f"<b>{len(users)}</b>"

    )


@dp.message(Command("stopmailing"))
async def stop_mailing(
    message: Message
):

    if message.from_user.id != ADMIN_ID:
        return

    if (
        not mailing_task
        or mailing_task.done()
    ):

        await message.answer(

            "ℹ️ Сейчас нет "
            "активной рассылки."

        )

        return

    mailing_stop.set()

    await message.answer(

        "🛑 Остановка текущей "
        "рассылки запрошена."

    )


def mailing_markup(data):

    if (
        data.get("button_text")
        and
        data.get("button_url")
    ):

        return kb([

            [

                InlineKeyboardButton(

                    text=data["button_text"],

                    url=data["button_url"]

                )

            ]

        ])

    return None


async def run_mailing(
    mailing_id,
    users,
    data
):

    delivered = 0
    blocked = 0
    failed = 0

    markup = mailing_markup(
        data
    )

    try:

        for row in users:

            if mailing_stop.is_set():

                await db.finish_mailing(

                    mailing_id,

                    "stopped",

                    delivered,

                    blocked,

                    failed

                )

                return

            user_id = row[
                "telegram_id"
            ]

            try:

                if data["type"] == "text":

                    await bot.send_message(

                        user_id,

                        data["text"],

                        reply_markup=markup

                    )

                elif data["type"] == "photo":

                    await bot.send_photo(

                        user_id,

                        data["file_id"],

                        caption=
                        data.get("caption")
                        or "",

                        reply_markup=markup

                    )

                else:

                    await bot.send_video(

                        user_id,

                        data["file_id"],

                        caption=
                        data.get("caption")
                        or "",

                        reply_markup=markup

                    )

                delivered += 1

            except TelegramForbiddenError:

                blocked += 1

                await db.deactivate_user(
                    user_id
                )

            except TelegramBadRequest as error:

                if (
                    "chat not found"
                    in str(error).lower()
                ):

                    blocked += 1

                    await db.deactivate_user(
                        user_id
                    )

                else:

                    failed += 1

            except Exception:

                failed += 1

                logging.exception(
                    "Mailing error"
                )

            await asyncio.sleep(
                0.05
            )

        await db.finish_mailing(

            mailing_id,

            "finished",

            delivered,

            blocked,

            failed

        )

        await bot.send_message(

            ADMIN_ID,

            "📊 <b>Рассылка завершена!</b>\n\n"

            f"👥 Всего: {len(users)}\n"

            f"✅ Доставлено: {delivered}\n"

            f"🚫 Недоступны: {blocked}\n"

            f"❌ Ошибки: {failed}"

        )

    except Exception:

        logging.exception(
            "Mailing crashed"
        )

        await db.finish_mailing(

            mailing_id,

            "failed",

            delivered,

            blocked,

            failed

        )


# ============================================================
# ИСТОРИЯ РАССЫЛОК
# ============================================================

@dp.message(Command("mailings"))
async def mailings(
    message: Message
):

    if message.from_user.id != ADMIN_ID:
        return

    rows = await db.mailing_history()

    if not rows:

        await message.answer(
            "История пока пустая."
        )

        return

    text = (
        "📊 <b>Последние рассылки</b>\n\n"
    )

    for row in rows:

        text += (

            f"#{row['id']} — "
            f"{row['status']}\n"

            f"👥 {row['total']} | "
            f"✅ {row['delivered']} | "
            f"🚫 {row['blocked']} | "
            f"❌ {row['failed']}\n\n"

        )

    await message.answer(
        text
    )


# ============================================================
# WEBHOOK / RENDER
# ============================================================

async def health(request):

    return web.Response(
        text="OK"
    )


async def webhook(request):

    if WEBHOOK_SECRET:

        incoming_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        )

        if incoming_secret != WEBHOOK_SECRET:

            return web.Response(
                status=403,
                text="Forbidden"
            )

    data = await request.json()

    update = Update.model_validate(
        data
    )

    await dp.feed_update(
        bot,
        update
    )

    return web.Response(
        text="OK"
    )


async def on_startup(app):

    await db.connect()

    webhook_url = (
        f"{RENDER_EXTERNAL_URL}"
        "/webhook"
    )

    await bot.set_webhook(

        url=webhook_url,

        secret_token=WEBHOOK_SECRET,

        drop_pending_updates=True

    )

    logging.info(
        "Webhook set: %s",
        webhook_url
    )


async def on_shutdown(app):

    await bot.delete_webhook()

    await db.close()

    await bot.session.close()


app = web.Application()

app.router.add_get(
    "/",
    health
)

app.router.add_post(
    "/webhook",
    webhook
)

app.on_startup.append(
    on_startup
)

app.on_shutdown.append(
    on_shutdown
)


if __name__ == "__main__":

    web.run_app(

        app,

        host="0.0.0.0",

        port=PORT

    )
