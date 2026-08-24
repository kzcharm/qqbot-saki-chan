import hashlib
import hmac
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "binding_code", ROOT / "src/plugins/gokz/core/binding_code.py"
)
binding_code = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binding_code)


def encode_base62(raw: bytes) -> str:
    number = int.from_bytes(raw, byteorder="big")
    chars = []
    while number:
        number, digit = divmod(number, len(binding_code.ALPHABET))
        chars.append(binding_code.ALPHABET[digit])
    return "".join(reversed(chars or ["0"])).zfill(binding_code.ENCODED_CODE_LENGTH)


def make_code(account_id: int, expires_at: int, secret: str) -> str:
    payload = account_id.to_bytes(4, "big") + expires_at.to_bytes(4, "big")
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()[:8]
    return binding_code.PREFIX + encode_base62(payload + signature)


class BindingCodeTest(unittest.TestCase):
    secret = "test shared secret"
    account_id = 987654321
    expires_at = 2_000_000_000

    def test_verifies_valid_code_and_returns_steamid64(self):
        code = make_code(self.account_id, self.expires_at, self.secret)

        result = binding_code.verify_binding_code(code, self.secret, now=self.expires_at)

        self.assertEqual(result["steamid64"], str(binding_code.STEAMID64_BASE + self.account_id))
        self.assertEqual(result["expires_at"], self.expires_at)

    def test_rejects_invalid_prefix_length_and_characters(self):
        code = make_code(self.account_id, self.expires_at, self.secret)
        invalid_codes = (
            "kztop" + code[len(binding_code.PREFIX):],
            code[:-1],
            binding_code.PREFIX + ("!" * binding_code.ENCODED_CODE_LENGTH),
            binding_code.PREFIX + ("z" * binding_code.ENCODED_CODE_LENGTH),
        )

        for invalid_code in invalid_codes:
            with self.subTest(code=invalid_code):
                with self.assertRaises(ValueError):
                    binding_code.verify_binding_code(invalid_code, self.secret, now=0)

    def test_rejects_tampering_wrong_secret_and_expired_code(self):
        code = make_code(self.account_id, self.expires_at, self.secret)
        tampered = code[:-1] + ("0" if code[-1] != "0" else "1")

        for invalid_code, secret, now in (
            (tampered, self.secret, 0),
            (code, "different secret", 0),
            (code, self.secret, self.expires_at + 1),
        ):
            with self.subTest(code=invalid_code, secret=secret, now=now):
                with self.assertRaises(ValueError):
                    binding_code.verify_binding_code(invalid_code, secret, now=now)


if __name__ == "__main__":
    unittest.main()
