import httpx
from datetime import datetime, timezone


class DB:
    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def req(self, method, table, params=None, json=None, headers=None):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{self.base}/{table}",
                params=params,
                json=json,
                headers={**self.headers, **(headers or {})},
            )

            response.raise_for_status()

            if not response.content:
                return None

            return response.json()

    async def get_user(self, telegram_id):
        result = await self.req(
            "GET",
            "users",
            {
                "telegram_id": f"eq.{telegram_id}",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def create_user(self, telegram_id, username):
        return await self.req(
            "POST",
            "users",
            json={
                "telegram_id": telegram_id,
                "username": username,
            },
        )

    async def update_user(self, telegram_id, **fields):
        return await self.req(
            "PATCH",
            "users",
            {
                "telegram_id": f"eq.{telegram_id}",
            },
            fields,
        )

    async def get_profile(self, user_id):
        result = await self.req(
            "GET",
            "profiles",
            {
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def upsert_profile(self, user_id, **fields):
        fields["user_id"] = user_id

        return await self.req(
            "POST",
            "profiles",
            json=fields,
            headers={
                "Prefer": "resolution=merge-duplicates"
            },
        )

    async def update_profile(self, user_id, **fields):
        return await self.req(
            "PATCH",
            "profiles",
            {
                "user_id": f"eq.{user_id}",
            },
            fields,
        )

    async def get_public_profile(self, user_id):
        result = await self.req(
            "GET",
            "public_profiles",
            {
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def set_current_target(self, user_id, target_id):
        await self.update_user(
            user_id,
            current_target_id=target_id,
        )

    async def get_current_target(self, user_id):
        user = await self.get_user(user_id)

        if not user:
            return None

        return user.get("current_target_id")

    async def next_unrated(self, user_id):
        result = await self.req(
            "POST",
            "rpc/next_unrated_profile",
            json={
                "p_user_id": user_id
            },
        )

        return result[0] if result else None

    async def next_already_rated(self, user_id):
        result = await self.req(
            "POST",
            "rpc/next_rated_profile",
            json={
                "p_user_id": user_id
            },
        )

        return result[0] if result else None

    async def get_rating(self, rater_id, target_id):
        result = await self.req(
            "GET",
            "ratings",
            {
                "rater_id": f"eq.{rater_id}",
                "profile_user_id": f"eq.{target_id}",
                "limit": "1",
            },
        )

        return result[0] if result else None

    async def upsert_rating(self, rater_id, target_id, score):
        return await self.req(
            "POST",
            "ratings",
            json={
                "rater_id": rater_id,
                "profile_user_id": target_id,
                "score": score,
            },
            headers={
                "Prefer": "resolution=merge-duplicates"
            },
        )

    async def add_advice(self, sender, target, score, text):
        return await self.req(
            "POST",
            "advice",
            json={
                "from_user_id": sender,
                "to_user_id": target,
                "score": score,
                "text": text,
            },
        )

    async def add_report(self, reporter, target, reason, comment):
        result = await self.req(
            "POST",
            "reports",
            json={
                "reporter_id": reporter,
                "profile_user_id": target,
                "reason": reason,
                "comment": comment,
            },
            headers={
                "Prefer": "return=representation"
            },
        )

        return result[0]["id"]

    async def open_reports(self):
        return await self.req(
            "GET",
            "reports",
            {
                "status": "eq.open",
                "order": "created_at.desc",
                "limit": "20",
            },
        )

    async def close_report(self, report_id, admin_id):
        return await self.req(
            "PATCH",
            "reports",
            {
                "id": f"eq.{report_id}",
            },
            {
                "status": "closed",
                "admin_id": admin_id,
                "resolved_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
        )

    async def pending_profiles(self):
        return await self.req(
            "GET",
            "profiles",
            {
                "status": "eq.pending",
                "order": "created_at.asc",
                "limit": "20",
            },
        )

    async def set_profile_status(self, user_id, status):
        return await self.update_profile(
            user_id,
            status=status,
        )

    async def delete_profile(self, user_id):
        return await self.update_profile(
            user_id,
            status="deleted",
            deleted_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

    async def stats(self, user_id):
        result = await self.req(
            "GET",
            "profile_stats",
            {
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )

        if result:
            return result[0]

        return {
            "average": 0,
            "received": 0,
            "given": 0,
            "advice": 0,
        }

    async def all_user_ids(self):
        result = await self.req(
            "GET",
            "users",
            {
                "select": "telegram_id",
                "limit": "100000",
            },
        )

        return [
            row["telegram_id"]
            for row in result
        ]

    async def add_broadcast(
        self,
        admin_id,
        message,
        sent_count,
        failed_count,
    ):
        return await self.req(
            "POST",
            "broadcasts",
            json={
                "admin_id": admin_id,
                "message": message,
                "sent_count": sent_count,
                "failed_count": failed_count,
            },
        )

    async def broadcast_history(self):
        return await self.req(
            "GET",
            "broadcasts",
            {
                "order": "created_at.desc",
                "limit": "20",
            },
        )
