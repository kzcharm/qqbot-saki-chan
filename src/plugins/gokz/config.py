import os

from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
GOKZ_TOP_API_KEY = os.getenv("GOKZ_TOP_API_KEY", "")
UPTIME_KUMA_API_KEY = os.getenv("UPTIME_KUMA_API_KEY", "")
# Shared with gokz.top to verify signed, short-lived binding codes. The
# lowercase name remains as a deployment-migration fallback.
QQ_BOT_SECRET = os.getenv("QQ_BOT_SECRET") or os.getenv("qq_bot_secret", "")


class Config(BaseModel):
    """Plugin Config Here"""
    steam_api_key: str = STEAM_API_KEY
    uptime_kuma_api_key: str = UPTIME_KUMA_API_KEY
