import os
import json
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

    # =========================
    # USERS
    # =========================

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
                "select": "*",
            },
            json=data,
        )

    # =========================
    # PROFILES
    # =========================

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
    ):
        result = await self.request(
            "POST",
            "profiles",
            params={"select": "*"},
            json={
                "user_id": telegram_id,
                "photo_id": photo_id,
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
                "select": "*",
            },
            json=data,
        )

    async def delete_profile(self, telegram_id: int):
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

    # =========================
    # MULTIPLE PHOTOS
    # =========================

    @staticmethod
    def parse_photo_ids(photo_id):
        if not photo_id:
            return []

        if isinstance(photo_id, list):
            return [
                str(x)
                for x in photo_id
                if x
            ]

        if not isinstance(photo_id, str):
            return [str(photo_id)]

        value = photo_id.strip()

        if not value:
            return []

        if value.startswith("["):
            try:
                parsed = json.loads(value)

                if isinstance(parsed, list):
                    return [
                        str(x)
                        for x in parsed
                        if x
                    ]
            except json.JSONDecodeError:
                pass

        return [value]

    async def get_profile_photos(
        self,
        telegram_id: int,
    ):
        profile = await self.get_profile(
            telegram_id
        )

        if not profile:
            return []

        return self.parse_photo_ids(
            profile.get("photo_id")
        )

    async def set_profile_photos(
        self,
        telegram_id: int,
        photo_ids: list[str],
    ):
        photo_ids = [
            str(x)
            for x in photo_ids
            if x
        ]

        if not photo_ids:
            return None

        if len(photo_ids) == 1:
            value = photo_ids[0]
        else:
            value = json.dumps(
                photo_ids,
                ensure_ascii=False,
            )

        return await self.update_profile(
            telegram_id,
            {
                "photo_id": value,
            },
        )

    # =========================
    # RATINGS
    # =========================

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

    async def create_rating(
        self,
        rater_id: int,
        profile_user_id: int,
        score: float,
    ):
        existing = await self.get_rating(
            rater_id,
            profile_user_id,
        )

        if existing:
            return await self.request(
                "PATCH",
                "ratings",
                params={
                    "rater_id": f"eq.{rater_id}",
                    "profile_user_id": f"eq.{profile_user_id}",
                    "select": "*",
                },
                json={
                    "score": score,
                    "updated_at": "now()",
                },
            )

        return await self.request(
            "POST",
            "ratings",
            params={"select": "*"},
            json={
                "rater_id": rater_id,
                "profile_user_id": profile_user_id,
                "score": score,
            },
        )

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

        data = {
            "score": float(score),
        }

        if look_type is not None:
            data["look_type"] = look_type

        if existing:
            data["updated_at"] = "now()"

            return await self.request(
                "PATCH",
                "ratings",
                params={
                    "rater_id": f"eq.{rater_id}",
                    "profile_user_id": f"eq.{profile_user_id}",
                    "select": "*",
                },
                json=data,
            )

        data.update(
            {
                "rater_id": rater_id,
                "profile_user_id": profile_user_id,
            }
        )

        return await self.request(
            "POST",
            "ratings",
            params={"select": "*"},
            json=data,
        )

    async def get_average_rating(
        self,
        telegram_id: int,
    ):
        result = await self.request(
            "GET",
            "ratings",
            params={
                "profile_user_id": f"eq.{telegram_id}",
                "select": "score",
            },
        )

        if not result:
            return 0.0

        scores = [
            float(row["score"])
            for row in result
            if row.get("score") is not None
        ]

        if not scores:
            return 0.0

        return round(
            sum(scores) / len(scores),
            1,
        )

    async def get_received_ratings_count(
        self,
        telegram_id: int,
    ):
        result = await self.request(
            "GET",
            "ratings",
            params={
                "profile_user_id": f"eq.{telegram_id}",
                "select": "id",
            },
        )

        return len(result or [])

    async def get_rating_count(
        self,
        telegram_id: int,
    ):
        return await self.get_received_ratings_count(
            telegram_id
        )

    # =========================
    # FIND PROFILE
    # =========================

    async def next_unrated_profile(
        self,
        telegram_id: int,
    ):
        result = await self.request(
            "GET",
            "public_profiles",
            params={
                "select": "*",
                "user_id": f"neq.{telegram_id}",
                "order": "random",
                "limit": "50",
            },
        )

        for profile in result or []:
            rating = await self.get_rating(
                telegram_id,
                profile["user_id"],
            )

            if not rating:
                return profile

        return None

    async def next_rated_profile(
        self,
        telegram_id: int,
    ):
        ratings = await self.request(
            "GET",
            "ratings",
            params={
                "rater_id": f"eq.{telegram_id}",
                "select": "profile_user_id,score",
                "order": "updated_at.desc",
            },
        )

        if not ratings:
            return None

        for rating in ratings:
            profile = await self.request(
                "GET",
                "public_profiles",
                params={
                    "user_id": f"eq.{rating['profile_user_id']}",
                    "select": "*",
                    "limit": "1",
                },
            )

            if profile:
                return profile[0]

        return None

    async def get_random_unrated_profile(
        self,
        telegram_id: int,
    ):
        return await self.next_unrated_profile(
            telegram_id
        )

    async def get_random_rated_profile(
        self,
        telegram_id: int,
    ):
        return await self.next_rated_profile(
            telegram_id
        )

    # =========================
    # ADVICE
    # =========================

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

    # =========================
    # REPORTS
    # =========================

    async def create_report(
        self,
        reporter_id: int,
        profile_user_id: int,
        reason: str,
        comment: str | None = None,
    ):
        return await self.request(
            "POST",
            "reports",
            params={"select": "*"},
            json={
                "reporter_id": reporter_id,
                "profile_user_id": profile_user_id,
                "reason": reason,
                "comment": comment,
            },
        )

    async def get_reports(self):
        return await self.request(
            "GET",
            "reports",
            params={
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

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
        admin_id: int,
    ):
        return await self.request(
            "PATCH",
            "reports",
            params={
                "id": f"eq.{report_id}",
            },
            json={
                "status": "closed",
                "admin_id": admin_id,
                "resolved_at": "now()",
            },
        )

    # =========================
    # BROADCASTS
    # =========================

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
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    # =========================
    # ALL USERS
    # =========================

    async def get_all_users(self):
        return await self.request(
            "GET",
            "users",
            params={
                "select": "telegram_id",
            },
        )
