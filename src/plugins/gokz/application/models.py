"""Structured responses; no platform SDK objects cross this boundary."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CommandInput:
    arguments: tuple[str, ...] = ()
    mode: str | None = None
    steamid: str | None = None
    user: str | None = None
    update: bool = False
    overall: int | None = None
    gameplay: int | None = None
    visuals: int | None = None
    comment: str | None = None


@dataclass
class Result:
    title: str
    description: str = ""
    fields: list[tuple[str, str]] = field(default_factory=list)
    image: str | None = None
    file: Path | None = None
    links: list[tuple[str, str]] = field(default_factory=list)
    # Choice labels and full replacement input. Only the requesting user may execute it.
    choices: list[tuple[str, str, CommandInput]] = field(default_factory=list)
    private: bool = False
    tone: str = "neutral"
    category: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)
    footer: str = ""
    record: dict[str, Any] | None = None
    # Unformatted feature data consumed by platform-specific presentation.
    data: dict[str, Any] = field(default_factory=dict)


class UserError(Exception):
    def __init__(self, en: str, zh: str, *, tone: str = "warning"):
        self.tone = tone
        self.en, self.zh = en, zh
        super().__init__(en)
