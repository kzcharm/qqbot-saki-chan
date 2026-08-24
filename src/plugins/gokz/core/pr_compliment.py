"""One-time, TTS-safe compliments for notable first GOKZ completions."""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Mapping
from typing import Any

import aiohttp
from nonebot import logger
from nonebot.adapters.qq import MessageSegment
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from src.plugins.gokz.api.helper import fetch_json
from src.plugins.gokz.config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    FISH_AUDIO_API_KEY,
    FISH_AUDIO_REFERENCE_ID,
)
from src.plugins.gokz.core.formatter import format_gruntime
from src.plugins.gokz.db.db import engine
from src.plugins.gokz.db.models import ComplimentedRun


GOKZ_TOP_V1 = "https://api.gokz.top/v1"
FISH_TTS_URL = "https://api.fish.audio/v1/tts"
MAX_SPEECH_LENGTH = 120
MAX_GENERATION_ATTEMPTS = 4
JAPANESE_COMPLIMENT_PROBABILITY = 0.2
PLAYER_NAME_PROBABILITY = 0.5
DESUWA_PROBABILITY = 0.5
ALLOWED_TTS_TAGS = {
    "calm",
    "confident",
    "satisfied",
    "proud",
    "surprised",
    "soft tone",
    "emphasis",
    "chuckling",
    "sighing",
    "break",
    "long-break",
}
TTS_TAG_RE = re.compile(r"\[([^\[\]]+)\]")
ASCII_DESUWA_RE = re.compile(r"\bdesuwa\b", re.IGNORECASE)


def _record_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    return []


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def first_ovr_record_id(record: Mapping[str, Any], steamid: str) -> int | None:
    """Return the GOKZ Top ID when this GlobalAPI run is the first OVR completion."""
    record_id = record.get("id")
    map_id = record.get("map_id")
    if not isinstance(map_id, int):
        maps = await fetch_json(
            f"{GOKZ_TOP_V1}/maps",
            params={"name": record.get("map_name"), "limit": 10},
        )
        map_candidates = _record_list(maps)
        map_name = str(record.get("map_name") or "").casefold()
        map_data = next(
            (item for item in map_candidates if str(item.get("name") or "").casefold() == map_name),
            map_candidates[0] if map_candidates else None,
        )
        map_id = map_data.get("id") if isinstance(map_data, Mapping) else None
    if not isinstance(map_id, int):
        return None

    history = await fetch_json(
        f"{GOKZ_TOP_V1}/records/run-history",
        params={
            "identifier": steamid,
            "map_id": map_id,
            "stage": int(record.get("stage") or 0),
            "scope": "OVR",
            # NUB history includes every normal completion, including PRO runs.
            "type": "NUB",
        },
    )
    entries = _record_list(history)
    if not entries:
        return None
    first = entries[0]
    if isinstance(record_id, int):
        return record_id if first.get("id") == record_id else None
    # GlobalAPI is the source for `/pr`; when it does not expose a GOKZ Top
    # record ID, match the current run to the first OVR history entry.
    current_run_is_first = (
        abs(float(first.get("time") or -1) - float(record.get("time") or -2)) < 0.001
        and _integer(first.get("teleports")) == _integer(record.get("teleports"))
    )
    first_id = first.get("id")
    return first_id if current_run_is_first and isinstance(first_id, int) else None


async def is_first_ovr_completion(record: Mapping[str, Any], steamid: str) -> bool:
    """Return whether this is the first completion, across all GOKZ modes."""
    return await first_ovr_record_id(record, steamid) is not None


def is_notable_run(record: Mapping[str, Any]) -> bool:
    return _integer(record.get("points")) > 800 or _integer(
        record.get("map_tier") or record.get("tier")
    ) >= 6


def claim_run(record_id: int) -> bool:
    """Atomically claim a record. A duplicate claim means no new voice message."""
    with Session(engine) as session:
        try:
            session.add(ComplimentedRun(record_id=record_id))
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False


def release_run_claim(record_id: int) -> None:
    """Permit a later `/pr` retry when generation or delivery failed."""
    with Session(engine) as session:
        run = session.get(ComplimentedRun, record_id)
        if run:
            session.delete(run)
            session.commit()


def build_compliment_prompt(
    record: Mapping[str, Any], *, include_player_name: bool, allow_desuwa: bool,
    use_japanese: bool = False,
) -> tuple[str, str]:
    """Return the fixed policy prompt and run-specific user facts."""
    system = """你是 KZ 社区的语音成就播报员。只输出最终播报文本，不要解释。播报直接交给 TTS，输出一到两句短的自然口语，使用逗号、句号或问号。禁止 Markdown、颜文字、emoji、破折号、分号、括号、省略号和成绩单式复述。
语气克制、有教养、略带高傲的大小姐感。可以轻微调侃或不情愿地认可，但绝不能羞辱、阴阳怪气、夸大成绩、直接扮演角色或引用角色台词。
夸赞要求：每条播报必须至少包含一个明确的褒义评价词，例如厉害、漂亮、出色、完美、精彩、惊人、漂亮极了、无可挑剔。不能只停留在还算利落、勉强认可这类模糊中性词。
傲娇表达可按需使用：采用先抑后扬、不情愿承认或嫌弃中带肯定的结构，例如以真是的、受不了、虽然不想说、本来想挑刺的、真拿你没办法开头，后半句直接给出肯定；也可用算你厉害、这波我认了、给你点个赞吧收束。不要每条都使用这种结构。
播报切入点可以从以下维度自然发散：零存点、用时、分数、地图特征、操作细腻度、听觉流畅感、反差点评、节奏感、身心状态推测、结果导向。避免每次都以“零存点”开头，避免重复使用“干净利落”“一气呵成”“跑穿”等套话。
关于零存点的表达：优先使用“裸跳”及其自然变体，例如全程裸跳、裸跳收掉、裸跳跑完、直接裸跳、裸跳过图。仅在需要偶尔变化时，才使用“零存点”“没碰存点”等替代，这类替代表达占比不超过三成。禁止每句都固定使用同一词组。
标签使用规则：Fish S2 标签最多两个，可选 [calm]、[confident]、[satisfied]、[proud]、[surprised]、[soft tone]、[emphasis]、[chuckling]、[sighing]、[break]、[long-break]。标签不算句子，不能单独输出，必须接完整中文播报正文。
成绩处理规则：从真实存在的零存点、首次完成、高分、高难度、PB 提升、高排名、Server Record 或 World Record 中随机挑一到两个重点，不要虚构未提供的成就。若成绩信息标为首次完成未验证，禁止使用或暗示首次完成、首通、第一次跑完、第一次裸跳等说法。
玩家名与语气词规则：玩家名每次随机决定是否提及；日文“ですわ”每次随机决定是否使用。"""
    player = record.get("player")
    player_name = record.get("player_name") or (
        player.get("name") if isinstance(player, Mapping) else "玩家"
    )
    facts = {
        "玩家": player_name,
        "地图": record.get("map_name"),
        "地图难度": f"T{record.get('map_tier') or record.get('tier') or 0}",
        "模式": record.get("mode"),
        "用时": format_gruntime(float(record.get("time") or 0)),
        "存点数": int(record.get("teleports") or 0),
        "分数": int(record.get("points") or 0),
        "首次完成": (
            "已验证，是"
            if record.get("first_ovr_completion") is True
            else "未验证，禁止提及或暗示首次完成、首通、第一次跑完或第一次裸跳"
        ),
        "播报语言": (
            "日语。必须提及玩家名，只输出一句自然、简短的日语称赞。"
            "不要念地图、用时、分数或其他成绩数据。"
            if use_japanese else "中文"
        ),
        "允许提及玩家名": "是" if include_player_name else "否，不要提及名字或昵称",
        "允许使用日文ですわ": "是，可选且最多一次，只能置于任意一句的句末" if allow_desuwa else "否，绝不能使用ですわ或desuwa",
    }
    user = "本次真实成绩如下：\n" + "\n".join(f"{key}：{value}" for key, value in facts.items())
    return system, user


def sanitize_speech(
    text: str,
    *,
    allow_desuwa: bool,
    forbidden_player_name: str | None = None,
    require_japanese: bool = False,
) -> str | None:
    """Enforce a compact, speakable subset of the model response."""
    text = str(text).replace("```", "").replace("**", "").replace("__", "")
    text = text.replace("——", "，").replace("—", "，").replace("–", "，")
    text = text.replace(";", "，").replace("；", "，").replace("…", "。").replace("...", "。")
    text = text.translate(str.maketrans({"(": "", ")": "", "（": "", "）": "", "#": ""}))
    text = " ".join(text.strip().split())
    if not text:
        return None
    # Formatting artefacts should not discard an otherwise good voice line.
    # DeepSeek occasionally leaves a Markdown marker or angle-bracket wrapper
    # around its answer; strip those characters and continue sanitising.
    text = re.sub(r"[`*_{}<>]", "", text)
    text = text.replace("【", "").replace("】", "")

    tags: list[str] = []

    def keep_tag(match: re.Match[str]) -> str:
        tag = match.group(1).strip().lower()
        if tag in ALLOWED_TTS_TAGS and len(tags) < 2:
            tags.append(tag)
            return f"\uFFF0{len(tags) - 1}\uFFF1"
        return ""

    text = TTS_TAG_RE.sub(keep_tag, text).replace("[", "").replace("]", "")
    for index, tag in enumerate(tags):
        text = text.replace(f"\uFFF0{index}\uFFF1", f"[{tag}]")
    text = ASCII_DESUWA_RE.sub("", text)
    if forbidden_player_name:
        text = re.sub(re.escape(forbidden_player_name), "", text, flags=re.IGNORECASE)
    desuwa_marker = "\uFFF2"
    if allow_desuwa and "ですわ" in text:
        text = text.replace("ですわ", desuwa_marker, 1).replace("ですわ", "")
    else:
        text = text.replace("ですわ", "")
    # Keep one naturally positioned sentence-final ですわ. An occurrence in
    # the middle of a sentence is removed instead of being moved unnaturally.
    text = re.sub(
        rf"{desuwa_marker}(?=[。！？]|$)",
        "ですわ",
        text,
    ).replace(desuwa_marker, "").strip(" ，。！？")
    if not text:
        return None
    # A Japanese line needs meaningful kana beyond the player's Latin name.
    # This rejects Chinese fallbacks and name-only replies before they reach TTS.
    if require_japanese and len(re.findall(r"[ぁ-んァ-ヶ]", text)) < 3:
        return None
    if len(text) > MAX_SPEECH_LENGTH:
        sentence_end = max(text.rfind(mark, 0, MAX_SPEECH_LENGTH) for mark in "。！？")
        text = text[:sentence_end + 1] if sentence_end >= 0 else text[:MAX_SPEECH_LENGTH]
    if text.count("。") + text.count("！") + text.count("？") > 2:
        parts = re.split(r"(?<=[。！？])", text)
        text = "".join(parts[:2]).strip()
    return text if text[-1] in "。！？" else f"{text}。"


async def generate_compliment(
    record: Mapping[str, Any], *, include_player_name: bool, allow_desuwa: bool,
    use_japanese: bool = False,
) -> str | None:
    if not DEEPSEEK_API_KEY:
        logger.warning("Skipping /pr compliment: DEEPSEEK_API_KEY is not configured")
        return None
    system, user = build_compliment_prompt(
        record,
        include_player_name=include_player_name,
        allow_desuwa=allow_desuwa,
        use_japanese=use_japanese,
    )
    url = f"{DEEPSEEK_API_BASE.rstrip('/')}/chat/completions"
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.9,
        "max_tokens": 180,
    }
    player = record.get("player")
    player_name = record.get("player_name") or (
        player.get("name") if isinstance(player, Mapping) else None
    )
    for attempt in range(MAX_GENERATION_ATTEMPTS):
        retry_instruction = (
            "请重新生成。只输出一句完整、自然的日语称赞，必须提及玩家名，"
            "不得包含中文或成绩数据。"
            if use_japanese else
            "请重新生成。只输出一到两句完整的中文播报正文，不能只输出语气标签。"
        )
        request_body = body if attempt == 0 else {
            **body,
            "messages": [
                *body["messages"],
                {
                    "role": "user",
                    "content": retry_instruction,
                },
            ],
        }
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=request_body,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                ) as response:
                    if response.status != 200:
                        logger.warning(f"DeepSeek compliment request failed: {response.status}")
                        return None
                    data = await response.json()
            speech = sanitize_speech(
                data["choices"][0]["message"]["content"],
                allow_desuwa=allow_desuwa,
                forbidden_player_name=None if include_player_name else str(player_name or ""),
                require_japanese=use_japanese,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning(f"DeepSeek compliment request failed: {error}")
            return None
        except (KeyError, IndexError, TypeError):
            logger.warning("DeepSeek returned an unusable compliment response")
            return None
        if speech:
            return speech
        if attempt + 1 < MAX_GENERATION_ATTEMPTS:
            logger.warning("DeepSeek returned empty speech; retrying /pr compliment generation")
    logger.warning("DeepSeek returned empty speech after retries; skipping /pr compliment")
    return None


async def synthesize_speech(text: str) -> bytes | None:
    if not FISH_AUDIO_API_KEY or not FISH_AUDIO_REFERENCE_ID:
        logger.warning("Skipping /pr compliment: Fish Audio credentials are not configured")
        return None
    body = {
        "text": text,
        "reference_id": FISH_AUDIO_REFERENCE_ID,
        "format": "mp3",
        "sample_rate": 44100,
        "mp3_bitrate": 128,
        "normalize": True,
        "prosody": {"speed": 1, "volume": 0, "normalize_loudness": True},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                FISH_TTS_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {FISH_AUDIO_API_KEY}",
                    "model": "s2.1-pro",
                },
            ) as response:
                if response.status != 200:
                    logger.warning(f"Fish Audio synthesis failed: {response.status}")
                    return None
                audio = await response.read()
                return audio or None
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        logger.warning(f"Fish Audio synthesis failed: {error}")
        return None


async def maybe_send_pr_compliment(
    bot: Any,
    event: Any,
    record: Mapping[str, Any],
    steamid: str,
    *,
    force: bool = False,
) -> None:
    """Best-effort delivery; this must never break the normal `/pr` response."""
    record_id: int | None = None
    if not force:
        if not is_notable_run(record):
            return
        # High-score runs are already exceptional and have a stable GlobalAPI ID.
        # Only T6+ runs need the extra GOKZ Top history round trip to establish a
        # cross-mode first completion.
        if _integer(record.get("map_tier") or record.get("tier")) >= 6:
            record_id = await first_ovr_record_id(record, steamid)
            if isinstance(record_id, int):
                record = {**record, "first_ovr_completion": True}
        else:
            record_id = record.get("id")
        if not isinstance(record_id, int):
            return
        if not claim_run(record_id):
            return

    try:
        use_japanese = random.random() < JAPANESE_COMPLIMENT_PROBABILITY
        text = await generate_compliment(
            record,
            include_player_name=use_japanese or random.random() < PLAYER_NAME_PROBABILITY,
            # Japanese output is already a distinct style; keep the Chinese
            # `ですわ` randomisation separate from it.
            allow_desuwa=not use_japanese and random.random() < DESUWA_PROBABILITY,
            use_japanese=use_japanese,
        )
        if not text:
            logger.warning(f"No safe /pr compliment text was generated for record {record_id}")
            release_run_claim(record_id)
            return
        audio = await synthesize_speech(text)
        if not audio:
            logger.warning(f"No Fish Audio data was generated for record {record_id}")
            release_run_claim(record_id)
            return
        await bot.send(event, MessageSegment.file_audio(audio))
    except Exception:
        logger.exception(f"Unable to send /pr voice compliment for record {record_id or 'dev-bypass'}")
        if record_id is not None:
            release_run_claim(record_id)
