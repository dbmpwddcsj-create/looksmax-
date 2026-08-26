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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO
)


# ============================================================
# BOT
# ============================================================

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
# TABLE TYPES
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
# STATES
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
# KEYBOARD HELPER
# ============================================================

def kb(rows):

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# ============================================================
# MAIN KEYBOARD
# ============================================================

def main_kb(lang="ru"):

    if lang == "en":

        return kb([

            [
                InlineKeyboardButton(
                    text="⭐ Rate appearance",
                    callback_data="rate_people"
                )
            ],

            [
                InlineKeyboardButton(
                    text="👤 Create profile",
                    callback_data="create_profile"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📋 My profile",
                    callback_data="my_profile"
                )
            ],

            [
                InlineKeyboardButton(
                    text="✏️ Edit profile",
                    callback_data="edit_profile"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🌐 Language",
                    callback_data="language"
                )
            ]

        ])

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
        ],

        [
            InlineKeyboardButton(
                text="🌐 Язык",
                callback_data="language"
            )
        ]

    ])


# ============================================================
# PROFILE KEYBOARD
# ============================================================

def profile_kb(
    user_id,
    lang="ru"
):

    if lang == "en":

        return kb([

            [
                InlineKeyboardButton(
                    text="⭐ Rate this user",
                    callback_data=f"rate:{user_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🚩 Report",
                    callback_data=f"report:{user_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="➡️ Next profile",
                    callback_data="rate_people"
                )
            ]

        ])

    return kb([

        [
            InlineKeyboardButton(
                text="⭐ Оценить этого пользователя",
                callback_data=f"rate:{user_id}"
            )
        ],

        [
            InlineKeyboardButton(
                text="🚩 Пожаловаться",
                callback_data=f"report:{user_id}"
            )
        ],

        [
            InlineKeyboardButton(
                text="➡️ Следующая анкета",
                callback_data="rate_people"
            )
        ]

    ])


# ============================================================
# EDIT KEYBOARD
# ============================================================

def edit_kb(lang="ru"):

    if lang == "en":

        return kb([

            [

                InlineKeyboardButton(
                    text="✏️ Name",
                    callback_data="edit:name"
                ),

                InlineKeyboardButton(
                    text="🎂 Age",
                    callback_data="edit:age"
                )

            ],

            [

                InlineKeyboardButton(
                    text="📸 Photo",
                    callback_data="edit:photo"
                ),

                InlineKeyboardButton(
                    text="⚧ Gender",
                    callback_data="edit:gender"
                )

            ],

            [

                InlineKeyboardButton(
                    text="📝 Facts",
                    callback_data="edit:facts"
                )

            ],

            [

                InlineKeyboardButton(
                    text="🗑 Delete profile",
                    callback_data="delete_profile"
                )

            ],

            [

                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="main"
                )

            ]

        ])

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


# ============================================================
# TABLE KEYBOARD
# ============================================================

def table_kb(
    gender,
    lang="ru"
):

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
            text=(
                "⏭ Skip"
                if lang == "en"
                else "⏭ Пропустить"
            ),
            callback_data="table:skip"
        )

    ])

    return kb(rows)


# ============================================================
# LANGUAGE KEYBOARD
# ============================================================

def language_kb():

    return kb([

        [

            InlineKeyboardButton(
                text="🇷🇺 Русский",
                callback_data="lang:ru"
            ),

            InlineKeyboardButton(
                text="🇬🇧 English",
                callback_data="lang:en"
            )

        ]

    ])


# ============================================================
# AGREEMENT
# ============================================================

def agreement_kb(lang):

    if lang == "en":

        return kb([

            [

                InlineKeyboardButton(
                    text="✅ I agree",
                    callback_data="agreement:yes"
                )

            ],

            [

                InlineKeyboardButton(
                    text="❌ I don't agree",
                    callback_data="agreement:no"
                )

            ]

        ])

    return kb([

        [

            InlineKeyboardButton(
                text="✅ Согласен",
                callback_data="agreement:yes"
            )

        ],

        [

            InlineKeyboardButton(
                text="❌ Не согласен",
                callback_data="agreement:no"
            )

        ]

    ])


def agreement_text(lang):

    if lang == "en":

        return (
            "📜 <b>Before creating a profile</b>\n\n"

            "You must be at least 13 years old to use "
            "the bot.\n\n"

            "Your age is shown in your profile and "
            "can be seen by other users.\n\n"

            "Your photo must show your real face. "
            "Otherwise your profile may be removed.\n\n"

            "Active moderation is used in the bot.\n\n"

            "By pressing «I agree», you accept the "
            "rules and privacy policy."
        )

    return (
        "📜 <b>Перед созданием анкеты</b>\n\n"

        "Ботом можно пользоваться с 13 лет.\n\n"

        "Возраст указывается в анкете и виден другим.\n\n"

        "На фото — ваше настоящее лицо, иначе анкету удалят.\n\n"

        "В боте работает активная модерация.\n\n"

        "Нажимая «Согласен», вы принимаете правила "
        "и политику."
    )


# ============================================================
# DELETE KEYBOARD
# ============================================================

def delete_confirm_kb(lang):

    if lang == "en":

        return kb([

            [

                InlineKeyboardButton(
                    text="🗑 Yes, delete",
                    callback_data="delete:yes"
                ),

                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="delete:no"
                )

            ]

        ])

    return kb([

        [

            InlineKeyboardButton(
                text="🗑 Да, удалить",
                callback_data="delete:yes"
            ),

            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="delete:no"
            )

        ]

    ])


# ============================================================
# REPORT KEYBOARD
# ============================================================

def report_kb(user_id, lang):

    if lang == "en":

        return kb([

            [

                InlineKeyboardButton(
                    text="🚫 Fake photo",
                    callback_data=f"reportreason:{user_id}:fake"
                )

            ],

            [

                InlineKeyboardButton(
                    text="🔞 Inappropriate content",
                    callback_data=f"reportreason:{user_id}:inappropriate"
                )

            ],

            [

                InlineKeyboardButton(
                    text="👶 Age violation",
                    callback_data=f"reportreason:{user_id}:age"
                )

            ],

            [

                InlineKeyboardButton(
                    text="⚠️ Other",
                    callback_data=f"reportreason:{user_id}:other"
                )

            ]

        ])

    return kb([

        [

            InlineKeyboardButton(
                text="🚫 Фейковое фото",
                callback_data=f"reportreason:{user_id}:fake"
            )

        ],

        [

            InlineKeyboardButton(
                text="🔞 Неподходящий контент",
                callback_data=f"reportreason:{user_id}:inappropriate"
            )

        ],

        [

            InlineKeyboardButton(
                text="👶 Нарушение возраста",
                callback_data=f"reportreason:{user_id}:age"
            )

        ],

        [

            InlineKeyboardButton(
                text="⚠️ Другое",
                callback_data=f"reportreason:{user_id}:other"
            )

        ]

    ])


# ============================================================
# REPORT REASONS
# ============================================================

def report_reason_name(
    reason,
    lang="ru"
):

    if lang == "en":

        names = {

            "fake":
                "Fake / not real face",

            "inappropriate":
                "Inappropriate content",

            "age":
                "Age violation",

            "other":
                "Other"

        }

    else:

        names = {

            "fake":
                "Фейковое / ненастоящее фото",

            "inappropriate":
                "Неподходящий контент",

            "age":
                "Нарушение возраста",

            "other":
                "Другое"

        }

    return names.get(
        reason,
        reason
    )


# ============================================================
# AVERAGE
# ============================================================

def format_average(
    scores
):

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


async def stats_text(
    user_id,
    lang="ru"
):

    scores = await db.get_scores(
        user_id
    )

    if not scores:

        if lang == "en":
            return "⭐ No ratings yet"

        return "⭐ Оценок пока нет"

    average = format_average(
        scores
    )

    if lang == "en":

        return (
            f"⭐ Average rating: "
            f"<b>{average:.1f}/10</b>\n"

            f"👥 Ratings: "
            f"<b>{len(scores)}</b>"
        )

    return (
        f"⭐ Средняя оценка: "
        f"<b>{average:.1f}/10</b>\n"

        f"👥 Оценок: "
        f"<b>{len(scores)}</b>"
    )


def gender_name(
    gender,
    lang="ru"
):

    if gender == "male":

        return (
            "Male"
            if lang == "en"
            else "Мужской"
        )

    return (
        "Female"
        if lang == "en"
        else "Женский"
    )


async def profile_text(
    user
):

    lang = user.get(
        "language",
        "ru"
    )

    text = (

        f"👤 <b>{user['name']}</b>\n"

        f"🎂 "
        + (
            "Age"
            if lang == "en"
            else "Возраст"
        )
        + f": <b>{user['age']}</b>\n"

        f"⚧ "
        + (
            "Gender"
            if lang == "en"
            else "Пол"
        )
        + f": <b>{gender_name(user['gender'], lang)}</b>\n"

    )

    if user["username"]:

        text += (
            f"🔗 Username: "
            f"@{user['username']}\n"
        )

    if user["facts"]:

        text += (

            "\n📝 <b>"
            + (
                "About me"
                if lang == "en"
                else "О себе"
            )
            + ":</b>\n"

            f"{user['facts']}\n"
        )

    text += (
        "\n"
        +
        await stats_text(
            user["telegram_id"],
            lang
        )
    )

    return text


async def send_profile_message(
    message,
    user,
    own=False
):

    lang = user.get(
        "language",
        "ru"
    )

    text = await profile_text(
        user
    )

    markup = (

        edit_kb(lang)

        if own

        else profile_kb(
            user["telegram_id"],
            lang
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

@dp.message(
    CommandStart()
)
async def start(
    message: Message
):

    await db.upsert_user(

        message.from_user.id,

        message.from_user.username

    )

    user = await db.get_user(
        message.from_user.id
    )

    language = user["language"]

    # --------------------------------------------------------
    # FIRST START
    # --------------------------------------------------------

    if not user["language"]:

        await message.answer(
            "🌐 <b>Choose your language / "
            "Выберите язык:</b>",
            reply_markup=language_kb()
        )

        return

    # На случай старой БД.
    if language not in ("ru", "en"):

        await message.answer(
            "🌐 <b>Choose your language / "
            "Выберите язык:</b>",
            reply_markup=language_kb()
        )

        return

    if language == "en":

        await message.answer(

            f"👋 Hello, "
            f"<b>{message.from_user.first_name}</b>!\n\n"

            "✨ Here you can get ratings of your "
            "appearance from other users, rate "
            "other people and receive advice.\n\n"

            "💫 Everything is free!\n\n"

            "<b>What would you like to do?</b>",

            reply_markup=main_kb("en")

        )

    else:

        await message.answer(

            f"👋 Привет, "
            f"<b>{message.from_user.first_name}</b>!\n\n"

            "✨ Здесь ты можешь получить "
            "оценку своей внешности от других "
            "пользователей, оценивать других, "
            "получать советы и многое другое.\n\n"

            "💫 Всё бесплатно!\n\n"

            "<b>Что хочешь сделать?</b>",

            reply_markup=main_kb("ru")

        )


# ============================================================
# LANGUAGE
# ============================================================

@dp.callback_query(
    F.data == "language"
)
async def language_menu(
    call: CallbackQuery
):

    await call.answer()

    await call.message.answer(
        "🌐 Choose language / Выберите язык:",
        reply_markup=language_kb()
    )


@dp.callback_query(
    F.data.startswith("lang:")
)
async def choose_language(
    call: CallbackQuery
):

    language = call.data.split(":")[1]

    await db.set_language(
        call.from_user.id,
        language
    )

    await call.answer()

    if language == "en":

        await call.message.answer(
            "🇬🇧 Language changed to English.",
            reply_markup=main_kb("en")
        )

    else:

        await call.message.answer(
            "🇷🇺 Язык изменён на русский.",
            reply_markup=main_kb("ru")
        )


# ============================================================
# MAIN MENU
# ============================================================

@dp.callback_query(
    F.data == "main"
)
async def main_menu(
    call: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await call.answer()

    lang = await db.get_language(
        call.from_user.id
    )

    if lang == "en":

        text = "🏠 <b>Main menu</b>"

    else:

        text = "🏠 <b>Главное меню</b>"

    await call.message.answer(

        text,

        reply_markup=main_kb(lang)

    )


# ============================================================
# CREATE PROFILE
# ============================================================

@dp.callback_query(
    F.data == "create_profile"
)
async def create_profile(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    lang = await db.get_language(
        call.from_user.id
    )

    accepted = await db.has_agreement(
        call.from_user.id
    )

    if not accepted:

        await call.message.answer(

            agreement_text(lang),

            reply_markup=agreement_kb(lang)

        )

        return

    await state.set_state(
        ProfileStates.name
    )

    if lang == "en":

        text = (
            "👤 <b>Creating profile</b>\n\n"
            "Enter your name:"
        )

    else:

        text = (
            "👤 <b>Создание анкеты</b>\n\n"
            "Напиши своё имя:"
        )

    await call.message.answer(
        text
    )


# ============================================================
# AGREEMENT
# ============================================================

@dp.callback_query(
    F.data == "agreement:yes"
)
async def agreement_yes(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    await db.accept_agreement(
        call.from_user.id
    )

    lang = await db.get_language(
        call.from_user.id
    )

    await state.set_state(
        ProfileStates.name
    )

    if lang == "en":

        await call.message.answer(
            "👤 <b>Creating profile</b>\n\n"
            "Enter your name:"
        )

    else:

        await call.message.answer(
            "👤 <b>Создание анкеты</b>\n\n"
            "Напиши своё имя:"
        )


@dp.callback_query(
    F.data == "agreement:no"
)
async def agreement_no(
    call: CallbackQuery
):

    await call.answer()

    lang = await db.get_language(
        call.from_user.id
    )

    if lang == "en":

        text = (
            "❌ You need to accept the rules "
            "to create a profile."
        )

    else:

        text = (
            "❌ Чтобы создать анкету, "
            "необходимо принять правила."
        )

    await call.message.answer(
        text,
        reply_markup=main_kb(lang)
    )


# ============================================================
# PROFILE NAME
# ============================================================

@dp.message(
    ProfileStates.name
)
async def profile_name(
    message: Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    lang = await db.get_language(
        message.from_user.id
    )

    if not 2 <= len(value) <= 40:

        if lang == "en":

            await message.answer(
                "❌ Name must be between "
                "2 and 40 characters."
            )

        else:

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

    if lang == "en":

        await message.answer(
            "🎂 Enter your age.\n\n"
            "<b>Minimum age — 13.</b>"
        )

    else:

        await message.answer(
            "🎂 Напиши возраст.\n\n"
            "<b>Минимальный возраст — 13 лет.</b>"
        )


# ============================================================
# PROFILE AGE
# ============================================================

@dp.message(
    ProfileStates.age
)
async def profile_age(
    message: Message,
    state: FSMContext
):

    lang = await db.get_language(
        message.from_user.id
    )

    try:

        age = int(
            (message.text or "").strip()
        )

    except ValueError:

        await message.answer(
            "❌ Enter your age as a number."
            if lang == "en"
            else
            "❌ Введи возраст числом."
        )

        return

    if not 13 <= age <= 100:

        await message.answer(

            (
                "❌ You must be at least 13 "
                "years old to use a profile."
                if lang == "en"
                else
                "❌ Использование своей анкеты "
                "доступно с 13 лет."
            )

        )

        return

    await state.update_data(
        age=age
    )

    await state.set_state(
        ProfileStates.gender
    )

    if lang == "en":

        text = "⚧ Select your gender:"

        buttons = [

            InlineKeyboardButton(
                text="👨 Male",
                callback_data="gender:male"
            ),

            InlineKeyboardButton(
                text="👩 Female",
                callback_data="gender:female"
            )

        ]

    else:

        text = "⚧ Выбери пол:"

        buttons = [

            InlineKeyboardButton(
                text="👨 Мужской",
                callback_data="gender:male"
            ),

            InlineKeyboardButton(
                text="👩 Женский",
                callback_data="gender:female"
            )

        ]

    await message.answer(
        text,
        reply_markup=kb([buttons])
    )


# ============================================================
# PROFILE GENDER
# ============================================================

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

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "📸 Send a photo of your real face."
        if lang == "en"
        else
        "📸 Отправь фотографию своего настоящего лица."

    )


# ============================================================
# PROFILE PHOTO
# ============================================================

@dp.message(
    ProfileStates.photo
)
async def profile_photo(
    message: Message,
    state: FSMContext
):

    lang = await db.get_language(
        message.from_user.id
    )

    if not message.photo:

        await message.answer(

            "❌ Send a photo."
            if lang == "en"
            else
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

        (
            "📝 Tell us a few facts about yourself.\n\n"
            "This is optional."
            if lang == "en"
            else
            "📝 Напиши несколько фактов о себе.\n\n"
            "Это необязательно."
        ),

        reply_markup=kb([

            [

                InlineKeyboardButton(

                    text=(
                        "⏭ Skip"
                        if lang == "en"
                        else "⏭ Пропустить"
                    ),

                    callback_data="facts:skip"

                )

            ]

        ])

    )


# ============================================================
# PROFILE FACTS SKIP
# ============================================================

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


# ============================================================
# PROFILE FACTS
# ============================================================

@dp.message(
    ProfileStates.facts
)
async def profile_facts(
    message: Message,
    state: FSMContext
):

    facts = (
        message.text or ""
    ).strip()

    lang = await db.get_language(
        message.from_user.id
    )

    if len(facts) > 1000:

        await message.answer(

            "❌ Maximum 1000 characters."
            if lang == "en"
            else
            "❌ Максимум 1000 символов."

        )

        return

    await finish_profile(
        message,
        message.from_user.id,
        state,
        facts
    )


# ============================================================
# FINISH PROFILE
# ============================================================

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

    lang = await db.get_language(
        user_id
    )

    if lang == "en":

        text = (
            "🎉 <b>Profile created!</b>\n\n"
            "Other users can now see and rate it."
        )

    else:

        text = (
            "🎉 <b>Анкета создана!</b>\n\n"
            "Теперь её смогут видеть "
            "и оценивать другие пользователи."
        )

    await message.answer(

        text,

        reply_markup=main_kb(lang)

    )


# ============================================================
# MY PROFILE
# ============================================================

@dp.callback_query(
    F.data == "my_profile"
)
async def my_profile(
    call: CallbackQuery
):

    await call.answer()

    user = await db.get_profile(
        call.from_user.id
    )

    lang = await db.get_language(
        call.from_user.id
    )

    if not user:

        await call.message.answer(

            "❌ You don't have a profile yet."
            if lang == "en"
            else
            "❌ Анкета ещё не создана.",

            reply_markup=main_kb(lang)

        )

        return

    await send_profile_message(
        call.message,
        user,
        own=True
    )


# ============================================================
# EDIT PROFILE
# ============================================================

@dp.callback_query(
    F.data == "edit_profile"
)
async def edit_profile(
    call: CallbackQuery
):

    await call.answer()

    user = await db.get_profile(
        call.from_user.id
    )

    lang = await db.get_language(
        call.from_user.id
    )

    if not user:

        await call.message.answer(

            "❌ Create a profile first."
            if lang == "en"
            else
            "❌ Сначала создай анкету."

        )

        return

    await call.message.answer(

        "✏️ <b>What would you like to change?</b>"
        if lang == "en"
        else
        "✏️ <b>Что изменить?</b>",

        reply_markup=edit_kb(lang)

    )


# ============================================================
# DELETE PROFILE
# ============================================================

@dp.callback_query(
    F.data == "delete_profile"
)
async def delete_profile_confirm(
    call: CallbackQuery
):

    await call.answer()

    lang = await db.get_language(
        call.from_user.id
    )

    if lang == "en":

        text = (
            "⚠️ <b>Delete profile?</b>\n\n"
            "Your profile will disappear from "
            "rating and all ratings connected "
            "to it will be deleted.\n\n"
            "You can create a new profile later."
        )

    else:

        text = (
            "⚠️ <b>Удалить анкету?</b>\n\n"
            "Анкета исчезнет из рейтинга, а связанные "
            "с ней оценки будут удалены.\n\n"
            "Позже ты сможешь создать новую анкету."
        )

    await call.message.answer(

        text,

        reply_markup=delete_confirm_kb(lang)

    )


@dp.callback_query(
    F.data == "delete:yes"
)
async def delete_profile_yes(
    call: CallbackQuery
):

    await call.answer()

    await db.delete_profile(
        call.from_user.id
    )

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "🗑 <b>Profile deleted.</b>"
        if lang == "en"
        else
        "🗑 <b>Анкета удалена.</b>",

        reply_markup=main_kb(lang)

    )


@dp.callback_query(
    F.data == "delete:no"
)
async def delete_profile_no(
    call: CallbackQuery
):

    await call.answer()

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "❌ Deletion cancelled."
        if lang == "en"
        else
        "❌ Удаление отменено.",

        reply_markup=main_kb(lang)

    )


# ============================================================
# EDIT FIELD
# ============================================================

@dp.callback_query(
    F.data.startswith("edit:")
)
async def edit_field(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    field = (
        call.data.split(":")[1]
    )

    lang = await db.get_language(
        call.from_user.id
    )

    mapping_ru = {

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

    mapping_en = {

        "name": (
            EditStates.name,
            "👤 Enter your new name:"
        ),

        "age": (
            EditStates.age,
            "🎂 Enter your new age (13+):"
        ),

        "photo": (
            EditStates.photo,
            "📸 Send a new photo:"
        ),

        "facts": (
            EditStates.facts,
            "📝 Enter new facts:"
        )

    }

    mapping = (
        mapping_en
        if lang == "en"
        else mapping_ru
    )

    if field == "gender":

        await state.set_state(
            EditStates.gender
        )

        if lang == "en":

            buttons = [

                InlineKeyboardButton(
                    text="👨 Male",
                    callback_data="editgender:male"
                ),

                InlineKeyboardButton(
                    text="👩 Female",
                    callback_data="editgender:female"
                )

            ]

            text = "⚧ Select your new gender:"

        else:

            buttons = [

                InlineKeyboardButton(
                    text="👨 Мужской",
                    callback_data="editgender:male"
                ),

                InlineKeyboardButton(
                    text="👩 Женский",
                    callback_data="editgender:female"
                )

            ]

            text = "⚧ Выбери новый пол:"

        await call.message.answer(

            text,

            reply_markup=kb([buttons])

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


# ============================================================
# EDIT GENDER
# ============================================================

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

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "✅ Gender changed."
        if lang == "en"
        else
        "✅ Пол изменён.",

        reply_markup=main_kb(lang)

    )


# ============================================================
# EDIT NAME
# ============================================================

@dp.message(
    EditStates.name
)
async def edit_name(
    message: Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    lang = await db.get_language(
        message.from_user.id
    )

    if not 2 <= len(value) <= 40:

        await message.answer(

            "❌ Name must be between "
            "2 and 40 characters."
            if lang == "en"
            else
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

        "✅ Name changed."
        if lang == "en"
        else
        "✅ Имя изменено.",

        reply_markup=main_kb(lang)

    )


# ============================================================
# EDIT AGE
# ============================================================

@dp.message(
    EditStates.age
)
async def edit_age(
    message: Message,
    state: FSMContext
):

    lang = await db.get_language(
        message.from_user.id
    )

    try:

        age = int(
            (message.text or "").strip()
        )

    except ValueError:

        await message.answer(

            "❌ Enter your age as a number."
            if lang == "en"
            else
            "❌ Введи возраст числом."

        )

        return

    if not 13 <= age <= 100:

        await message.answer(

            "❌ Age must be between 13 and 100."
            if lang == "en"
            else
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

        "✅ Age changed."
        if lang == "en"
        else
        "✅ Возраст изменён.",

        reply_markup=main_kb(lang)

    )


# ============================================================
# EDIT PHOTO
# ============================================================

@dp.message(
    EditStates.photo
)
async def edit_photo(
    message: Message,
    state: FSMContext
):

    lang = await db.get_language(
        message.from_user.id
    )

    if not message.photo:

        await message.answer(

            "❌ Send a photo."
            if lang == "en"
            else
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

        "✅ Photo changed."
        if lang == "en"
        else
        "✅ Фото изменено.",

        reply_markup=main_kb(lang)

    )


# ============================================================
# EDIT FACTS
# ============================================================

@dp.message(
    EditStates.facts
)
async def edit_facts(
    message: Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    lang = await db.get_language(
        message.from_user.id
    )

    if len(value) > 1000:

        await message.answer(

            "❌ Maximum 1000 characters."
            if lang == "en"
            else
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

        "✅ Facts changed."
        if lang == "en"
        else
        "✅ Факты изменены.",

        reply_markup=main_kb(lang)

    )


# ============================================================
# SHOW RATING PROFILE
# ============================================================

async def show_rating_profile(
    message,
    user,
    state,
    repeated=False
):

    await state.clear()

    await state.update_data(

        rated_user_id=
        user["telegram_id"],

        repeated=repeated

    )

    lang = await db.get_language(
        message.from_user.id
    )

    # Принудительно используем язык
    # смотрящего пользователя.
    user = dict(user)

    user["language"] = lang

    await message.answer_photo(

        user["photo_file_id"],

        caption=
        await profile_text(user),

        reply_markup=profile_kb(
            user["telegram_id"],
            lang
        )

    )

    if repeated:

        if lang == "en":

            text = (
                "⚠️ <b>You have already rated this profile.</b>\n\n"
                "There are no new profiles left.\n\n"
                "Do you want to change your rating?"
            )

            buttons = [

                [

                    InlineKeyboardButton(
                        text="✏️ Change rating",
                        callback_data="repeat:yes"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="➡️ Next",
                        callback_data="rate_people"
                    )

                ]

            ]

        else:

            text = (
                "⚠️ <b>Ты уже оценивал эту анкету.</b>\n\n"
                "Новых анкет больше нет.\n\n"
                "Хочешь изменить свою оценку?"
            )

            buttons = [

                [

                    InlineKeyboardButton(
                        text="✏️ Изменить оценку",
                        callback_data="repeat:yes"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="➡️ Следующая",
                        callback_data="rate_people"
                    )

                ]

            ]

        await message.answer(
            text,
            reply_markup=kb(buttons)
        )

        return

    if lang == "en":

        text = (
            "⭐ <b>Rate appearance</b>\n\n"
            "Enter a number from "
            "<b>1 to 10</b>.\n\n"
            "One digit after the decimal point "
            "is allowed:\n\n"
            "<code>8.5</code>"
        )

    else:

        text = (
            "⭐ <b>Оцени внешность</b>\n\n"
            "Напиши число от "
            "<b>1 до 10</b>.\n\n"
            "Можно использовать "
            "одну цифру после точки "
            "или запятой:\n\n"
            "<code>8.5</code>\n"
            "<code>8,5</code>"
        )

    await message.answer(

        text,

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text=(
                        "⏭ Skip"
                        if lang == "en"
                        else "⏭ Пропустить"
                    ),
                    callback_data="rate_people"
                )

            ]

        ])

    )

    await state.set_state(
        RatingStates.score
    )


# ============================================================
# RATE PEOPLE
# ============================================================

@dp.callback_query(
    F.data == "rate_people"
)
async def rate_people(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    user = await db.random_profile(
        call.from_user.id
    )

    # --------------------------------------------------------
    # ЕСЛИ НОВЫХ АНКЕТ НЕТ
    # --------------------------------------------------------

    if not user:

        user = await db.random_rated_profile(
            call.from_user.id
        )

        if not user:

            lang = await db.get_language(
                call.from_user.id
            )

            await call.message.answer(

                "😔 No profiles available."
                if lang == "en"
                else
                "😔 Сейчас нет доступных "
                "анкет для оценки."

            )

            return

        await show_rating_profile(

            call.message,

            user,

            state,

            repeated=True

        )

        return

    # --------------------------------------------------------
    # ЕСТЬ НОВЫЕ АНКЕТЫ
    # --------------------------------------------------------

    await show_rating_profile(

        call.message,

        user,

        state,

        repeated=False

    )


# ============================================================
# REPEAT RATING CONFIRMATION
# ============================================================

@dp.callback_query(
    F.data == "repeat:yes"
)
async def repeat_rating_yes(
    call: CallbackQuery,
    state: FSMContext
):

    await call.answer()

    data = await state.get_data()

    rated_id = data.get(
        "rated_user_id"
    )

    if not rated_id:

        return

    rating = await db.get_rating(

        call.from_user.id,

        rated_id

    )

    if not rating:

        await call.message.answer(
            "❌ Rating not found."
        )

        await state.clear()

        return

    await state.update_data(

        rating_id=rating["id"],

        repeated=True

    )

    await state.set_state(
        RatingStates.score
    )

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "✏️ Enter your new rating from "
        "<b>1 to 10</b>."
        if lang == "en"
        else
        "✏️ Напиши новую оценку от "
        "<b>1 до 10</b>.",

    )


# ============================================================
# SPECIFIC PROFILE
# ============================================================

@dp.callback_query(
    F.data.startswith("rate:")
)
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
            "❌ You cannot rate yourself."
        )

        return

    user = await db.get_profile(
        target
    )

    if not user:

        await call.message.answer(
            "❌ Profile unavailable."
        )

        return

    already = await db.rating_exists(

        call.from_user.id,

        target

    )

    if already:

        lang = await db.get_language(
            call.from_user.id
        )

        await state.clear()

        await state.update_data(
            rated_user_id=target,
            repeated=True
        )

        await call.message.answer(

            (
                "⚠️ <b>You have already rated this user.</b>\n\n"
                "Do you want to change your rating?"
                if lang == "en"
                else
                "⚠️ <b>Ты уже оценивал этого пользователя.</b>\n\n"
                "Хочешь изменить свою оценку?"
            ),

            reply_markup=kb([

                [

                    InlineKeyboardButton(
                        text=(
                            "✏️ Change rating"
                            if lang == "en"
                            else "✏️ Изменить оценку"
                        ),
                        callback_data="repeat:yes"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text=(
                            "❌ Cancel"
                            if lang == "en"
                            else "❌ Отмена"
                        ),
                        callback_data="rate_people"
                    )

                ]

            ])

        )

        return

    await state.clear()

    await state.update_data(

        rated_user_id=target,

        repeated=False

    )

    await state.set_state(
        RatingStates.score
    )

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        (
            "⭐ Enter a rating from "
            "<b>1 to 10</b>.\n\n"
            "Example: <code>8.7</code>"
            if lang == "en"
            else
            "⭐ Напиши оценку "
            "от <b>1 до 10</b>.\n\n"
            "Например: <code>8.7</code>"
        )

    )


# ============================================================
# RECEIVE SCORE
# ============================================================

@dp.message(
    RatingStates.score
)
async def receive_score(
    message: Message,
    state: FSMContext
):

    raw = (
        message.text or ""
    ).strip().replace(",", ".")

    lang = await db.get_language(
        message.from_user.id
    )

    if not re.fullmatch(

        r"(?:[1-9](?:\.\d)?|10(?:\.0)?)",

        raw

    ):

        await message.answer(

            (
                "❌ Rating must be from "
                "1 to 10.\n\n"
                "Example: <code>7.5</code>"
                if lang == "en"
                else
                "❌ Оценка должна быть "
                "от 1 до 10.\n\n"
                "Например: <code>7.5</code>"
            )

        )

        return

    score = float(raw)

    data = await state.get_data()

    rated_id = data[
        "rated_user_id"
    ]

    if rated_id == message.from_user.id:

        await state.clear()

        await message.answer(
            "❌ You cannot rate yourself."
            if lang == "en"
            else
            "❌ Нельзя оценивать себя."
        )

        return

    repeated = data.get(
        "repeated",
        False
    )

    rating_id = data.get(
        "rating_id"
    )

    # --------------------------------------------------------
    # ИЗМЕНЕНИЕ СТАРОЙ ОЦЕНКИ
    # --------------------------------------------------------

    if repeated:

        if not rating_id:

            rating = await db.get_rating(

                message.from_user.id,

                rated_id

            )

            if not rating:

                await state.clear()

                await message.answer(
                    "❌ Rating not found."
                    if lang == "en"
                    else
                    "❌ Оценка не найдена."
                )

                return

            rating_id = rating["id"]

        await db.update_rating(

            rating_id,

            score

        )

        await state.update_data(
            rating_id=rating_id,
            score=score
        )

    # --------------------------------------------------------
    # НОВАЯ ОЦЕНКА
    # --------------------------------------------------------

    else:

        if await db.rating_exists(

            message.from_user.id,

            rated_id

        ):

            rating = await db.get_rating(

                message.from_user.id,

                rated_id

            )

            rating_id = rating["id"]

            await db.update_rating(

                rating_id,

                score

            )

        else:

            rating = await db.add_rating(

                message.from_user.id,

                rated_id,

                score

            )

            rating_id = rating["id"]

        await state.update_data(

            rating_id=rating_id,

            score=score

        )

    user = await db.get_profile(
        rated_id
    )

    await state.set_state(
        RatingStates.table_type
    )

    await message.answer(

        (
            f"✅ Rating <b>{score:.1f}/10</b> saved!\n\n"
            "📊 <b>Additional table rating</b>\n\n"
            "Optional. Choose a type or skip."
            if lang == "en"
            else
            f"✅ Оценка <b>{score:.1f}/10</b> сохранена!\n\n"
            "📊 <b>Дополнительная оценка по таблице</b>\n\n"
            "Это необязательно.\n"
            "Выбери подходящий тип или пропусти."
        ),

        reply_markup=
        table_kb(
            user["gender"],
            lang
        )

    )


# ============================================================
# TABLE TYPE
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

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        (
            "💬 <b>Would you like to leave advice?</b>\n\n"
            "This is optional."
            if lang == "en"
            else
            "💬 <b>Хочешь оставить совет?</b>\n\n"
            "Это необязательно."
        ),

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text=(
                        "💬 Write advice"
                        if lang == "en"
                        else "💬 Написать совет"
                    ),
                    callback_data="advice:write"
                )

            ],

            [

                InlineKeyboardButton(
                    text=(
                        "⏭ Skip"
                        if lang == "en"
                        else "⏭ Пропустить"
                    ),
                    callback_data="advice:skip"
                )

            ]

        ])

    )


# ============================================================
# ADVICE
# ============================================================

@dp.callback_query(
    RatingStates.advice,
    F.data == "advice:write"
)
async def advice_write(
    call: CallbackQuery
):

    await call.answer()

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        (
            "💬 Write your advice.\n\n"
            "Please be respectful."
            if lang == "en"
            else
            "💬 Напиши свой совет.\n\n"
            "Пожалуйста, оставайся корректным "
            "и уважительным."
        )

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

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "✅ Rating sent!"
        if lang == "en"
        else
        "✅ Оценка отправлена!",

        reply_markup=main_kb(lang)

    )


@dp.message(
    RatingStates.advice
)
async def advice_receive(
    message: Message,
    state: FSMContext
):

    advice = (
        message.text or ""
    ).strip()

    lang = await db.get_language(
        message.from_user.id
    )

    if len(advice) > 1000:

        await message.answer(

            "❌ Maximum 1000 characters."
            if lang == "en"
            else
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

        "✅ Rating and advice sent!"
        if lang == "en"
        else
        "✅ Оценка и совет отправлены!",

        reply_markup=main_kb(lang)

    )


# ============================================================
# NOTIFY RATING
# ============================================================

async def notify_rating(

    rated_id,
    rater_id,
    score,
    table_type,
    advice

):

    lang = await db.get_language(
        rated_id
    )

    if lang == "en":

        text = (
            "🔔 <b>Your profile was rated!</b>\n\n"
            f"⭐ Rating: <b>{score:.1f}/10</b>\n"
        )

        if table_type:

            text += (
                f"📊 Table type: "
                f"<b>{table_type}</b>\n"
            )

        if advice:

            text += (
                "\n💬 <b>Advice:</b>\n"
                f"{advice}\n"
            )

        text += (
            "\n👤 You can view the profile "
            "of the person who rated you."
        )

        button_text = "👤 View profile"

    else:

        text = (
            "🔔 <b>Твою анкету оценили!</b>\n\n"
            f"⭐ Оценка: <b>{score:.1f}/10</b>\n"
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

        button_text = "👤 Посмотреть профиль"

    try:

        await bot.send_message(

            rated_id,

            text,

            reply_markup=kb([

                [

                    InlineKeyboardButton(

                        text=button_text,

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
# VIEW RATER
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

        lang = await db.get_language(
            call.from_user.id
        )

        await call.message.answer(

            "❌ Profile unavailable."
            if lang == "en"
            else
            "❌ Анкета больше недоступна."

        )

        return

    user = dict(user)

    user["language"] = await db.get_language(
        call.from_user.id
    )

    await send_profile_message(

        call.message,

        user,

        own=False

    )


# ============================================================
# REPORT PROFILE
# ============================================================

@dp.callback_query(
    F.data.startswith("report:")
)
async def report_profile(
    call: CallbackQuery
):

    await call.answer()

    reported_id = int(
        call.data.split(":")[1]
    )

    if reported_id == call.from_user.id:

        return

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        (
            "🚩 <b>Why do you want to report this profile?</b>"
            if lang == "en"
            else
            "🚩 <b>Почему ты хочешь пожаловаться "
            "на эту анкету?</b>"
        ),

        reply_markup=
        report_kb(
            reported_id,
            lang
        )

    )


# ============================================================
# REPORT REASON
# ============================================================

@dp.callback_query(
    F.data.startswith("reportreason:")
)
async def report_reason(
    call: CallbackQuery
):

    await call.answer()

    parts = call.data.split(":")

    reported_id = int(
        parts[1]
    )

    reason = parts[2]

    if reported_id == call.from_user.id:

        return

    exists = await db.report_exists(

        call.from_user.id,

        reported_id

    )

    if exists:

        lang = await db.get_language(
            call.from_user.id
        )

        await call.message.answer(

            "⚠️ You have already reported this profile."
            if lang == "en"
            else
            "⚠️ Ты уже жаловался на эту анкету."

        )

        return

    await db.create_report(

        call.from_user.id,

        reported_id,

        reason

    )

    lang = await db.get_language(
        call.from_user.id
    )

    await call.message.answer(

        "✅ Report sent to moderation. Thank you."
        if lang == "en"
        else
        "✅ Жалоба отправлена модерации. Спасибо."

    )

    # --------------------------------------------------------
    # SEND REPORT TO ADMIN
    # --------------------------------------------------------

    reported = await db.get_profile(
        reported_id
    )

    reporter = await db.get_user(
        call.from_user.id
    )

    if not reported:

        return

    admin_text = (

        "🚨 <b>Новая жалоба</b>\n\n"

        f"👤 На пользователя: "
        f"<b>{reported['name']}</b>\n"

        f"🆔 ID: <code>{reported_id}</code>\n"

        f"🚩 Причина: "
        f"<b>{report_reason_name(reason, 'ru')}</b>\n\n"

        f"👮 Жалоба от: "
        f"<code>{call.from_user.id}</code>"
    )

    try:

        sent = await bot.send_photo(

            ADMIN_ID,

            reported["photo_file_id"],

            caption=admin_text,

            reply_markup=kb([

                [

                    InlineKeyboardButton(
                        text="👀 Посмотреть анкету",
                        callback_data=f"admin:view:{reported_id}"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="🗑 Удалить анкету",
                        callback_data=f"admin:delete:{reported_id}"
                    )

                ]

            ])

        )

    except Exception:

        logging.exception(
            "Failed to notify admin about report"
        )


# ============================================================
# ADMIN
# ============================================================

@dp.message(
    Command("admin")
)
async def admin(
    message: Message
):

    if message.from_user.id != ADMIN_ID:
        return

    pending = await db.get_pending_reports()

    await message.answer(

        "🛠 <b>Админ-панель</b>\n\n"

        "/mailing — создать рекламную рассылку\n"
        "/stopmailing — остановить текущую рассылку\n"
        "/mailings — история рассылок\n"
        "/reports — жалобы\n\n"

        f"🚨 Новых жалоб: <b>{len(pending)}</b>"

    )


# ============================================================
# REPORTS
# ============================================================

@dp.message(
    Command("reports")
)
async def reports(
    message: Message
):

    if message.from_user.id != ADMIN_ID:
        return

    rows = await db.get_pending_reports()

    if not rows:

        await message.answer(
            "🚨 Новых жалоб нет."
        )

        return

    await message.answer(
        f"🚨 <b>Жалоб: {len(rows)}</b>\n\n"
        "Ниже будут показаны анкеты."
    )

    for row in rows:

        if not row["reported_photo"]:

            continue

        text = (

            "🚨 <b>Жалоба</b>\n\n"

            f"👤 Пользователь: "
            f"<b>{row['reported_name'] or '—'}</b>\n"

            f"🆔 ID: "
            f"<code>{row['reported_id']}</code>\n"

            f"🚩 Причина: "
            f"<b>{report_reason_name(row['reason'], 'ru')}</b>\n"

            f"👮 Жалоба от: "
            f"<code>{row['reporter_id']}</code>\n"

            f"📌 Жалоба #{row['id']}"
        )

        await message.answer_photo(

            row["reported_photo"],

            caption=text,

            reply_markup=kb([

                [

                    InlineKeyboardButton(
                        text="👀 Посмотреть",
                        callback_data=
                        f"admin:view:{row['reported_id']}"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="🗑 Удалить анкету",
                        callback_data=
                        f"admin:delete:{row['reported_id']}"
                    )

                ],

                [

                    InlineKeyboardButton(
                        text="✅ Отклонить жалобу",
                        callback_data=
                        f"admin:resolve:{row['id']}"
                    )

                ]

            ])

        )


# ============================================================
# ADMIN VIEW PROFILE
# ============================================================

@dp.callback_query(
    F.data.startswith("admin:view:")
)
async def admin_view_profile(
    call: CallbackQuery
):

    if call.from_user.id != ADMIN_ID:

        await call.answer()

        return

    await call.answer()

    user_id = int(
        call.data.split(":")[2]
    )

    user = await db.get_profile(
        user_id
    )

    if not user:

        await call.message.answer(
            "❌ Анкета уже недоступна."
        )

        return

    user = dict(user)

    user["language"] = "ru"

    await call.message.answer_photo(

        user["photo_file_id"],

        caption=
        await profile_text(user),

        reply_markup=kb([

            [

                InlineKeyboardButton(
                    text="🗑 Удалить анкету",
                    callback_data=
                    f"admin:delete:{user_id}"
                )

            ]

        ])

    )


# ============================================================
# ADMIN DELETE PROFILE
# ============================================================

@dp.callback_query(
    F.data.startswith("admin:delete:")
)
async def admin_delete_profile(
    call: CallbackQuery
):

    if call.from_user.id != ADMIN_ID:

        await call.answer()

        return

    await call.answer()

    user_id = int(
        call.data.split(":")[2]
    )

    await db.delete_profile(
        user_id
    )

    await call.message.answer(
        f"🗑 Анкета <code>{user_id}</code> удалена."
    )

    # Сообщаем пользователю.
    try:

        lang = await db.get_language(
            user_id
        )

        await bot.send_message(

            user_id,

            (
                "⚠️ Your profile was removed by moderation."
                if lang == "en"
                else
                "⚠️ Твоя анкета была удалена модерацией."
            )

        )

    except Exception:

        logging.exception(
            "Failed to notify deleted user"
        )


# ============================================================
# ADMIN RESOLVE REPORT
# ============================================================

@dp.callback_query(
    F.data.startswith("admin:resolve:")
)
async def admin_resolve_report(
    call: CallbackQuery
):

    if call.from_user.id != ADMIN_ID:

        await call.answer()

        return

    await call.answer()

    report_id = int(
        call.data.split(":")[2]
    )

    await db.resolve_report(

        report_id,

        "rejected"

    )

    await call.message.answer(
        f"✅ Жалоба #{report_id} отклонена."
    )


# ============================================================
# MAILING
# ============================================================

@dp.message(
    Command("mailing")
)
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


# ============================================================
# MAILING CONTENT
# ============================================================

@dp.message(
    MailingStates.content
)
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

                    callback_data=
                    "mailing:add_button"

                )

            ],

            [

                InlineKeyboardButton(

                    text="➡️ Без кнопки",

                    callback_data=
                    "mailing:no_button"

                )

            ],

            [

                InlineKeyboardButton(

                    text="❌ Отмена",

                    callback_data=
                    "mailing:cancel"

                )

            ]

        ])

    )


# ============================================================
# MAILING BUTTON
# ============================================================

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


@dp.message(
    MailingStates.button_text
)
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


@dp.message(
    MailingStates.button_url
)
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

                    callback_data=
                    "mailing:start"

                )

            ],

            [

                InlineKeyboardButton(

                    text="❌ Отмена",

                    callback_data=
                    "mailing:cancel"

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
# START MAILING
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


# ============================================================
# STOP MAILING
# ============================================================

@dp.message(
    Command("stopmailing")
)
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


# ============================================================
# MAILING MARKUP
# ============================================================

def mailing_markup(
    data
):

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


# ============================================================
# RUN MAILING
# ============================================================

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
# MAILING HISTORY
# ============================================================

@dp.message(
    Command("mailings")
)
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

async def health(
    request
):

    return web.Response(
        text="OK"
    )


async def webhook(
    request
):

    if WEBHOOK_SECRET:

        incoming_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        )

        if incoming_secret != WEBHOOK_SECRET:

            return web.Response(
                status=403,
                text="Forbidden"
            )

    try:

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

    except Exception:

        logging.exception(
            "Webhook processing error"
        )

        return web.Response(
            status=500,
            text="Internal Server Error"
        )


# ============================================================
# STARTUP
# ============================================================

async def on_startup(
    app
):

    await db.connect()

    webhook_url = (
        f"{RENDER_EXTERNAL_URL}"
        "/webhook"
    )

    await bot.set_webhook(

        url=webhook_url,

        secret_token=
        WEBHOOK_SECRET,

        drop_pending_updates=True

    )

    logging.info(
        "Webhook set: %s",
        webhook_url
    )


# ============================================================
# SHUTDOWN
# ============================================================

async def on_shutdown(
    app
):

    await bot.delete_webhook()

    await db.close()

    await bot.session.close()


# ============================================================
# WEB APP
# ============================================================

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


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    web.run_app(

        app,

        host="0.0.0.0",

        port=PORT

    )
