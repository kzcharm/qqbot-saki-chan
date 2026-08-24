import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]


def package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


def load_compliment_module():
    package("src", ROOT / "src")
    package("src.plugins", ROOT / "src/plugins")
    package("src.plugins.gokz", ROOT / "src/plugins/gokz")
    package("src.plugins.gokz.api", ROOT / "src/plugins/gokz/api")
    package("src.plugins.gokz.core", ROOT / "src/plugins/gokz/core")
    package("src.plugins.gokz.db", ROOT / "src/plugins/gokz/db")

    helper = types.ModuleType("src.plugins.gokz.api.helper")
    helper.fetch_json = None
    sys.modules[helper.__name__] = helper
    config = types.ModuleType("src.plugins.gokz.config")
    config.DEEPSEEK_API_BASE = "https://api.deepseek.com"
    config.DEEPSEEK_API_KEY = ""
    config.DEEPSEEK_MODEL = "deepseek-v4-flash"
    config.FISH_AUDIO_API_KEY = ""
    config.FISH_AUDIO_REFERENCE_ID = ""
    sys.modules[config.__name__] = config
    formatter = types.ModuleType("src.plugins.gokz.core.formatter")
    formatter.format_gruntime = lambda seconds: str(seconds)
    sys.modules[formatter.__name__] = formatter
    db = types.ModuleType("src.plugins.gokz.db.db")
    db.engine = object()
    sys.modules[db.__name__] = db
    models = types.ModuleType("src.plugins.gokz.db.models")
    models.ComplimentedRun = object
    sys.modules[models.__name__] = models

    spec = importlib.util.spec_from_file_location(
        "src.plugins.gokz.core.pr_compliment",
        ROOT / "src/plugins/gokz/core/pr_compliment.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compliment = load_compliment_module()


RECORD = {
    "id": 42,
    "map_id": 8,
    "map_name": "kz_memento",
    "map_tier": 6,
    "mode": "KZT",
    "player_name": "Runner",
    "time": 86.891,
    "teleports": 0,
    "points": 826,
    "stage": 0,
}


class TestSpeechSanitizing(unittest.TestCase):
    def test_keeps_safe_tags_and_japanese_desuwa_at_a_sentence_end(self):
        text = compliment.sanitize_speech(
            "[proud] 一路到底还能跑得这么稳，确实挺像样，ですわ。",
            allow_desuwa=True,
        )
        self.assertEqual(text, "[proud] 一路到底还能跑得这么稳，确实挺像样，ですわ。")

        two_sentences = compliment.sanitize_speech(
            "这次跑得很漂亮，ですわ。下一把也继续保持。",
            allow_desuwa=True,
        )
        self.assertEqual(two_sentences, "这次跑得很漂亮，ですわ。下一把也继续保持。")

    def test_removes_desuwa_when_the_program_did_not_allow_it(self):
        text = compliment.sanitize_speech("这次确实跑得不错，ですわ。", allow_desuwa=False)
        self.assertEqual(text, "这次确实跑得不错。")

    def test_cleans_unsupported_tags_and_tts_hostile_punctuation(self):
        self.assertEqual(compliment.sanitize_speech("[angry] 这次太强了。", allow_desuwa=False), "这次太强了。")
        self.assertEqual(compliment.sanitize_speech("这次太强了——确实如此。", allow_desuwa=False), "这次太强了，确实如此。")

    def test_keeps_speakable_text_when_markdown_artifacts_remain(self):
        text = compliment.sanitize_speech(
            "**这次*跑得<不错>*，【值得认可】。**", allow_desuwa=False
        )
        self.assertEqual(text, "这次跑得不错，值得认可。")

    def test_japanese_mode_requires_a_complete_japanese_line(self):
        self.assertEqual(
            compliment.sanitize_speech(
                "Runnerさん、本当にすごい。",
                allow_desuwa=False,
                require_japanese=True,
            ),
            "Runnerさん、本当にすごい。",
        )
        self.assertIsNone(
            compliment.sanitize_speech(
                "Runner，跑得很漂亮。",
                allow_desuwa=False,
                require_japanese=True,
            )
        )

    def test_removes_a_name_when_the_program_did_not_allow_one(self):
        text = compliment.sanitize_speech(
            "Runner，这次确实跑得不错。",
            allow_desuwa=False,
            forbidden_player_name="Runner",
        )
        self.assertEqual(text, "这次确实跑得不错。")

    def test_prompt_exposes_only_program_controlled_flags(self):
        _, user = compliment.build_compliment_prompt(
            RECORD, include_player_name=False, allow_desuwa=False
        )
        self.assertIn("允许提及玩家名：否", user)
        self.assertIn("绝不能使用ですわ或desuwa", user)
        self.assertIn("首次完成：未验证", user)

    def test_prompt_allows_first_completion_only_when_verified(self):
        _, user = compliment.build_compliment_prompt(
            {**RECORD, "first_ovr_completion": True},
            include_player_name=False,
            allow_desuwa=False,
        )
        self.assertIn("首次完成：已验证，是", user)

    def test_japanese_prompt_requires_name_without_record_data(self):
        _, user = compliment.build_compliment_prompt(
            RECORD,
            include_player_name=True,
            allow_desuwa=False,
            use_japanese=True,
        )
        self.assertIn("播报语言：日语", user)
        self.assertIn("必须提及玩家名", user)
        self.assertIn("不要念地图、用时、分数", user)

class TestEligibility(unittest.IsolatedAsyncioTestCase):
    def test_score_or_tier_makes_a_run_notable(self):
        self.assertTrue(compliment.is_notable_run({"points": 801, "map_tier": 1}))
        self.assertTrue(compliment.is_notable_run({"points": 1, "map_tier": 6}))
        self.assertFalse(compliment.is_notable_run({"points": 800, "map_tier": 5}))

    async def test_ovr_history_uses_the_first_record_id(self):
        with patch.object(
            compliment,
            "fetch_json",
            AsyncMock(return_value={"data": [{"id": 42}, {"id": 43}]}),
        ) as fetch:
            self.assertTrue(await compliment.is_first_ovr_completion(RECORD, "steamid"))
        self.assertEqual(fetch.call_args.kwargs["params"]["scope"], "OVR")
        self.assertEqual(fetch.call_args.kwargs["params"]["type"], "NUB")

    async def test_ovr_history_rejects_later_runs(self):
        with patch.object(
            compliment,
            "fetch_json",
            AsyncMock(return_value={"data": [{"id": 41}, {"id": 42}]}),
        ):
            self.assertFalse(await compliment.is_first_ovr_completion(RECORD, "steamid"))

    async def test_globalapi_run_uses_the_first_history_id_for_deduplication(self):
        globalapi_record = {**RECORD, "id": None, "map_id": None}
        with patch.object(
            compliment,
            "fetch_json",
            AsyncMock(
                side_effect=[
                    [{"id": 8, "name": "kz_memento"}],
                    {"data": [{"id": 91, "time": 86.891, "teleports": 0}]},
                ]
            ),
        ):
            record_id = await compliment.first_ovr_record_id(globalapi_record, "steamid")
        self.assertEqual(record_id, 91)


class TestDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_dev_force_bypasses_eligibility_history_and_deduplication(self):
        record = {"id": 42, "map_tier": 1, "points": 1, "teleports": 2}
        bot = AsyncMock()
        attachment = object()
        with (
            patch.object(compliment, "first_ovr_record_id", AsyncMock()) as first_run,
            patch.object(compliment, "claim_run") as claim,
            patch.object(compliment, "generate_compliment", AsyncMock(return_value="跑得不错。")),
            patch.object(compliment, "synthesize_speech", AsyncMock(return_value=b"mp3")),
            patch.object(compliment.MessageSegment, "file_audio", return_value=attachment),
        ):
            await compliment.maybe_send_pr_compliment(bot, object(), record, "steamid", force=True)
        first_run.assert_not_awaited()
        claim.assert_not_called()
        bot.send.assert_awaited_once()

    async def test_japanese_mode_forces_the_name_and_disables_chinese_desuwa(self):
        bot = AsyncMock()
        with (
            patch.object(compliment.random, "random", return_value=0.1),
            patch.object(compliment, "generate_compliment", AsyncMock(return_value="すごい。")) as generate,
            patch.object(compliment, "synthesize_speech", AsyncMock(return_value=b"mp3")),
            patch.object(compliment.MessageSegment, "file_audio", return_value=object()),
        ):
            await compliment.maybe_send_pr_compliment(bot, object(), RECORD, "steamid", force=True)
        self.assertEqual(
            generate.call_args.kwargs,
            {"include_player_name": True, "allow_desuwa": False, "use_japanese": True},
        )

    async def test_high_score_run_skips_gokz_history_and_uses_its_globalapi_id(self):
        record = {**RECORD, "map_tier": 2, "points": 826, "id": 26331297}
        bot = AsyncMock()
        attachment = object()
        with (
            patch.object(compliment, "first_ovr_record_id", AsyncMock()) as first_run,
            patch.object(compliment, "claim_run", return_value=True) as claim,
            patch.object(compliment, "generate_compliment", AsyncMock(return_value="跑得不错。")),
            patch.object(compliment, "synthesize_speech", AsyncMock(return_value=b"mp3")),
            patch.object(compliment.MessageSegment, "file_audio", return_value=attachment),
        ):
            await compliment.maybe_send_pr_compliment(bot, object(), record, "steamid")
        first_run.assert_not_awaited()
        claim.assert_called_once_with(26331297)
        bot.send.assert_awaited_once()

    async def test_delivery_is_skipped_when_an_existing_claim_is_found(self):
        bot = AsyncMock()
        with (
            patch.object(compliment, "first_ovr_record_id", AsyncMock(return_value=42)),
            patch.object(compliment, "claim_run", return_value=False),
            patch.object(compliment, "generate_compliment", AsyncMock()) as generate,
        ):
            await compliment.maybe_send_pr_compliment(bot, object(), RECORD, "steamid")
        generate.assert_not_awaited()
        bot.send.assert_not_awaited()

    async def test_failed_synthesis_releases_the_claim(self):
        bot = AsyncMock()
        with (
            patch.object(compliment, "first_ovr_record_id", AsyncMock(return_value=42)),
            patch.object(compliment, "claim_run", return_value=True),
            patch.object(compliment, "generate_compliment", AsyncMock(return_value="跑得不错。")),
            patch.object(compliment, "synthesize_speech", AsyncMock(return_value=None)),
            patch.object(compliment, "release_run_claim") as release,
        ):
            await compliment.maybe_send_pr_compliment(bot, object(), RECORD, "steamid")
        release.assert_called_once_with(42)
        bot.send.assert_not_awaited()

    async def test_audio_delivery_uses_a_qq_file_attachment(self):
        bot = AsyncMock()
        attachment = object()
        with (
            patch.object(compliment, "first_ovr_record_id", AsyncMock(return_value=42)),
            patch.object(compliment, "claim_run", return_value=True),
            patch.object(compliment, "generate_compliment", AsyncMock(return_value="跑得不错。")),
            patch.object(compliment, "synthesize_speech", AsyncMock(return_value=b"mp3")),
            patch.object(compliment.MessageSegment, "file_audio", return_value=attachment),
        ):
            await compliment.maybe_send_pr_compliment(bot, object(), RECORD, "steamid")
        bot.send.assert_awaited_once()
        self.assertIs(bot.send.call_args.args[1], attachment)


class _FakeResponse:
    status = 200

    async def read(self):
        return b"mp3-bytes"


class _FakeJsonResponse(_FakeResponse):
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


class _FakeRequest:
    def __init__(self, response=None):
        self.response = response or _FakeResponse()

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_):
        return False


class _FakeSession:
    def __init__(self, responses=None):
        self.post_calls = []
        self.responses = list(responses or [_FakeResponse()])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return _FakeRequest(self.responses.pop(0))


class TestDeepSeekGeneration(unittest.IsolatedAsyncioTestCase):
    async def test_retries_empty_speech_without_using_a_fallback_template(self):
        session = _FakeSession([
            _FakeJsonResponse({"choices": [{"message": {"content": "[angry]"}}]}),
            _FakeJsonResponse({"choices": [{"message": {"content": "这次跑得很漂亮。"}}]}),
        ])
        with (
            patch.object(compliment.aiohttp, "ClientSession", return_value=session),
            patch.object(compliment, "DEEPSEEK_API_KEY", "deepseek-key"),
        ):
            text = await compliment.generate_compliment(
                RECORD, include_player_name=True, allow_desuwa=False
            )
        self.assertEqual(text, "这次跑得很漂亮。")
        self.assertEqual(len(session.post_calls), 2)


class TestFishAudioRequest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_mp3_request_with_the_configured_voice_model(self):
        session = _FakeSession()
        with (
            patch.object(compliment.aiohttp, "ClientSession", return_value=session),
            patch.object(compliment, "FISH_AUDIO_API_KEY", "fish-key"),
            patch.object(compliment, "FISH_AUDIO_REFERENCE_ID", "voice-model"),
        ):
            audio = await compliment.synthesize_speech("[calm] 这次跑得不错。")
        self.assertEqual(audio, b"mp3-bytes")
        url, request = session.post_calls[0]
        self.assertEqual(url, compliment.FISH_TTS_URL)
        self.assertEqual(request["json"]["reference_id"], "voice-model")
        self.assertEqual(request["json"]["format"], "mp3")
        self.assertEqual(request["headers"]["model"], "s2.1-pro")
