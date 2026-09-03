import os
from datetime import datetime, timezone
from typing import Any

import httpx


class Database:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

        self.client = httpx.AsyncClient(
            timeout=30.0
        )

    # =========================================================
    # COMMON
    # =========================================================

    async def close(self):
        await self.client.aclose()

    async def request(
        self,
        method: str,
        table: str,
        params: dict | None = None,
        json: Any = None,
    ):
        url = f"{self.url}/rest/v1/{table}"

        response = await self.client.request(
            method,
            url,
            headers=self.headers,
            params=params,
            json=json,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Supabase error {response.status_code}: "
                f"{response.text}"
            )

        if not response.text:
            return None

        return response.json()

    async def rpc(
        self,
        function: str,
        json: Any = None,
    ):
        url = f"{self.url}/rest/v1/rpc/{function}"

        response = await self.client.post(
            url,
            headers=self.headers,
            json=json,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Supabase RPC error {response.status_code}: "
                f"{response.text}"
            )

        if not response.text:
            return None

        return response.json()

    # =========================================================
    # USERS
    # =========================================================

    async def get_user(
        self,
        telegram_id: int,
    ):
        result = await self.request(
            "GET",
            "users",
            params={
                "telegram_id": f"eq.{telegram_id}",
                "select": "*",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def create_user(
        self,
        telegram_id: int,
        username: str | None,
    ):
        existing = await self.get_user(
            telegram_id
        )

        if existing:
            return existing

        result = await self.request(
            "POST",
            "users",
            params={
                "select": "*",
            },
            json={
                "telegram_id": telegram_id,
                "username": username,
                "accepted_rules": False,
                "rating_mode": "both",
            },
        )

        return result[0] if result else None

    async def ensure_user(
        self,
        telegram_id: int,
        username: str | None,
    ):
        """
        Возвращает:
            (user, is_new)
        """

        user = await self.get_user(
            telegram_id
        )

        if user:
            if user.get("username") != username:
                await self.update_user(
                    telegram_id,
                    {
                        "username": username,
                    },
                )

                user["username"] = username

            if not user.get("rating_mode"):
                await self.update_user(
                    telegram_id,
                    {
                        "rating_mode": "both",
                    },
                )

                user["rating_mode"] = "both"

            return user, False

        user = await self.create_user(
            telegram_id,
            username,
        )

        return user, True

    async def update_user(
        self,
        telegram_id: int,
        data: dict,
    ):
        return await self.request(
            "PATCH",
            "users",
            params={
                "telegram_id": f"eq.{telegram_id}",
            },
            json=data,
        )

    async def update_user_age(
        self,
        telegram_id: int,
        age: int,
    ):
        return await self.update_user(
            telegram_id,
            {
                "age": age,
            },
        )

    async def update_user_gender(
        self,
        telegram_id: int,
        gender: str,
    ):
        return await self.update_user(
            telegram_id,
            {
                "gender": gender,
            },
        )

    async def update_rating_mode(
        self,
        telegram_id: int,
        mode: str,
    ):
        if mode not in (
            "score",
            "table",
            "both",
        ):
            raise ValueError(
                "Invalid rating mode"
            )

        return await self.update_user(
            telegram_id,
            {
                "rating_mode": mode,
            },
        )

    async def get_rating_mode(
        self,
        telegram_id: int,
    ):
        user = await self.get_user(
            telegram_id
        )

        if not user:
            return "both"

        mode = user.get(
            "rating_mode"
        )

        if mode not in (
            "score",
            "table",
            "both",
        ):
            return "both"

        return mode

    async def get_all_users(self):
        return await self.request(
            "GET",
            "users",
            params={
                "select": "telegram_id",
            },
        ) or []

    async def get_user_count(self):
        result = await self.rpc(
            "get_user_count"
        )

        return int(result or 0)

    # =========================================================
    # PROFILES
    # =========================================================

    async def get_profile(
        self,
        telegram_id: int,
    ):
        result = await self.request(
            "GET",
            "profiles",
            params={
                "user_id": f"eq.{telegram_id}",
                "select": "*",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def create_profile(
        self,
        telegram_id: int,
        photo_id: str,
        facts: str | None = None,
        height: float | None = None,
        weight: float | None = None,
        photo_ids: list[str] | None = None,
    ):
        existing = await self.get_profile(
            telegram_id
        )

        if not photo_ids:
            photo_ids = [photo_id]

        profile_data = {
            "photo_id": photo_ids[0],
            "photo_ids": photo_ids,
            "facts": facts,
            "height": height,
            "weight": weight,
            "status": "active",
            "deleted_at": None,
        }

        if existing:
            return await self.update_profile(
                telegram_id,
                profile_data,
            )

        result = await self.request(
            "POST",
            "profiles",
            params={
                "select": "*",
            },
            json={
                "user_id": telegram_id,
                **profile_data,
            },
        )

        return result[0] if result else None

    async def update_profile(
        self,
        telegram_id: int,
        data: dict,
    ):
        return await self.request(
            "PATCH",
            "profiles",
            params={
                "user_id": f"eq.{telegram_id}",
            },
            json=data,
        )

    async def update_profile_photos(
        self,
        telegram_id: int,
        photo_ids: list[str],
    ):
        if not photo_ids:
            return None

        return await self.update_profile(
            telegram_id,
            {
                "photo_id": photo_ids[0],
                "photo_ids": photo_ids,
            },
        )

    async def get_profile_photos(
        self,
        telegram_id: int,
    ):
        profile = await self.get_profile(
            telegram_id
        )

        if not profile:
            return []

        photo_ids = profile.get(
            "photo_ids"
        )

        if isinstance(photo_ids, list) and photo_ids:
            return photo_ids

        photo_id = profile.get(
            "photo_id"
        )

        if photo_id:
            return [photo_id]

        return []

    async def delete_profile(
        self,
        telegram_id: int,
    ):
        # Удаляем связи лайков с удаляемой анкетой.
        await self.request(
            "DELETE",
            "likes",
            params={
                "or": (
                    f"(from_user_id.eq.{telegram_id},"
                    f"to_user_id.eq.{telegram_id})"
                ),
            },
        )

        return await self.update_profile(
            telegram_id,
            {
                "status": "deleted",
                "deleted_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
        )

    async def restore_profile(
        self,
        telegram_id: int,
    ):
        return await self.update_profile(
            telegram_id,
            {
                "status": "active",
                "deleted_at": None,
            },
        )

    async def get_active_profile_count(self):
        result = await self.rpc(
            "get_active_profile_count"
        )

        return int(result or 0)

    async def get_profile_count(self):
        result = await self.request(
            "GET",
            "profiles",
            params={
                "select": "user_id",
            },
        )

        return len(result or [])

    # =========================================================
    # RATING PROFILES
    # =========================================================

    async def get_random_unrated_profile(
        self,
        rater_id: int,
        exclude_ids: list[int] | None = None,
    ):
        profiles = await self.request(
            "GET",
            "profiles",
            params={
                "user_id": f"neq.{rater_id}",
                "status": "eq.active",
                "select": "*",
            },
        ) or []

        if not profiles:
            return None

        exclude_ids = set(
            exclude_ids or []
        )

        ratings = await self.request(
            "GET",
            "ratings",
            params={
                "rater_id": f"eq.{rater_id}",
                "select": "profile_user_id",
            },
        ) or []

        rated_ids = {
            row["profile_user_id"]
            for row in ratings
            if row.get(
                "profile_user_id"
            ) is not None
        }

        candidates = [
            profile
            for profile in profiles
            if profile.get("user_id")
            not in exclude_ids
            and profile.get("user_id")
            not in rated_ids
        ]

        if not candidates:
            return None

        import random

        return random.choice(
            candidates
        )

    async def get_random_rated_profile(
        self,
        rater_id: int,
        exclude_ids: list[int] | None = None,
    ):
        ratings = await self.request(
            "GET",
            "ratings",
            params={
                "rater_id": f"eq.{rater_id}",
                "select": (
                    "profile_user_id,"
                    "score,look_type"
                ),
            },
        ) or []

        if not ratings:
            return None

        exclude_ids = set(
            exclude_ids or []
        )

        import random

        random.shuffle(ratings)

        for rating in ratings:
            profile_user_id = rating.get(
                "profile_user_id"
            )

            if profile_user_id in exclude_ids:
                continue

            if profile_user_id == rater_id:
                continue

            profile = await self.get_profile(
                profile_user_id
            )

            if (
                profile
                and profile.get("status")
                == "active"
            ):
                return profile

        return None

    # =========================================================
    # RATINGS
    # =========================================================

    async def get_rating(
        self,
        rater_id: int,
        profile_user_id: int,
    ):
        if rater_id == profile_user_id:
            return None

        result = await self.request(
            "GET",
            "ratings",
            params={
                "rater_id": f"eq.{rater_id}",
                "profile_user_id": (
                    f"eq.{profile_user_id}"
                ),
                "select": "*",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def save_rating(
        self,
        rater_id: int,
        profile_user_id: int,
        score: float,
        look_type: str | None = None,
    ):
        if rater_id == profile_user_id:
            raise ValueError(
                "User cannot rate themselves"
            )

        if not 1 <= float(score) <= 10:
            raise ValueError(
                "Score must be between 1 and 10"
            )

        existing = await self.get_rating(
            rater_id,
            profile_user_id,
        )

        data = {
            "score": float(score),
            "look_type": look_type,
        }

        if existing:
            return await self.request(
                "PATCH",
                "ratings",
                params={
                    "rater_id": f"eq.{rater_id}",
                    "profile_user_id": (
                        f"eq.{profile_user_id}"
                    ),
                },
                json=data,
            )

        return await self.request(
            "POST",
            "ratings",
            params={
                "select": "*",
            },
            json={
                "rater_id": rater_id,
                "profile_user_id": profile_user_id,
                **data,
            },
        )

    async def get_average_rating(
        self,
        profile_user_id: int,
    ):
        result = await self.request(
            "GET",
            "ratings",
            params={
                "profile_user_id": (
                    f"eq.{profile_user_id}"
                ),
                "select": "score",
            },
        )

        if not result:
            return 0.0

        scores = []

        for row in result:
            try:
                scores.append(
                    float(row["score"])
                )
            except (
                TypeError,
                ValueError,
                KeyError,
            ):
                continue

        if not scores:
            return 0.0

        return round(
            sum(scores) / len(scores),
            1,
        )

    async def get_rating_count(
        self,
        profile_user_id: int,
    ):
        result = await self.request(
            "GET",
            "ratings",
            params={
                "profile_user_id": (
                    f"eq.{profile_user_id}"
                ),
                "select": "id",
            },
        )

        return len(result or [])

    # =========================================================
    # LIKES
    # =========================================================

    async def get_like(
        self,
        from_user_id: int,
        to_user_id: int,
    ):
        if from_user_id == to_user_id:
            return None

        result = await self.request(
            "GET",
            "likes",
            params={
                "from_user_id": (
                    f"eq.{from_user_id}"
                ),
                "to_user_id": (
                    f"eq.{to_user_id}"
                ),
                "select": "*",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def create_like(
        self,
        from_user_id: int,
        to_user_id: int,
    ):
        if from_user_id == to_user_id:
            return None

        existing = await self.get_like(
            from_user_id,
            to_user_id,
        )

        if existing:
            return existing

        try:
            result = await self.request(
                "POST",
                "likes",
                params={
                    "select": "*",
                },
                json={
                    "from_user_id": from_user_id,
                    "to_user_id": to_user_id,
                },
            )

            return (
                result[0]
                if result
                else None
            )

        except RuntimeError as exc:
            # Защита от гонки при unique constraint.
            if "duplicate" in str(
                exc
            ).lower():
                return await self.get_like(
                    from_user_id,
                    to_user_id,
                )
            raise

    async def has_mutual_like(
        self,
        user_a: int,
        user_b: int,
    ):
        first = await self.get_like(
            user_a,
            user_b,
        )

        if not first:
            return False

        second = await self.get_like(
            user_b,
            user_a,
        )

        return second is not None

    async def get_likes_received(
        self,
        user_id: int,
    ):
        return await self.request(
            "GET",
            "likes",
            params={
                "to_user_id": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        ) or []

    # =========================================================
    # ADVICE
    # =========================================================

    async def create_advice(
        self,
        from_user_id: int,
        to_user_id: int,
        text: str,
        score: float | None = None,
    ):
        if from_user_id == to_user_id:
            return None

        return await self.request(
            "POST",
            "advice",
            params={
                "select": "*",
            },
            json={
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "text": text,
                "score": score,
            },
        )

    # =========================================================
    # REPORTS
    # =========================================================

    async def create_report(
        self,
        reporter_id: int,
        profile_user_id: int,
        reason: str,
    ):
        if reporter_id == profile_user_id:
            return None

        result = await self.request(
            "POST",
            "reports",
            params={
                "select": "*",
            },
            json={
                "reporter_id": reporter_id,
                "profile_user_id": profile_user_id,
                "reason": reason,
                "status": "open",
            },
        )

        return result[0] if result else None

    async def get_reports(self):
        return await self.request(
            "GET",
            "reports",
            params={
                "select": "*",
                "order": "id.desc",
                "limit": "100",
            },
        ) or []

    async def get_report(
        self,
        report_id: int,
    ):
        result = await self.request(
            "GET",
            "reports",
            params={
                "id": f"eq.{report_id}",
                "select": "*",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def close_report(
        self,
        report_id: int,
    ):
        return await self.request(
            "PATCH",
            "reports",
            params={
                "id": f"eq.{report_id}",
            },
            json={
                "status": "closed",
            },
        )

    async def resolve_report(
        self,
        report_id: int,
    ):
        return await self.request(
            "PATCH",
            "reports",
            params={
                "id": f"eq.{report_id}",
            },
            json={
                "status": "resolved",
            },
        )

    # Оставляем метод для совместимости,
    # но новый bot.py использует close_report().
    async def delete_report(
        self,
        report_id: int,
    ):
        return await self.close_report(
            report_id
        )

    # =========================================================
    # BROADCAST
    # =========================================================

    async def create_broadcast(
        self,
        admin_id: int,
        message: str,
        sent_count: int,
        failed_count: int,
    ):
        return await self.request(
            "POST",
            "broadcasts",
            params={
                "select": "*",
            },
            json={
                "admin_id": admin_id,
                "message": message,
                "sent_count": sent_count,
                "failed_count": failed_count,
            },
        )

    async def get_broadcasts(self):
        return await self.request(
            "GET",
            "broadcasts",
            params={
                "select": "*",
                "order": "id.desc",
                "limit": "100",
            },
        ) or []

    # =========================================================
    # ADMIN SETTINGS
    # =========================================================

    async def new_user_notifications_enabled(
        self,
    ):
        result = await self.rpc(
            "get_new_user_notifications"
        )

        return bool(result)

    async def set_new_user_notifications(
        self,
        enabled: bool,
    ):
        return await self.rpc(
            "set_new_user_notifications",
            {
                "enabled": bool(enabled),
            },
        )

    # =========================================================
    # ADMIN STATS
    # =========================================================

    async def get_admin_stats(self):
        result = await self.rpc(
            "get_admin_stats"
        )

        return result or {
            "users": 0,
            "active_profiles": 0,
            "pending_profiles": 0,
            "deleted_profiles": 0,
            "ratings": 0,
            "likes": 0,
            "advice": 0,
            "open_reports": 0,
        }
