from typing import Literal

Game = Literal["gokz", "cs2kz"]


def format_game(game: str) -> Game:
    game = str(game).strip().lower()
    if game in {"g", "gokz", "csgo", "csgo-kz"}:
        return "gokz"
    if game in {"2", "cs2", "cs2kz"}:
        return "cs2kz"
    raise ValueError("Invalid game")


def toggle_game(game: str) -> Game:
    return "cs2kz" if format_game(game) == "gokz" else "gokz"


def format_cs2kz_mode(mode: str) -> str:
    mode = str(mode).strip().lower()
    mode_mapping = {
        "c": "classic",
        "ckz": "classic",
        "classic": "classic",
        "s": "classic",
        "skz": "classic",
        "k": "classic",
        "kzt": "classic",
        "kz_timer": "classic",
        "kz_simple": "classic",
        "v": "vanilla",
        "vnl": "vanilla",
        "vanilla": "vanilla",
        "kz_vanilla": "vanilla",
    }
    if mode not in mode_mapping:
        raise ValueError("Invalid CS2KZ mode")
    return mode_mapping[mode]


def format_cs2kz_mode_label(mode: str) -> str:
    return "VNL" if format_cs2kz_mode(mode) == "vanilla" else "CKZ"
