import asyncpg

class Database:
    def __init__(self, url):
        self.url = url
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.url,
            min_size=1,
            max_size=10
        )
        await self.create_tables()

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username TEXT,
                    name TEXT,
                    age INTEGER CHECK (age IS NULL OR age >= 13),
                    gender TEXT CHECK (gender IN ('male', 'female')),
                    photo_file_id TEXT,
                    facts TEXT,
                    profile_created BOOLEAN NOT NULL DEFAULT FALSE,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    agreed_to_tos BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # На случай, если таблица users уже существует, безопасно добавляем колонку
            try:
                await conn.execute("""
                    ALTER TABLE users 
                    ADD COLUMN agreed_to_tos BOOLEAN NOT NULL DEFAULT FALSE;
                """)
            except asyncpg.exceptions.DuplicateColumnError:
                pass

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id BIGSERIAL PRIMARY KEY,
                    rater_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    rated_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    score NUMERIC(3,1) NOT NULL CHECK (score >= 1 AND score <= 10),
                    table_type TEXT,
                    advice TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(rater_id, rated_id),
                    CHECK(rater_id <> rated_id)
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS mailings (
                    id BIGSERIAL PRIMARY KEY,
                    admin_id BIGINT NOT NULL,
                    message_type TEXT NOT NULL,
                    message_text TEXT,
                    button_text TEXT,
                    button_url TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ,
                    total INTEGER NOT NULL DEFAULT 0,
                    delivered INTEGER NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id BIGSERIAL PRIMARY KEY,
                    reporter_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    reported_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ratings_rated ON ratings(rated_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active, profile_created)")

    async def upsert_user(self, telegram_id, username):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (telegram_id, username)
                VALUES ($1, $2)
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    is_active = TRUE,
                    updated_at = NOW()
            """, telegram_id, username)

    async def get_user(self, telegram_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)

    async def get_profile(self, telegram_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM users
                WHERE telegram_id = $1 AND profile_created = TRUE AND is_active = TRUE
            """, telegram_id)

    async def save_profile(self, telegram_id, name, age, gender, photo_file_id, facts):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users
                SET name = $2, age = $3, gender = $4, photo_file_id = $5, facts = $6,
                    profile_created = TRUE, is_active = TRUE, updated_at = NOW()
                WHERE telegram_id = $1
            """, telegram_id, name, age, gender, photo_file_id, facts)

    async def update_field(self, telegram_id, field, value):
        allowed = {"name", "age", "gender", "photo_file_id", "facts"}
        if field not in allowed:
            raise ValueError("Invalid field")
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                UPDATE users SET {field} = $2, updated_at = NOW()
                WHERE telegram_id = $1
            """, telegram_id, value)

    async def random_profile(self, current_id):
        async with self.pool.acquire() as conn:
            unrated = await conn.fetchrow("""
                SELECT u.*, FALSE as is_rated
                FROM users u
                WHERE u.profile_created = TRUE 
                  AND u.is_active = TRUE 
                  AND u.telegram_id <> $1
                  AND NOT EXISTS (
                      SELECT 1 FROM ratings r 
                      WHERE r.rater_id = $1 AND r.rated_id = u.telegram_id
                  )
                ORDER BY RANDOM() LIMIT 1
            """, current_id)
            
            if unrated:
                return dict(unrated)
                
            rated = await conn.fetchrow("""
                SELECT u.*, TRUE as is_rated
                FROM users u
                WHERE u.profile_created = TRUE 
                  AND u.is_active = TRUE 
                  AND u.telegram_id <> $1
                ORDER BY RANDOM() LIMIT 1
            """, current_id)

            return dict(rated) if rated else None

    async def add_rating(self, rater_id, rated_id, score):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                INSERT INTO ratings (rater_id, rated_id, score)
                VALUES ($1, $2, $3)
                ON CONFLICT (rater_id, rated_id) 
                DO UPDATE SET 
                    score = EXCLUDED.score,
                    created_at = NOW()
                RETURNING id
            """, rater_id, rated_id, score)

    async def rating_exists(self, rater_id, rated_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM ratings WHERE rater_id = $1 AND rated_id = $2
                )
            """, rater_id, rated_id)

    async def add_table_type(self, rating_id, table_type):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE ratings SET table_type = $2 WHERE id = $1", rating_id, table_type)

    async def add_advice(self, rating_id, advice):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE ratings SET advice = $2 WHERE id = $1", rating_id, advice)

    async def get_scores(self, telegram_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT score FROM ratings WHERE rated_id = $1 ORDER BY created_at", telegram_id)

    async def get_active_users(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT telegram_id FROM users WHERE is_active = TRUE")

    async def deactivate_user(self, telegram_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET is_active = FALSE WHERE telegram_id = $1", telegram_id)

    async def create_mailing(self, admin_id, message_type, message_text, button_text, button_url, total):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                INSERT INTO mailings (admin_id, message_type, message_text, button_text, button_url, total)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, admin_id, message_type, message_text, button_text, button_url, total)

    async def finish_mailing(self, mailing_id, status, delivered, blocked, failed):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE mailings
                SET status = $2, delivered = $3, blocked = $4, failed = $5, finished_at = NOW()
                WHERE id = $1
            """, mailing_id, status, delivered, blocked, failed)

    async def mailing_history(self, limit=10):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM mailings ORDER BY id DESC LIMIT $1", limit)

    # --- Новые методы для обновлений бота ---

    async def agree_to_tos(self, telegram_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET agreed_to_tos = TRUE WHERE telegram_id = $1", telegram_id)

    async def delete_profile(self, telegram_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users 
                SET profile_created = FALSE, name = NULL, age = NULL, gender = NULL, photo_file_id = NULL, facts = NULL
                WHERE telegram_id = $1
            """, telegram_id)
            # Также удаляем связанные оценки пользователя, чтобы не влиять на статистику (по желанию)
            await conn.execute("DELETE FROM ratings WHERE rated_id = $1 OR rater_id = $1", telegram_id)

    async def add_report(self, reporter_id, reported_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO reports (reporter_id, reported_id) VALUES ($1, $2)
            """, reporter_id, reported_id)

