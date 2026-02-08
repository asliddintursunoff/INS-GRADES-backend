import httpx  # async HTTP client
from app.config import bot_settings
BOT_TOKEN = bot_settings.BOT_TOKEN
API_URL = bot_settings.API_URL

async def send_message(user_telegram_id: str, message: str):
    async with httpx.AsyncClient() as client:
        await client.post(API_URL, json={
            "chat_id": user_telegram_id,
            "text": message,
            "parse_mode": "HTML"
        })
