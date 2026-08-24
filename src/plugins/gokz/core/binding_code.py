import hashlib
import hmac
import time
from typing import Optional, TypedDict


PREFIX = "KZTOP"
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
STEAMID64_BASE = 76561197960265728
RAW_CODE_LENGTH = 16
ENCODED_CODE_LENGTH = 22


class BindingCode(TypedDict):
    steamid64: str
    expires_at: int


def base62_decode(input_text: str) -> bytes:
    """Decode a 22-character KZTOP payload into its 16 raw bytes."""
    if len(input_text) != ENCODED_CODE_LENGTH:
        raise ValueError("Invalid binding-code length")

    number = 0
    for char in input_text:
        digit = ALPHABET.find(char)
        if digit == -1:
            raise ValueError("Invalid binding-code character")
        number = number * len(ALPHABET) + digit

    if number.bit_length() > RAW_CODE_LENGTH * 8:
        raise ValueError("Invalid binding code")

    return number.to_bytes(RAW_CODE_LENGTH, byteorder="big")


def verify_binding_code(code: str, secret: str, *, now: Optional[int] = None) -> BindingCode:
    """Verify a KZTOP binding code and return its SteamID64 and expiry."""
    if not code.startswith(PREFIX):
        raise ValueError("Invalid binding-code prefix")

    raw = base62_decode(code[len(PREFIX):])
    payload = raw[:8]
    signature = raw[8:]
    expected_signature = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).digest()[:8]

    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid binding-code signature")

    account_id = int.from_bytes(payload[:4], byteorder="big", signed=False)
    expires_at = int.from_bytes(payload[4:], byteorder="big", signed=False)
    current_time = int(time.time()) if now is None else now
    if expires_at < current_time:
        raise ValueError("Binding code has expired")

    return {
        "steamid64": str(STEAMID64_BASE + account_id),
        "expires_at": expires_at,
    }
