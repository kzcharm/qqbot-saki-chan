import os

from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
QQ_BOT_SECRET = os.getenv("qq_bot_secret", "")
ENABLE_DIRECT_STEAM_BINDING = os.getenv("enable_direct_steam_binding", "").lower() in ("true", "1", "yes")


class Config(BaseModel):
    """Plugin Config Here"""
    steam_api_key: str = STEAM_API_KEY
