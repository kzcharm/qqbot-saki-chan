"""Identity boundaries shared by QQ and Discord commands."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RequestContext:
    platform: Literal["qq", "discord"]
    account_id: str
    conversation_id: str | None = None
    permissions: frozenset[str] = frozenset()

    @property
    def locale(self) -> str:
        return "en" if self.platform == "discord" else "zh-CN"

    @property
    def storage_key(self) -> str:
        return f"{self.platform}:{self.account_id}"

    @property
    def is_admin(self) -> bool:
        return "root" in self.permissions
