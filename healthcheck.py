"""Container health reflects both configured adapter connections."""

import json
import os
from pathlib import Path

HEALTH_PATH = Path("/tmp/gokz-bot-health.json")


def healthy() -> bool:
    try:
        platforms = os.getenv("BOT_PLATFORMS", "")
        expected = {p.strip() for p in platforms.split(",") if p.strip()}
        if not expected:
            expected = {
                name
                for name in ("qq", "discord")
                if json.loads(os.getenv(name.upper() + "_BOTS", "[]"))
            }
        connected = set(json.loads(HEALTH_PATH.read_text()))
        return bool(expected) and expected.issubset(connected)
    except (OSError, ValueError, TypeError):
        return False


if __name__ == "__main__":
    raise SystemExit(0 if healthy() else 1)
