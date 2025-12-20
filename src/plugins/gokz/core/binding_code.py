import hmac
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict

# Base36 character set (0-9, A-Z)
BASE36_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def base36_to_int(s: str) -> int:
    """Convert base36 string to integer."""
    num = 0
    for char in s.upper():
        if char not in BASE36_CHARS:
            raise ValueError(f"Invalid base36 character: {char}")
        num = num * 36 + BASE36_CHARS.index(char)
    return num


def int_to_base36(num: int) -> str:
    """Convert integer to base36 string."""
    if num == 0:
        return "0"
    result = []
    while num > 0:
        result.append(BASE36_CHARS[num % 36])
        num //= 36
    return "".join(reversed(result))


def decode_binding_code(code: str, secret: str) -> Optional[Dict[str, any]]:
    """
    Decode and validate a 32-character binding code.

    Args:
        code: The 32-character binding code from the user
        secret: The shared secret (same as qq_bot_secret in database settings)

    Returns:
        Dict with 'steamid64' (str) and 'exp' (datetime) if valid, None if invalid/expired
    """
    if len(code) != 32:
        return None

    try:
        # Split: [steamid64:11][exp_minutes:5][signature:16]
        steamid64_encoded = code[:11]
        expire_encoded = code[11:16]
        signature_encoded = code[16:32]

        # Verify HMAC signature
        message = f"{steamid64_encoded}:{expire_encoded}"
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).digest()

        expected_signature_int = int.from_bytes(expected_signature[:8], byteorder="big")
        expected_signature_encoded = int_to_base36(expected_signature_int).zfill(16)

        if signature_encoded != expected_signature_encoded:
            return None  # Invalid signature

        # Decode steamid64
        steamid64 = str(base36_to_int(steamid64_encoded))

        # Decode expiration
        expire_minutes = base36_to_int(expire_encoded)
        expire_datetime = datetime.fromtimestamp(expire_minutes * 60, tz=timezone.utc)

        # Check expiration
        if datetime.now(timezone.utc) > expire_datetime:
            return None  # Expired

        return {
            "steamid64": steamid64,
            "exp": expire_datetime,
        }
    except (ValueError, IndexError, OverflowError):
        return None

