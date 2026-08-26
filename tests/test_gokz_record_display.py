import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_display_helpers():
    source = (ROOT / "src/plugins/gokz/plugins/kzglobal.py").read_text(encoding="utf-8")
    functions = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "gokz_record_mode_label",
            "gokz_record_rating_line",
            "gokz_record_tier",
        }
    ]
    def format_kzmode(mode, _):
        modes = {
            "kz_timer": "kzt",
            "kzt": "kzt",
            "kz_simple": "skz",
            "skz": "skz",
            "kz_vanilla": "vnl",
            "vnl": "vnl",
            "ovr": "ovr",
        }
        if str(mode).lower() not in modes:
            raise ValueError("invalid mode")
        return modes[str(mode).lower()]

    namespace = {"format_kzmode": format_kzmode, "MAP_TIERS": {"kz_cached": 3}}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "kzglobal.py", "exec"), namespace)
    return namespace


HELPERS = load_display_helpers()


class TestGOKZRecordDisplay(unittest.TestCase):
    def test_pr_mode_uses_the_returned_concrete_mode(self):
        self.assertEqual(
            HELPERS["gokz_record_mode_label"]({"mode": "kz_vanilla"}, "OVR"),
            "VNL",
        )

    def test_pr_mode_falls_back_to_the_query_scope_when_missing(self):
        self.assertEqual(
            HELPERS["gokz_record_mode_label"]({}, "KZT"),
            "KZT",
        )

    def test_pb_rating_is_rendered_only_when_the_response_includes_it(self):
        render = HELPERS["gokz_record_rating_line"]

        self.assertEqual(render({"rating": 7.5}), "║ Rating:　7.5")
        self.assertEqual(render({}), "")
        self.assertEqual(render({"rating": None}), "")

    def test_v1_record_tier_is_preserved_for_compliment_eligibility(self):
        tier = HELPERS["gokz_record_tier"]

        self.assertEqual(tier({"map_name": "kz_cached", "map_tier": 6}), 6)
        self.assertEqual(tier({"map_name": "kz_cached"}), 3)


if __name__ == "__main__":
    unittest.main()
