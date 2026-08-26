import os
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

    async def request(
        self,
        method: str,
        table: str,
        params=None,
        json=None,
    ):
        url = f"{self.url}/rest/v1/{table}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
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

    # =========================================================
    # USERS
    # =========================================================

    async def get_user(self, telegram_id: int):
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
        result = await self.request(
            "POST",
            "users",
            params={"select": "*"},
            json={
                "telegram_id": telegram_id,
                "username": username,
            },
        )

        return result[0] if result else None

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
            {"age": age},
        )

    async def update_user_gender(
        self,
        telegram_id: int,
        gender: str,
    ):
        return await self.update_user(
            telegram_id,
            {"gender": gender},
        )

    async def get_all_users(self):
        return await self.request(
            "GET",
            "users",
            params={
                "select": "telegram_id",
            },
        )

    # =========================================================
    # PROFILES
    # =========================================================

    async def get_profile(self, telegram_id: int):
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
        if not photo_ids:
            photo_ids = [photo_id]

        result = await self.request(
            "POST",
            "profiles",
            params={"select": "*"},
            json={
                "user_id": telegram_id,
                "photo_id": photo_ids[0],
                "photo_ids": photo_ids,
                "facts": facts,
                "height": height,
                "weight": weight,
                "status": "active",
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

        photo_ids = profile.get("photo_ids")

        if photo_ids:
            return photo_ids

        photo_id = profile.get("photo_id")

        if photo_id:
            return [photo_id]

        return []

    async def delete_profile(
        self,
        telegram_id: int,
    ):
        return await self.request(
            "PATCH",
            "profiles",
            params={
                "user_id": f"eq.{telegram_id}",
            },
            json={
                "status": "deleted",
                "deleted_at": "now()",
            },
        )

    async def restore_profile(
        self,
        telegram_id: int,
    ):
        return await self.request(
            "PATCH",
            "profiles",
            params={
                "user_id": f"eq.{telegram_id}",
            },
            json={
                "status": "active",
                "deleted_at": None,
            },
        )

    # =========================================================
    # RATING PROFILES
    # =========================================================

    async def get_random_unrated_profile(
        self,
        rater_id: int,
    ):
        profiles = await self.request(
            "GET",
            "profiles",
            params={
                "user_id": f"neq.{rater_id}",
                "status": "eq.active",
                "select": "*",
                "limit": "100",
            },
        )

        if not profiles:
            return None

        for profile in profiles:
            profile_user_id = profile["user_id"]

            existing = await self.get_rating(
                rater_id,
                profile_user_id,
            )

            if existing is None:
                return profile

        return None

    async def get_random_rated_profile(
        self,
        rater_id: int,
    ):
        ratings = await self.request(
            "GET",
            "ratings",
            params={
                "rater_id": f"eq.{rater_id}",
                "select": "profile_user_id,score,look_type",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

        if not ratings:
            return None

        for rating in ratings:
            profile = await self.get_profile(
                rating["profile_user_id"]
            )

            if profile and profile.get("status") == "active":
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
        result = await self.request(
            "GET",
            "ratings",
            params={
                "rater_id": f"eq.{rater_id}",
                "profile_user_id": f"eq.{profile_user_id}",
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
        existing = await self.get_rating(
            rater_id,
            profile_user_id,
        )

        if existing:
            data = {
                "score": score,
                "updated_at": "now()",
            }

            if look_type is not None:
                data["look_type"] = look_type

            return await self.request(
                "PATCH",
                "ratings",
                params={
                    "rater_id": f"eq.{rater_id}",
                    "profile_user_id": f"eq.{profile_user_id}",
                },
                json=data,
            )

        return await self.request(
            "POST",
            "ratings",
            params={"select": "*"},
            json={
                "rater_id": rater_id,
                "profile_user_id": profile_user_id,
                "score": score,
                "look_type": look_type,
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
                "profile_user_id": f"eq.{profile_user_id}",
                "select": "score",
            },
        )

        if not result:
            return 0.0

        scores = []

        for row in result:
            try:
                scores.append(float(row["score"]))
            except (TypeError, ValueError):
                pass

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
                "profile_user_id": f"eq.{profile_user_id}",
                "select": "id",
            },
        )

        return len(result or [])

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
        return await self.request(
            "POST",
            "advice",
            params={"select": "*"},
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
        return await self.request(
            "POST",
            "reports",
            params={"select": "*"},
            json={
                "reporter_id": reporter_id,
                "profile_user_id": profile_user_id,
                "reason": reason,
            },
        )

    async def get_reports(self):
        return await self.request(
            "GET",
            "reports",
            params={
                "select": "*",
                "order": "id.desc",
                "limit": "100",
            },
        )

    async def get_report(self, report_id: int):
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
            params={"select": "*"},
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
        )
