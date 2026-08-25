import os


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DATABASE_URL = os.getenv("DATABASE_URL")

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).rstrip("/")

WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    ""
)

PORT = int(
    os.getenv("PORT", "10000")
)


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set"
    )

if not ADMIN_ID:
    raise RuntimeError(
        "ADMIN_ID is not set"
    )

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set"
    )

if not RENDER_EXTERNAL_URL:
    raise RuntimeError(
        "RENDER_EXTERNAL_URL is not set"
    )
