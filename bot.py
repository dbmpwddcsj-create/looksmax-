import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aiosqlite
from aiohttp import web

from aiogram import Bot, Dispatcher, F
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

DATABASE_PATH = os.environ.get(
    "DATABASE_PATH",
    "bot.db",
)

MAX_PHOTOS = 5


# ============================================================
# DATABASE
# ============================================================

class Database:
    def __init__(self, path: str):
        self.path = path

    async def connect(self):
        return await aiosqlite.connect(self.path)

    async def init(self):
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    age INTEGER,
                    gender TEXT,
                    accepted_rules INTEGER DEFAULT 0,
                    rating_mode TEXT DEFAULT 'normal',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    user_id INTEGER PRIMARY KEY,
                    photo_id TEXT,
                    photo_ids TEXT,
                    facts TEXT,
                    height REAL,
                    weight REAL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id)
                        REFERENCES users(telegram_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ratings (
                    rater_id INTEGER NOT NULL,
                    profile_user_id INTEGER NOT NULL,
                    score REAL,
                    look_type TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (rater_id, profile_user_id)
                );

                CREATE TABLE IF NOT EXISTS viewed_profiles (
                    viewer_id INTEGER NOT NULL,
                    profile_user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (viewer_id, profile_user_id)
                );

                CREATE TABLE IF NOT EXISTS likes (
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (from_user_id, to_user_id)
                );

                CREATE TABLE IF NOT EXISTS matches (
                    user_a INTEGER NOT NULL,
                    user_b INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_a, user_b)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER NOT NULL,
                    profile_user_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS advice (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    message TEXT,
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Миграция для старых БД.
            cursor = await db.execute(
                "PRAGMA table_info(users)"
            )
            columns = {
                row[1]
                for row in await cursor.fetchall()
            }

            if "rating_mode" not in columns:
                await db.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN rating_mode TEXT
                    DEFAULT 'normal'
                    """
                )

            await db.commit()

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    async def get_user(self, telegram_id: int):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            return dict(zip(columns, row))

    async def create_user(
        self,
        telegram_id: int,
        username: str | None,
    ):
        async with self.connect() as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users
                (
                    telegram_id,
                    username
                )
                VALUES (?, ?)
                """,
                (
                    telegram_id,
                    username,
                ),
            )

            await db.commit()

        return await self.get_user(telegram_id)

    async def update_user(
        self,
        telegram_id: int,
        data: dict,
    ):
        if not data:
            return

        fields = []
        values = []

        for key, value in data.items():
            fields.append(f"{key} = ?")
            values.append(value)

        values.append(telegram_id)

        async with self.connect() as db:
            await db.execute(
                f"""
                UPDATE users
                SET {", ".join(fields)}
                WHERE telegram_id = ?
                """,
                values,
            )
            await db.commit()

    async def update_user_age(
        self,
        telegram_id: int,
        age: int,
    ):
        await self.update_user(
            telegram_id,
            {"age": age},
        )

    async def update_user_gender(
        self,
        telegram_id: int,
        gender: str,
    ):
        await self.update_user(
            telegram_id,
            {"gender": gender},
        )

    async def get_rating_mode(
        self,
        telegram_id: int,
    ):
        user = await self.get_user(telegram_id)

        if not user:
            return "normal"

        return user.get("rating_mode") or "normal"

    async def set_rating_mode(
        self,
        telegram_id: int,
        mode: str,
    ):
        await self.update_user(
            telegram_id,
            {"rating_mode": mode},
        )

    # --------------------------------------------------------
    # PROFILES
    # --------------------------------------------------------

    async def get_profile(
        self,
        user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM profiles
                WHERE user_id = ?
                """,
                (user_id,),
            )

            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            result = dict(zip(columns, row))

            try:
                result["photo_ids"] = (
                    json.loads(result["photo_ids"])
                    if result.get("photo_ids")
                    else []
                )
            except Exception:
                result["photo_ids"] = []

            return result

    async def create_profile(
        self,
        telegram_id: int,
        photo_id: str,
        photo_ids: list[str],
        facts: str | None,
        height: float | None,
        weight: float | None,
    ):
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO profiles
                (
                    user_id,
                    photo_id,
                    photo_ids,
                    facts,
                    height,
                    weight,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(user_id)
                DO UPDATE SET
                    photo_id = excluded.photo_id,
                    photo_ids = excluded.photo_ids,
                    facts = excluded.facts,
                    height = excluded.height,
                    weight = excluded.weight,
                    status = 'active',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    telegram_id,
                    photo_id,
                    json.dumps(photo_ids),
                    facts,
                    height,
                    weight,
                ),
            )

            await db.commit()

    async def update_profile(
        self,
        user_id: int,
        data: dict,
    ):
        if not data:
            return

        converted = dict(data)

        if "photo_ids" in converted:
            converted["photo_ids"] = json.dumps(
                converted["photo_ids"]
            )

        fields = []
        values = []

        for key, value in converted.items():
            fields.append(f"{key} = ?")
            values.append(value)

        fields.append(
            "updated_at = CURRENT_TIMESTAMP"
        )

        values.append(user_id)

        async with self.connect() as db:
            await db.execute(
                f"""
                UPDATE profiles
                SET {", ".join(fields)}
                WHERE user_id = ?
                """,
                values,
            )
            await db.commit()

    async def update_profile_photos(
        self,
        user_id: int,
        photo_ids: list[str],
    ):
        if not photo_ids:
            return

        await self.update_profile(
            user_id,
            {
                "photo_id": photo_ids[0],
                "photo_ids": photo_ids,
            },
        )

    async def delete_profile(
        self,
        user_id: int,
    ):
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE profiles
                SET status = 'deleted',
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (user_id,),
            )

            await db.commit()

    # --------------------------------------------------------
    # RATING / VIEW HISTORY
    # --------------------------------------------------------

    async def mark_profile_viewed(
        self,
        viewer_id: int,
        profile_user_id: int,
    ):
        if viewer_id == profile_user_id:
            return

        async with self.connect() as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO viewed_profiles
                (
                    viewer_id,
                    profile_user_id
                )
                VALUES (?, ?)
                """,
                (
                    viewer_id,
                    profile_user_id,
                ),
            )

            await db.commit()

    async def get_random_unrated_profile(
        self,
        user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT p.*
                FROM profiles p
                WHERE p.status = 'active'
                  AND p.user_id != ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ratings r
                      WHERE r.rater_id = ?
                        AND r.profile_user_id = p.user_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM viewed_profiles v
                      WHERE v.viewer_id = ?
                        AND v.profile_user_id = p.user_id
                  )
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (
                    user_id,
                    user_id,
                    user_id,
                ),
            )

            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            result = dict(zip(columns, row))

            try:
                result["photo_ids"] = (
                    json.loads(result["photo_ids"])
                    if result.get("photo_ids")
                    else []
                )
            except Exception:
                result["photo_ids"] = []

            return result

    async def get_random_rated_profile(
        self,
        user_id: int,
        exclude_user_id: int | None = None,
    ):
        async with self.connect() as db:
            params = [user_id]

            sql = """
                SELECT p.*
                FROM profiles p
                INNER JOIN ratings r
                    ON r.profile_user_id = p.user_id
                   AND r.rater_id = ?
                WHERE p.status = 'active'
                  AND p.user_id != ?
            """

            params.append(
                exclude_user_id
                if exclude_user_id is not None
                else user_id
            )

            sql += """
                ORDER BY RANDOM()
                LIMIT 1
            """

            cursor = await db.execute(
                sql,
                params,
            )

            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            result = dict(zip(columns, row))

            try:
                result["photo_ids"] = (
                    json.loads(result["photo_ids"])
                    if result.get("photo_ids")
                    else []
                )
            except Exception:
                result["photo_ids"] = []

            return result

    async def get_rating(
        self,
        rater_id: int,
        profile_user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM ratings
                WHERE rater_id = ?
                  AND profile_user_id = ?
                """,
                (
                    rater_id,
                    profile_user_id,
                ),
            )

            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            return dict(zip(columns, row))

    async def save_rating(
        self,
        rater_id: int,
        profile_user_id: int,
        score: float | None,
        look_type: str | None,
    ):
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO ratings
                (
                    rater_id,
                    profile_user_id,
                    score,
                    look_type
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(
                    rater_id,
                    profile_user_id
                )
                DO UPDATE SET
                    score = excluded.score,
                    look_type = excluded.look_type,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    rater_id,
                    profile_user_id,
                    score,
                    look_type,
                ),
            )

            await db.execute(
                """
                INSERT OR IGNORE INTO viewed_profiles
                (
                    viewer_id,
                    profile_user_id
                )
                VALUES (?, ?)
                """,
                (
                    rater_id,
                    profile_user_id,
                ),
            )

            await db.commit()

    async def get_average_rating(
        self,
        user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT AVG(score)
                FROM ratings
                WHERE profile_user_id = ?
                  AND score IS NOT NULL
                """,
                (user_id,),
            )

            row = await cursor.fetchone()

            if not row or row[0] is None:
                return 0.0

            return float(row[0])

    async def get_rating_count(
        self,
        user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM ratings
                WHERE profile_user_id = ?
                """,
                (user_id,),
            )

            row = await cursor.fetchone()

            return int(row[0]) if row else 0

    # --------------------------------------------------------
    # LIKES / MATCHES
    # --------------------------------------------------------

    async def add_like(
        self,
        from_user_id: int,
        to_user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT 1
                FROM likes
                WHERE from_user_id = ?
                  AND to_user_id = ?
                """,
                (
                    from_user_id,
                    to_user_id,
                ),
            )

            already_exists = (
                await cursor.fetchone()
            )

            if already_exists:
                return {
                    "created": False,
                    "mutual": await self.is_match(
                        from_user_id,
                        to_user_id,
                    ),
                }

            await db.execute(
                """
                INSERT INTO likes
                (
                    from_user_id,
                    to_user_id
                )
                VALUES (?, ?)
                """,
                (
                    from_user_id,
                    to_user_id,
                ),
            )

            cursor = await db.execute(
                """
                SELECT 1
                FROM likes
                WHERE from_user_id = ?
                  AND to_user_id = ?
                """,
                (
                    to_user_id,
                    from_user_id,
                ),
            )

            mutual = (
                await cursor.fetchone()
            )

            if mutual:
                a, b = sorted(
                    [
                        from_user_id,
                        to_user_id,
                    ]
                )

                await db.execute(
                    """
                    INSERT OR IGNORE INTO matches
                    (
                        user_a,
                        user_b
                    )
                    VALUES (?, ?)
                    """,
                    (a, b),
                )

            await db.commit()

            return {
                "created": True,
                "mutual": bool(mutual),
            }

    async def is_match(
        self,
        user_a: int,
        user_b: int,
    ):
        a, b = sorted(
            [user_a, user_b]
        )

        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT 1
                FROM matches
                WHERE user_a = ?
                  AND user_b = ?
                """,
                (a, b),
            )

            return bool(
                await cursor.fetchone()
            )

    async def get_like(
        self,
        from_user_id: int,
        to_user_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT 1
                FROM likes
                WHERE from_user_id = ?
                  AND to_user_id = ?
                """,
                (
                    from_user_id,
                    to_user_id,
                ),
            )

            return bool(
                await cursor.fetchone()
            )

    # --------------------------------------------------------
    # REPORTS
    # --------------------------------------------------------

    async def create_report(
        self,
        reporter_id: int,
        profile_user_id: int,
        reason: str,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO reports
                (
                    reporter_id,
                    profile_user_id,
                    reason
                )
                VALUES (?, ?, ?)
                """,
                (
                    reporter_id,
                    profile_user_id,
                    reason,
                ),
            )

            report_id = cursor.lastrowid

            await db.commit()

            cursor = await db.execute(
                """
                SELECT *
                FROM reports
                WHERE id = ?
                """,
                (report_id,),
            )

            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            return [dict(zip(columns, row))]

    async def get_reports(self):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM reports
                WHERE status = 'open'
                ORDER BY id DESC
                """
            )

            rows = await cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in rows
            ]

    async def get_report(
        self,
        report_id: int,
    ):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM reports
                WHERE id = ?
                """,
                (report_id,),
            )

            row = await cursor.fetchone()

            if not row:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            return dict(zip(columns, row))

    # --------------------------------------------------------
    # ADVICE
    # --------------------------------------------------------

    async def create_advice(
        self,
        from_user_id: int,
        to_user_id: int,
        text: str,
        score: float | None,
    ):
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO advice
                (
                    from_user_id,
                    to_user_id,
                    text,
                    score
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    from_user_id,
                    to_user_id,
                    text,
                    score,
                ),
            )

            await db.commit()

    # --------------------------------------------------------
    # BROADCAST
    # --------------------------------------------------------

    async def get_all_users(self):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM users
                """
            )

            rows = await cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in rows
            ]

    async def create_broadcast(
        self,
        admin_id: int,
        message: str,
        sent_count: int,
        failed_count: int,
    ):
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO broadcasts
                (
                    admin_id,
                    message,
                    sent_count,
                    failed_count
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    admin_id,
                    message,
                    sent_count,
                    failed_count,
                ),
            )

            await db.commit()

    async def get_broadcasts(self):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM broadcasts
                ORDER BY id DESC
                """
            )

            rows = await cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in rows
            ]


# ============================================================
# GLOBALS
# ============================================================

db = Database(DATABASE_PATH)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# STATES
# ============================================================

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
    look_type = State()
    advice = State()


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
                    text="⚡ Быстрое оценивание",
                    callback_data="rating_settings",
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


def edit_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📸 Изменить фотографии",
                    callback_data="edit_photos",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎂 Изменить возраст",
                    callback_data="edit_age",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚧ Изменить пол",
                    callback_data="edit_gender",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="menu_profile",
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


def photo_collection_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить ещё",
                    callback_data="add_photo",
                ),
                InlineKeyboardButton(
                    text="✅ Готово",
                    callback_data="photos_done",
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


def photo_first_keyboard():
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
# RATING SETTINGS
# ============================================================

def rating_settings_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Быстро: оценка 1–10",
                    callback_data="set_mode:score",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Быстро: только таблица",
                    callback_data="set_mode:look",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Обычный режим",
                    callback_data="set_mode:normal",
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


def mode_name(mode: str):
    names = {
        "normal": "✏️ Обычный режим",
        "score": "⭐ Быстрая оценка 1–10",
        "look": "📊 Быстрая оценка по таблице",
    }

    return names.get(
        mode,
        "✏️ Обычный режим",
    )


# ============================================================
# RATING KEYBOARDS
# ============================================================

def normal_rating_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Ввести оценку",
                    callback_data="enter_score",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❤️ Нравится",
                    callback_data="like_current",
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


def quick_score_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1",
                    callback_data="quick_score:1",
                ),
                InlineKeyboardButton(
                    text="2",
                    callback_data="quick_score:2",
                ),
                InlineKeyboardButton(
                    text="3",
                    callback_data="quick_score:3",
                ),
                InlineKeyboardButton(
                    text="4",
                    callback_data="quick_score:4",
                ),
                InlineKeyboardButton(
                    text="5",
                    callback_data="quick_score:5",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="6",
                    callback_data="quick_score:6",
                ),
                InlineKeyboardButton(
                    text="7",
                    callback_data="quick_score:7",
                ),
                InlineKeyboardButton(
                    text="8",
                    callback_data="quick_score:8",
                ),
                InlineKeyboardButton(
                    text="9",
                    callback_data="quick_score:9",
                ),
                InlineKeyboardButton(
                    text="10",
                    callback_data="quick_score:10",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❤️ Нравится",
                    callback_data="like_current",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚩 Жалоба",
                    callback_data="report_current",
                ),
                InlineKeyboardButton(
                    text="➡️ Следующая",
                    callback_data="next_profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="back_menu",
                )
            ],
        ]
    )


def quick_look_keyboard(gender: str):
    if gender == "Мужской":
        return male_look_keyboard(
            include_actions=True
        )

    return female_look_keyboard(
        include_actions=True
    )


def male_look_keyboard(
    include_actions=False,
):
    rows = [
        [
            InlineKeyboardButton(
                text="Sub 3",
                callback_data="quick_look:sub3",
            ),
            InlineKeyboardButton(
                text="Sub 5",
                callback_data="quick_look:sub5",
            ),
        ],
        [
            InlineKeyboardButton(
                text="LTN",
                callback_data="quick_look:ltn",
            ),
            InlineKeyboardButton(
                text="MTN",
                callback_data="quick_look:mtn",
            ),
            InlineKeyboardButton(
                text="HTN",
                callback_data="quick_look:htn",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Chad",
                callback_data="quick_look:chad",
            ),
            InlineKeyboardButton(
                text="True Adam",
                callback_data="quick_look:true_adam",
            ),
        ],
    ]

    if include_actions:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="❤️ Нравится",
                        callback_data="like_current",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🚩 Жалоба",
                        callback_data="report_current",
                    ),
                    InlineKeyboardButton(
                        text="➡️ Следующая",
                        callback_data="next_profile",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню",
                        callback_data="back_menu",
                    )
                ],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def female_look_keyboard(
    include_actions=False,
):
    rows = [
        [
            InlineKeyboardButton(
                text="Sub 3",
                callback_data="quick_look:sub3",
            ),
            InlineKeyboardButton(
                text="Sub 5",
                callback_data="quick_look:sub5",
            ),
        ],
        [
            InlineKeyboardButton(
                text="LTB",
                callback_data="quick_look:ltb",
            ),
            InlineKeyboardButton(
                text="MTB",
                callback_data="quick_look:mtb",
            ),
            InlineKeyboardButton(
                text="HTB",
                callback_data="quick_look:htb",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Stacy",
                callback_data="quick_look:stacy",
            ),
            InlineKeyboardButton(
                text="True Eve",
                callback_data="quick_look:true_eve",
            ),
        ],
    ]

    if include_actions:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="❤️ Нравится",
                        callback_data="like_current",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🚩 Жалоба",
                        callback_data="report_current",
                    ),
                    InlineKeyboardButton(
                        text="➡️ Следующая",
                        callback_data="next_profile",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню",
                        callback_data="back_menu",
                    )
                ],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
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


def after_rating_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💡 Добавить совет по улучшению внешности",
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


# ============================================================
# ADMIN
# ============================================================

def admin_report_keyboard(report_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Посмотреть анкету",
                    callback_data=f"admin_view_report:{report_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить анкету",
                    callback_data=f"admin_delete_report:{report_id}",
                )
            ],
        ]
    )


def admin_profile_keyboard(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить анкету",
                    callback_data=f"admin_delete_profile:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К жалобам",
                    callback_data="admin_reports",
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

    elif user.get("username") != message.from_user.username:
        await db.update_user(
            message.from_user.id,
            {
                "username": message.from_user.username
            },
        )

        user = await db.get_user(
            message.from_user.id
        )

    return user


def parse_number(value: str):
    value = value.strip().replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def is_admin(user_id: int):
    return user_id in ADMIN_IDS


async def show_menu(message: Message):
    username = message.from_user.username

    name = (
        f"@{username}"
        if username
        else message.from_user.first_name
        or "пользователь"
    )

    profile = await db.get_profile(
        message.from_user.id
    )

    if profile and profile.get("status") == "active":
        text = (
            f"👋 Привет, {name}!\n\n"
            "✨ Здесь ты можешь получать оценки "
            "своей внешности, оценивать других "
            "и знакомиться с людьми.\n\n"
            "💫 Всё бесплатно!\n\n"
            "Что хочешь сделать?"
        )
    else:
        text = (
            f"👋 Привет, {name}!\n\n"
            "✨ Здесь ты можешь получать оценки "
            "своей внешности, оценивать других "
            "и знакомиться с людьми.\n\n"
            "💫 Всё бесплатно!\n\n"
            "⚠️ Сначала создай анкету.\n\n"
            "Что хочешь сделать?"
        )

    await message.answer(
        text,
        reply_markup=main_menu(),
    )


async def get_photo_ids(profile: dict):
    photo_ids = profile.get("photo_ids")

    if photo_ids:
        return photo_ids

    photo_id = profile.get("photo_id")

    if photo_id:
        return [photo_id]

    return []


async def send_photos(
    message: Message,
    photo_ids: list[str],
    caption: str | None = None,
    reply_markup=None,
):
    if not photo_ids:
        return

    photo_ids = photo_ids[:MAX_PHOTOS]

    if len(photo_ids) == 1:
        await message.answer_photo(
            photo=photo_ids[0],
            caption=caption,
            reply_markup=reply_markup,
        )
        return

    media = []

    for index, photo_id in enumerate(photo_ids):
        if index == 0:
            media.append(
                InputMediaPhoto(
                    media=photo_id,
                    caption=caption,
                )
            )
        else:
            media.append(
                InputMediaPhoto(
                    media=photo_id,
                )
            )

    await message.answer_media_group(
        media=media
    )

    if reply_markup:
        await message.answer(
            "⬇️ Выбери действие:",
            reply_markup=reply_markup,
        )


async def save_profile_from_state(
    user_id: int,
    state: FSMContext,
):
    data = await state.get_data()

    photo_ids = data.get("photo_ids") or []

    if not photo_ids:
        return False

    existing = await db.get_profile(user_id)

    profile_data = {
        "photo_id": photo_ids[0],
        "photo_ids": photo_ids,
        "facts": data.get("facts"),
        "height": data.get("height"),
        "weight": data.get("weight"),
        "status": "active",
    }

    if existing:
        await db.update_profile(
            user_id,
            profile_data,
        )
    else:
        await db.create_profile(
            telegram_id=user_id,
            photo_id=photo_ids[0],
            photo_ids=photo_ids,
            facts=data.get("facts"),
            height=data.get("height"),
            weight=data.get("weight"),
        )

    return True


def format_look_type(value: str):
    names = {
        "sub3": "Sub 3",
        "sub5": "Sub 5",
        "ltn": "LTN",
        "mtn": "MTN",
        "htn": "HTN",
        "chad": "Chad",
        "true_adam": "True Adam",
        "ltb": "LTB",
        "mtb": "MTB",
        "htb": "HTB",
        "stacy": "Stacy",
        "true_eve": "True Eve",
    }

    return names.get(
        value,
        value,
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
            "accepted_rules": 1,
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
# REGISTRATION AGE
# ============================================================

@dp.message(Registration.age)
async def registration_age(
    message: Message,
    state: FSMContext,
):
    try:
        age = int(
            (message.text or "").strip()
        )
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

    await db.update_user_age(
        message.from_user.id,
        age,
    )

    await message.answer(
        "⚧ Выбери пол:",
        reply_markup=gender_keyboard(),
    )

    await state.set_state(
        Registration.gender
    )


# ============================================================
# REGISTRATION GENDER
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

    await db.update_user_gender(
        callback.from_user.id,
        gender,
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

    await callback.message.answer(
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
# RATING SETTINGS
# ============================================================

@dp.callback_query(F.data == "rating_settings")
async def rating_settings(
    callback: CallbackQuery,
):
    mode = await db.get_rating_mode(
        callback.from_user.id
    )

    await callback.message.answer(
        "⚡ Настройки оценивания\n\n"
        "Выбери режим, который будет использоваться "
        "при просмотре анкет.\n\n"
        f"Сейчас выбран: {mode_name(mode)}",
        reply_markup=rating_settings_keyboard(),
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("set_mode:")
)
async def set_rating_mode(
    callback: CallbackQuery,
):
    mode = callback.data.split(
        ":",
        1,
    )[1]

    if mode not in {
        "normal",
        "score",
        "look",
    }:
        await callback.answer(
            "Неизвестный режим.",
            show_alert=True,
        )
        return

    await db.set_rating_mode(
        callback.from_user.id,
        mode,
    )

    await callback.message.answer(
        "✅ Режим оценивания изменён.\n\n"
        f"Теперь используется: {mode_name(mode)}",
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

    await state.update_data(
        photo_ids=[]
    )

    await callback.message.answer(
        "📸 Отправь первую фотографию своего лица.\n\n"
        "Первая фотография обязательна.\n"
        f"Можно добавить до {MAX_PHOTOS} фотографий.",
        reply_markup=photo_first_keyboard(),
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
    data = await state.get_data()

    photo_ids = data.get("photo_ids") or []

    if len(photo_ids) >= MAX_PHOTOS:
        await message.answer(
            f"❌ Максимум {MAX_PHOTOS} фотографий.",
            reply_markup=photo_collection_keyboard(),
        )
        return

    photo_ids.append(
        message.photo[-1].file_id
    )

    await state.update_data(
        photo_ids=photo_ids
    )

    await message.answer(
        "✅ Фотография добавлена.\n\n"
        f"Добавлено: {len(photo_ids)}/{MAX_PHOTOS}\n\n"
        "Можешь добавить ещё фотографии "
        "или нажать «Готово».",
        reply_markup=photo_collection_keyboard(),
    )


@dp.message(ProfileCreation.photo)
async def invalid_photo(
    message: Message,
):
    await message.answer(
        "❌ Отправь именно фотографию.",
        reply_markup=photo_first_keyboard(),
    )


@dp.callback_query(
    ProfileCreation.photo,
    F.data == "add_photo",
)
async def add_photo(
    callback: CallbackQuery,
):
    await callback.message.answer(
        "📸 Отправь следующую фотографию."
    )

    await callback.answer()


@dp.callback_query(
    ProfileCreation.photo,
    F.data == "photos_done",
)
async def photos_done(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    photo_ids = data.get("photo_ids") or []

    if not photo_ids:
        await callback.answer(
            "Сначала отправь первую фотографию.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "📝 Напиши несколько фактов о себе.\n\n"
        "Это необязательно.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⏭ Пропустить",
                        callback_data="skip_profile_facts",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="cancel",
                    )
                ],
            ]
        ),
    )

    await state.set_state(
        ProfileCreation.facts
    )

    await callback.answer()


# ============================================================
# PROFILE FACTS
# ============================================================

@dp.callback_query(
    ProfileCreation.facts,
    F.data == "skip_profile_facts",
)
async def skip_profile_facts(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.update_data(
        facts=None
    )

    await ask_profile_height(
        callback.message,
        state,
    )

    await callback.answer()


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

    await ask_profile_height(
        message,
        state,
    )


async def ask_profile_height(
    message: Message,
    state: FSMContext,
):
    await message.answer(
        "📏 Укажи рост в сантиметрах.\n\n"
        "Например: 180\n"
        "Если не хочешь указывать — нажми «Пропустить».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⏭ Пропустить",
                        callback_data="skip_profile_height",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="cancel",
                    )
                ],
            ]
        ),
    )

    await state.set_state(
        ProfileCreation.height
    )


# ============================================================
# PROFILE HEIGHT
# ============================================================

@dp.callback_query(
    ProfileCreation.height,
    F.data == "skip_profile_height",
)
async def skip_profile_height(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.update_data(
        height=None
    )

    await ask_profile_weight(
        callback.message,
        state,
    )

    await callback.answer()


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
                "Например: 180",
            )
            return

        if height < 100 or height > 250:
            await message.answer(
                "❌ Укажи рост от 100 до 250 см.",
            )
            return

    await state.update_data(
        height=height
    )

    await ask_profile_weight(
        message,
        state,
    )


async def ask_profile_weight(
    message: Message,
    state: FSMContext,
):
    await message.answer(
        "⚖️ Укажи вес в килограммах.\n\n"
        "Можно написать:\n"
        "75\n"
        "75.5\n"
        "75,5\n\n"
        "Если не хочешь указывать — нажми «Пропустить».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⏭ Пропустить",
                        callback_data="skip_profile_weight",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="cancel",
                    )
                ],
            ]
        ),
    )

    await state.set_state(
        ProfileCreation.weight
    )


# ============================================================
# PROFILE WEIGHT
# ============================================================

@dp.callback_query(
    ProfileCreation.weight,
    F.data == "skip_profile_weight",
)
async def skip_profile_weight(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.update_data(
        weight=None
    )

    await finish_profile_creation(
        callback.message,
        state,
        callback.from_user.id,
    )

    await callback.answer()


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
                "Например: 75 или 75,5",
            )
            return

        if weight < 30 or weight > 300:
            await message.answer(
                "❌ Укажи вес от 30 до 300 кг.",
            )
            return

    await state.update_data(
        weight=weight
    )

    await finish_profile_creation(
        message,
        state,
        message.from_user.id,
    )


async def finish_profile_creation(
    message: Message,
    state: FSMContext,
    user_id: int,
):
    saved = await save_profile_from_state(
        user_id,
        state,
    )

    if not saved:
        await message.answer(
            "❌ Не удалось сохранить фотографии.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

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

    await send_profile(
        callback.message,
        profile,
        admin=False,
    )

    await callback.answer()


async def build_profile_text(
    profile: dict,
):
    user = await db.get_user(
        profile["user_id"]
    )

    if not user:
        return None

    average = await db.get_average_rating(
        profile["user_id"]
    )

    count = await db.get_rating_count(
        profile["user_id"]
    )

    username = user.get("username")

    text = (
        f"👤 @{username or 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—')}\n"
        f"⚧ Пол: {user.get('gender', '—')}\n"
        f"⭐ Средняя оценка: {average:.1f}/10\n"
        f"📊 Оценок: {count}\n"
    )

    if profile.get("facts"):
        text += (
            f"\n📝 Факты:\n"
            f"{profile['facts']}\n"
        )

    if profile.get("height"):
        text += (
            f"\n📏 Рост: "
            f"{profile['height']} см"
        )

    if profile.get("weight"):
        text += (
            f"\n⚖️ Вес: "
            f"{profile['weight']} кг"
        )

    return text


async def send_profile(
    message: Message,
    profile: dict,
    admin: bool = False,
):
    text = await build_profile_text(
        profile
    )

    if text is None:
        return

    photo_ids = await get_photo_ids(
        profile
    )

    if admin:
        keyboard = admin_profile_keyboard(
            profile["user_id"]
        )
    else:
        keyboard = profile_keyboard()

    await send_photos(
        message,
        photo_ids,
        caption=text,
        reply_markup=keyboard,
    )


# ============================================================
# DELETE OWN PROFILE
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
# EDIT PROFILE MENU
# ============================================================

@dp.callback_query(F.data == "edit_profile")
async def edit_profile(
    callback: CallbackQuery,
):
    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile or profile.get("status") != "active":
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "✏️ Что хочешь изменить?",
        reply_markup=edit_profile_keyboard(),
    )

    await callback.answer()


# ============================================================
# EDIT AGE
# ============================================================

@dp.callback_query(F.data == "edit_age")
async def edit_age_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.answer(
        "🎂 Введи новый возраст.\n\n"
        "Доступно только с 18 лет.",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        ProfileEdit.age
    )

    await callback.answer()


@dp.message(ProfileEdit.age)
async def edit_age_receive(
    message: Message,
    state: FSMContext,
):
    try:
        age = int(
            (message.text or "").strip()
        )
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

    await db.update_user_age(
        message.from_user.id,
        age,
    )

    await state.clear()

    await message.answer(
        "✅ Возраст изменён.",
        reply_markup=main_menu(),
    )


# ============================================================
# EDIT GENDER
# ============================================================

@dp.callback_query(F.data == "edit_gender")
async def edit_gender_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.answer(
        "⚧ Выбери новый пол:",
        reply_markup=gender_keyboard(),
    )

    await state.set_state(
        ProfileEdit.gender
    )

    await callback.answer()


@dp.callback_query(
    ProfileEdit.gender,
    F.data.in_({
        "gender_male",
        "gender_female",
    }),
)
async def edit_gender_receive(
    callback: CallbackQuery,
    state: FSMContext,
):
    gender = (
        "Мужской"
        if callback.data == "gender_male"
        else "Женский"
    )

    await db.update_user_gender(
        callback.from_user.id,
        gender,
    )

    await state.clear()

    await callback.message.answer(
        "✅ Пол изменён.",
        reply_markup=main_menu(),
    )

    await callback.answer()


# ============================================================
# EDIT PHOTOS
# ============================================================

@dp.callback_query(F.data == "edit_photos")
async def edit_photos_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await state.update_data(
        photo_ids=[]
    )

    await callback.message.answer(
        "📸 Отправь первую новую фотографию.\n\n"
        "Она заменит старые фотографии.\n"
        "Первая фотография обязательна.\n"
        f"Можно добавить до {MAX_PHOTOS} фотографий.",
        reply_markup=photo_first_keyboard(),
    )

    await state.set_state(
        ProfileEdit.photos
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

    photo_ids = data.get("photo_ids") or []

    if len(photo_ids) >= MAX_PHOTOS:
        await message.answer(
            f"❌ Максимум {MAX_PHOTOS} фотографий.",
            reply_markup=photo_collection_keyboard(),
        )
        return

    photo_ids.append(
        message.photo[-1].file_id
    )

    await state.update_data(
        photo_ids=photo_ids
    )

    await message.answer(
        f"✅ Фотография добавлена.\n\n"
        f"Добавлено: {len(photo_ids)}/{MAX_PHOTOS}",
        reply_markup=photo_collection_keyboard(),
    )


@dp.message(ProfileEdit.photos)
async def invalid_edit_photo(
    message: Message,
):
    await message.answer(
        "❌ Отправь именно фотографию.",
        reply_markup=photo_first_keyboard(),
    )


@dp.callback_query(
    ProfileEdit.photos,
    F.data == "add_photo",
)
async def edit_add_photo(
    callback: CallbackQuery,
):
    await callback.message.answer(
        "📸 Отправь следующую фотографию."
    )

    await callback.answer()


@dp.callback_query(
    ProfileEdit.photos,
    F.data == "photos_done",
)
async def edit_photos_done(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    photo_ids = data.get("photo_ids") or []

    if not photo_ids:
        await callback.answer(
            "Сначала отправь первую фотографию.",
            show_alert=True,
        )
        return

    await db.update_profile_photos(
        callback.from_user.id,
        photo_ids,
    )

    await state.clear()

    await callback.message.answer(
        "✅ Фотографии изменены.",
        reply_markup=main_menu(),
    )

    await callback.answer()


# ============================================================
# RATING START
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

    await show_next_profile(
        callback.message,
        callback.from_user.id,
        state,
    )

    await callback.answer()


@dp.callback_query(F.data == "next_profile")
async def next_profile(
    callback: CallbackQuery,
    state: FSMContext,
):
    current_id = (
        await state.get_data()
    ).get(
        "rating_profile_user_id"
    )

    # ВАЖНО:
    # текущая анкета помечается просмотренной.
    # Поэтому повторно через "Следующая"
    # она уже не попадёт.
    if current_id:
        await db.mark_profile_viewed(
            callback.from_user.id,
            current_id,
        )

    await state.clear()

    await show_next_profile(
        callback.message,
        callback.from_user.id,
        state,
    )

    await callback.answer()


async def show_next_profile(
    message: Message,
    user_id: int,
    state: FSMContext,
):
    profile = await db.get_random_unrated_profile(
        user_id
    )

    if profile:
        await send_rating_profile(
            message,
            profile,
            state,
            repeated=False,
        )
        return

    profile = await db.get_random_rated_profile(
        user_id,
        exclude_user_id=None,
    )

    if profile:
        previous = await db.get_rating(
            user_id,
            profile["user_id"],
        )

        previous_score = None

        if previous and previous.get("score") is not None:
            previous_score = float(
                previous["score"]
            )

        text = (
            "⚠️ Новых анкет, которые ты ещё "
            "не оценивал, больше нет.\n\n"
            "Теперь показываются анкеты, "
            "которые ты уже оценивал."
        )

        if previous_score is not None:
            text += (
                f"\n\nПредыдущая оценка: "
                f"{previous_score:.1f}/10."
            )

        await message.answer(text)

        await send_rating_profile(
            message,
            profile,
            state,
            repeated=True,
            previous_score=previous_score,
        )

        return

    await message.answer(
        "😔 Сейчас нет доступных анкет.",
        reply_markup=main_menu(),
    )


async def send_rating_profile(
    message: Message,
    profile: dict,
    state: FSMContext,
    repeated: bool = False,
    previous_score: float | None = None,
):
    profile_user_id = profile["user_id"]

    await state.update_data(
        rating_profile_user_id=profile_user_id
    )

    await db.mark_profile_viewed(
        message.chat.id,
        profile_user_id,
    )

    user = await db.get_user(
        profile_user_id
    )

    if not user:
        return

    text = (
        f"👤 @{user.get('username') or 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—')}\n"
        f"⚧ Пол: {user.get('gender', '—')}\n"
    )

    if profile.get("facts"):
        text += (
            f"\n📝 Факты:\n"
            f"{profile['facts']}\n"
        )

    if profile.get("height"):
        text += (
            f"\n📏 Рост: "
            f"{profile['height']} см"
        )

    if profile.get("weight"):
        text += (
            f"\n⚖️ Вес: "
            f"{profile['weight']} кг"
        )

    if repeated and previous_score is not None:
        text += (
            f"\n\n⚠️ Ты уже оценивал эту анкету "
            f"на {previous_score:.1f}/10."
        )

    mode = await db.get_rating_mode(
        message.chat.id
    )

    if mode == "score":
        keyboard = quick_score_keyboard()

    elif mode == "look":
        keyboard = quick_look_keyboard(
            user.get("gender")
        )

    else:
        keyboard = normal_rating_keyboard()

    photo_ids = await get_photo_ids(
        profile
    )

    await send_photos(
        message,
        photo_ids,
        caption=text,
        reply_markup=keyboard,
    )


# ============================================================
# QUICK SCORE
# ============================================================

@dp.callback_query(
    F.data.startswith("quick_score:")
)
async def quick_score(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    if not profile_user_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    try:
        score = float(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка оценки.",
            show_alert=True,
        )
        return

    existing = await db.get_rating(
        callback.from_user.id,
        profile_user_id,
    )

    # Быстрый режим должен быть быстрым:
    # если уже оценивал, оценка просто меняется.
    await db.save_rating(
        rater_id=callback.from_user.id,
        profile_user_id=profile_user_id,
        score=score,
        look_type=(
            existing.get("look_type")
            if existing
            else None
        ),
    )

    await notify_rating(
        profile_user_id,
        callback.from_user.id,
        score,
        (
            existing.get("look_type")
            if existing
            else None
        ),
    )

    await callback.answer(
        f"Оценка {int(score)}/10 сохранена."
    )

    await state.clear()

    # Автоматически следующая анкета.
    await show_next_profile(
        callback.message,
        callback.from_user.id,
        state,
    )


# ============================================================
# NORMAL SCORE
# ============================================================

@dp.callback_query(F.data == "enter_score")
async def enter_score(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    if not data.get("rating_profile_user_id"):
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "⭐ Напиши оценку от 1 до 10.\n\n"
        "Можно использовать десятичные значения:\n\n"
        "5.6\n"
        "7.5\n"
        "8.25\n"
        "9.8",
        reply_markup=cancel_keyboard(),
    )

    await state.set_state(
        Rating.score
    )

    await callback.answer()


@dp.message(Rating.score)
async def receive_score(
    message: Message,
    state: FSMContext,
):
    score = parse_number(
        message.text or ""
    )

    if score is None:
        await message.answer(
            "❌ Не понял оценку.\n\n"
            "Напиши число от 1 до 10.",
            reply_markup=cancel_keyboard(),
        )
        return

    if score < 1 or score > 10:
        await message.answer(
            "❌ Оценка должна быть от 1 до 10.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(
        pending_score=score
    )

    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    existing = await db.get_rating(
        message.from_user.id,
        profile_user_id,
    )

    if existing:
        previous_score = existing.get(
            "score"
        )

        if previous_score is not None:
            await message.answer(
                f"⚠️ Ты уже оценивал эту анкету "
                f"на {float(previous_score):.1f}/10.\n\n"
                f"Изменить оценку на {score:.1f}/10?",
                reply_markup=rating_confirm_keyboard(),
            )

            await state.set_state(
                Rating.confirm_change
            )

            return

    await ask_look_type(
        message,
        state,
    )


# ============================================================
# CONFIRM CHANGING SCORE
# ============================================================

@dp.callback_query(F.data == "confirm_rating")
async def confirm_rating(
    callback: CallbackQuery,
    state: FSMContext,
):
    await ask_look_type(
        callback.message,
        state,
    )

    await callback.answer()


@dp.callback_query(
    F.data == "cancel_rating_change"
)
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
# LOOK TYPE
# ============================================================

async def ask_look_type(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    if not profile_user_id:
        await message.answer(
            "❌ Анкета не найдена.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    user = await db.get_user(
        profile_user_id
    )

    if not user:
        await message.answer(
            "❌ Пользователь не найден.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    if user.get("gender") == "Мужской":
        keyboard = male_look_keyboard()
    else:
        keyboard = female_look_keyboard()

    await message.answer(
        "📊 Оценка по таблице — необязательная.\n\n"
        "Если хочешь, выбери подходящий тип.\n"
        "Если не хочешь — нажми «Пропустить».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                *keyboard.inline_keyboard,
                [
                    InlineKeyboardButton(
                        text="⏭ Пропустить",
                        callback_data="look:skip",
                    )
                ],
            ]
        ),
    )

    await state.set_state(
        Rating.look_type
    )


@dp.callback_query(
    Rating.look_type,
    F.data.startswith("look:")
)
async def select_look_type(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.split(
        ":",
        1,
    )[1]

    look_type = None

    if value != "skip":
        look_type = value

    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    score = data.get(
        "pending_score"
    )

    if not profile_user_id or score is None:
        await callback.message.answer(
            "❌ Не удалось сохранить оценку.",
            reply_markup=main_menu(),
        )
        await state.clear()
        await callback.answer()
        return

    await db.save_rating(
        rater_id=callback.from_user.id,
        profile_user_id=profile_user_id,
        score=float(score),
        look_type=look_type,
    )

    await notify_rating(
        profile_user_id,
        callback.from_user.id,
        float(score),
        look_type,
    )

    if look_type:
        table_text = (
            f"\n📊 Тип по таблице: "
            f"{format_look_type(look_type)}"
        )
    else:
        table_text = (
            "\n📊 Оценку по таблице пропустили."
        )

    await callback.message.answer(
        f"✅ Оценка сохранена: "
        f"{float(score):.1f}/10."
        f"{table_text}",
        reply_markup=after_rating_keyboard(),
    )

    await state.set_state(None)

    await callback.answer()


# ============================================================
# QUICK LOOK
# ============================================================

@dp.callback_query(
    F.data.startswith("quick_look:")
)
async def quick_look(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    profile_user_id = data.get(
        "rating_profile_user_id"
    )

    if not profile_user_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    look_type = callback.data.split(
        ":",
        1,
    )[1]

    await db.save_rating(
        rater_id=callback.from_user.id,
        profile_user_id=profile_user_id,
        score=None,
        look_type=look_type,
    )

    await notify_rating(
        profile_user_id,
        callback.from_user.id,
        None,
        look_type,
    )

    await callback.answer(
        f"{format_look_type(look_type)} сохранено."
    )

    await state.clear()

    # Автоматически следующая анкета.
    await show_next_profile(
        callback.message,
        callback.from_user.id,
        state,
    )


# ============================================================
# NOTIFICATION
# ============================================================

async def notify_rating(
    profile_user_id: int,
    rater_id: int,
    score: float | None,
    look_type: str | None,
):
    try:
        average = await db.get_average_rating(
            profile_user_id
        )

        if score is not None:
            text = (
                "⭐ Твою анкету оценили!\n\n"
                f"Оценка: {score:.1f}/10\n"
                f"Средняя оценка: {average:.1f}/10"
            )
        else:
            text = (
                "📊 Твою анкету оценили "
                "по таблице!\n\n"
            )

        if look_type:
            text += (
                f"\n📊 Тип по таблице: "
                f"{format_look_type(look_type)}"
            )

        await bot.send_message(
            profile_user_id,
            text,
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
    try:
        user_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        user_id
    )

    if not profile or profile.get("status") != "active":
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    await send_rater_profile(
        callback.message,
        profile,
    )

    await callback.answer()


async def send_rater_profile(
    message: Message,
    profile: dict,
):
    user = await db.get_user(
        profile["user_id"]
    )

    if not user:
        return

    average = await db.get_average_rating(
        profile["user_id"]
    )

    text = (
        f"👤 @{user.get('username') or 'без username'}\n"
        f"🎂 Возраст: {user.get('age', '—')}\n"
        f"⚧ Пол: {user.get('gender', '—')}\n"
        f"⭐ Средняя оценка: {average:.1f}/10\n"
    )

    if profile.get("facts"):
        text += (
            f"\n📝 Факты:\n"
            f"{profile['facts']}\n"
        )

    if profile.get("height"):
        text += (
            f"\n📏 Рост: "
            f"{profile['height']} см"
        )

    if profile.get("weight"):
        text += (
            f"\n⚖️ Вес: "
            f"{profile['weight']} кг"
        )

    await send_photos(
        message,
        await get_photo_ids(profile),
        caption=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐ Оценить",
                        callback_data=(
                            f"rate_user:{profile['user_id']}"
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
    try:
        user_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    if user_id == callback.from_user.id:
        await callback.answer(
            "Нельзя оценить себя.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        user_id
    )

    if not profile or profile.get("status") != "active":
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    await state.clear()

    await state.update_data(
        rating_profile_user_id=user_id
    )

    user = await db.get_user(user_id)

    mode = await db.get_rating_mode(
        callback.from_user.id
    )

    if mode == "score":
        keyboard = quick_score_keyboard()

    elif mode == "look":
        keyboard = quick_look_keyboard(
            user.get("gender")
        )

    else:
        keyboard = normal_rating_keyboard()

    await send_photos(
        callback.message,
        await get_photo_ids(profile),
        caption=(
            f"👤 @{user.get('username') or 'без username'}\n"
            f"🎂 Возраст: {user.get('age', '—')}\n"
            f"⚧ Пол: {user.get('gender', '—')}\n\n"
            "⭐ Оцени эту анкету:"
        ),
        reply_markup=keyboard,
    )

    await callback.answer()


# ============================================================
# LIKE SYSTEM
# ============================================================

@dp.callback_query(F.data == "like_current")
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

    target_profile = await db.get_profile(
        target_id
    )

    if (
        not target_profile
        or target_profile.get("status") != "active"
    ):
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    result = await db.add_like(
        from_user_id=callback.from_user.id,
        to_user_id=target_id,
    )

    if not result["created"]:
        if result["mutual"]:
            await callback.answer(
                "❤️ У вас уже взаимная симпатия!",
                show_alert=True,
            )
        else:
            await callback.answer(
                "❤️ Ты уже поставил лайк этой анкете.",
                show_alert=True,
            )
        return

    if result["mutual"]:
        await notify_match(
            callback.from_user.id,
            target_id,
        )

        await callback.answer(
            "💞 Взаимная симпатия! Вы можете познакомиться.",
            show_alert=True,
        )

        await callback.message.answer(
            "💞 Взаимная симпатия!\n\n"
            "Вы понравились друг другу. "
            "Я отправил вам Telegram-контакты друг друга."
        )

    else:
        await notify_like(
            target_id,
            callback.from_user.id,
        )

        await callback.answer(
            "❤️ Симпатия отправлена!",
            show_alert=True,
        )

        await callback.message.answer(
            "❤️ Симпатия отправлена!"
        )


async def user_contact_text(
    user_id: int,
):
    user = await db.get_user(user_id)

    if not user:
        return f"tg://user?id={user_id}"

    username = user.get("username")

    if username:
        return f"@{username}"

    return f'<a href="tg://user?id={user_id}">Открыть профиль</a>'


async def notify_like(
    target_id: int,
    from_user_id: int,
):
    try:
        from_user = await db.get_user(
            from_user_id
        )

        name = (
            f"@{from_user.get('username')}"
            if from_user
            and from_user.get("username")
            else "кто-то"
        )

        await bot.send_message(
            target_id,
            "❤️ Твоя анкета понравилась одному человеку!\n\n"
            f"От: {name}\n\n"
            "Ты можешь посмотреть его анкету. "
            "Если симпатия окажется взаимной — "
            "вы сможете познакомиться.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть анкету",
                            callback_data=(
                                f"view_like:{from_user_id}"
                            ),
                        )
                    ]
                ]
            ),
        )

    except Exception:
        logging.exception(
            "Failed to notify like"
        )


async def notify_match(
    user_a: int,
    user_b: int,
):
    try:
        contact_a = await user_contact_text(
            user_a
        )

        contact_b = await user_contact_text(
            user_b
        )

        await bot.send_message(
            user_a,
            "💞 Взаимная симпатия!\n\n"
            "Ваша симпатия взаимна.\n\n"
            f"👤 Telegram: {contact_b}",
            parse_mode="HTML",
        )

        await bot.send_message(
            user_b,
            "💞 Взаимная симпатия!\n\n"
            "Ваша симпатия взаимна.\n\n"
            f"👤 Telegram: {contact_a}",
            parse_mode="HTML",
        )

    except Exception:
        logging.exception(
            "Failed to notify match"
        )


@dp.callback_query(
    F.data.startswith("view_like:")
)
async def view_like(
    callback: CallbackQuery,
):
    try:
        user_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    if user_id == callback.from_user.id:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        user_id
    )

    if not profile or profile.get("status") != "active":
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    mutual = await db.is_match(
        callback.from_user.id,
        user_id,
    )

    await send_like_profile(
        callback.message,
        profile,
        mutual,
    )

    await callback.answer()


async def send_like_profile(
    message: Message,
    profile: dict,
    mutual: bool,
):
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

    if mutual:
        text += (
            "\n💞 У вас взаимная симпатия!"
        )

    keyboard_rows = []

    if not mutual:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="❤️ Мне тоже нравится",
                    callback_data=(
                        f"like_back:{profile['user_id']}"
                    ),
                )
            ]
        )

    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В меню",
                callback_data="back_menu",
            )
        ]
    )

    await send_photos(
        message,
        await get_photo_ids(profile),
        caption=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard_rows
        ),
    )


@dp.callback_query(
    F.data.startswith("like_back:")
)
async def like_back(
    callback: CallbackQuery,
):
    try:
        target_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    if target_id == callback.from_user.id:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    result = await db.add_like(
        from_user_id=callback.from_user.id,
        to_user_id=target_id,
    )

    if result["mutual"]:
        await notify_match(
            callback.from_user.id,
            target_id,
        )

        await callback.message.answer(
            "💞 Взаимная симпатия!\n\n"
            "Я отправил вам Telegram-контакты друг друга."
        )

        await callback.answer(
            "Взаимная симпатия!",
            show_alert=True,
        )

    else:
        await notify_like(
            target_id,
            callback.from_user.id,
        )

        await callback.answer(
            "❤️ Симпатия отправлена!",
            show_alert=True,
        )


# ============================================================
# ADVICE
# ============================================================

@dp.callback_query(F.data == "add_advice")
async def advice_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    to_user_id = data.get(
        "rating_profile_user_id"
    )

    if not to_user_id:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        to_user_id
    )

    if not profile or profile.get("status") != "active":
        await callback.answer(
            "Анкета недоступна.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "💡 Напиши совет по улучшению внешности.\n\n"
        "Например, совет по причёске, стилю, "
        "фотографии или другим аспектам внешности.",
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
            "❌ Пользователь не найден.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    profile = await db.get_profile(
        to_user_id
    )

    if not profile or profile.get("status") != "active":
        await message.answer(
            "❌ Анкета пользователя недоступна.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    existing = await db.get_rating(
        message.from_user.id,
        to_user_id,
    )

    score = (
        float(existing["score"])
        if existing
        and existing.get("score") is not None
        else None
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
            "💡 Тебе оставили совет по улучшению внешности!\n\n"
            f"{text}",
        )
    except Exception:
        logging.exception(
            "Failed to send advice"
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

    if not data.get("rating_profile_user_id"):
        await callback.answer(
            "Анкета не найдена.",
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
            "❌ Анкета не найдена.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    report = await db.create_report(
        reporter_id=message.from_user.id,
        profile_user_id=profile_user_id,
        reason=reason,
    )

    report_id = (
        report[0]["id"]
        if report
        else None
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚩 НОВАЯ ЖАЛОБА\n\n"
                f"Жалоба #{report_id or '—'}\n"
                f"От: {message.from_user.id}\n"
                f"На: {profile_user_id}\n"
                f"Причина: {reason}",
                reply_markup=(
                    admin_report_keyboard(report_id)
                    if report_id
                    else None
                ),
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
# ADMIN MENU
# ============================================================

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


# ============================================================
# ADMIN REPORTS
# ============================================================

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

    for report in reports[:30]:
        await callback.message.answer(
            f"🚩 Жалоба #{report['id']}\n\n"
            f"От: {report['reporter_id']}\n"
            f"На: {report['profile_user_id']}\n"
            f"Причина:\n{report['reason']}",
            reply_markup=admin_report_keyboard(
                report["id"]
            ),
        )

    await callback.answer()


# ============================================================
# ADMIN VIEW REPORT PROFILE
# ============================================================

@dp.callback_query(
    F.data.startswith("admin_view_report:")
)
async def admin_view_report(
    callback: CallbackQuery,
):
    if not is_admin(callback.from_user.id):
        return

    report_id = int(
        callback.data.split(":")[1]
    )

    report = await db.get_report(
        report_id
    )

    if not report:
        await callback.answer(
            "Жалоба не найдена.",
            show_alert=True,
        )
        return

    profile = await db.get_profile(
        report["profile_user_id"]
    )

    if not profile:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    if profile.get("status") != "active":
        await callback.answer(
            "Эта анкета уже удалена.",
            show_alert=True,
        )
        return

    await send_profile(
        callback.message,
        profile,
        admin=True,
    )

    await callback.answer()


# ============================================================
# ADMIN DELETE FROM REPORT
# ============================================================

@dp.callback_query(
    F.data.startswith("admin_delete_report:")
)
async def admin_delete_report(
    callback: CallbackQuery,
):
    if not is_admin(callback.from_user.id):
        return

    report_id = int(
        callback.data.split(":")[1]
    )

    report = await db.get_report(
        report_id
    )

    if not report:
        await callback.answer(
            "Жалоба не найдена.",
            show_alert=True,
        )
        return

    user_id = report["profile_user_id"]

    profile = await db.get_profile(
        user_id
    )

    if not profile:
        await callback.answer(
            "Анкета уже отсутствует.",
            show_alert=True,
        )
        return

    await db.delete_profile(
        user_id
    )

    await callback.message.answer(
        f"🗑 Анкета пользователя "
        f"{user_id} удалена.",
    )

    try:
        await bot.send_message(
            user_id,
            "⚠️ Твоя анкета была удалена модерацией.",
        )
    except Exception:
        logging.exception(
            "Failed to notify deleted user"
        )

    await callback.answer(
        "Анкета удалена."
    )


# ============================================================
# ADMIN DELETE PROFILE FROM VIEW
# ============================================================

@dp.callback_query(
    F.data.startswith("admin_delete_profile:")
)
async def admin_delete_profile(
    callback: CallbackQuery,
):
    if not is_admin(callback.from_user.id):
        return

    user_id = int(
        callback.data.split(":")[1]
    )

    profile = await db.get_profile(
        user_id
    )

    if not profile:
        await callback.answer(
            "Анкета не найдена.",
            show_alert=True,
        )
        return

    await db.delete_profile(
        user_id
    )

    await callback.message.answer(
        f"🗑 Анкета пользователя "
        f"{user_id} удалена.",
    )

    try:
        await bot.send_message(
            user_id,
            "⚠️ Твоя анкета была удалена модерацией.",
        )
    except Exception:
        logging.exception(
            "Failed to notify deleted user"
        )

    await callback.answer(
        "Анкета удалена."
    )


# ============================================================
# ADMIN BROADCAST
# ============================================================

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


# ============================================================
# BROADCAST HISTORY
# ============================================================

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
# MAIN
# ============================================================

async def main():
    await db.init()

    await start_web_server()

    logging.info(
        "Starting Telegram bot..."
    )

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    me = await bot.get_me()

    logging.info(
        f"Connected to Telegram: "
        f"@{me.username} id={me.id}"
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
