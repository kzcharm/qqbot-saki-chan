from textwrap import dedent
from typing import Optional

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent

from ..config import UPTIME_KUMA_API_KEY
from ..api.uptime_kuma import (
    STATUS_LABELS,
    fetch_uptime_kuma_summary,
)


UPTIME_KUMA_BASE_URL = "https://health.axekz.com"
UPTIME_KUMA_MONITOR_NAME = "GlobalAPI"

api_status = on_command("api", aliases={"API"})

STATUS_EMOJI = {
    0: "🔴",
    1: "🟢",
    2: "🟡",
    3: "🟡",
}


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    percent = value * 100 if value <= 1 else value
    text = f"{percent:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _format_ms(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "N/A"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text} ms"


def _normalize_value(value: Optional[str]) -> str:
    if not value:
        return "N/A"
    return "N/A" if value.strip().lower() == "n/a" else value


def _format_status(status_code: Optional[int]) -> str:
    label = STATUS_LABELS.get(status_code, "未知")
    emoji = STATUS_EMOJI.get(status_code, "🟡")
    return f"{emoji}{label}"


@api_status.handle()
async def _(event: MessageEvent):
    summary, error = await fetch_uptime_kuma_summary(
        UPTIME_KUMA_BASE_URL,
        UPTIME_KUMA_MONITOR_NAME,
        UPTIME_KUMA_API_KEY,
    )
    if error or not summary:
        return await api_status.finish(f"获取 GlobalAPI 状态失败: {error or '未知错误'}")

    status_text = _format_status(summary.status_code)
    current_response = _format_ms(summary.current_response_ms)
    avg_response_24h = _normalize_value(summary.avg_response_24h)
    uptime_24h = _format_percent(summary.uptime_24h)
    uptime_30d = _normalize_value(summary.uptime_30d)
    uptime_365d = _normalize_value(summary.uptime_365d)

    rows = "暂无记录"
    if summary.events:
        rows = "\n".join(
            f"{_format_status(status)}\t{time}\t{msg}"
            for status, time, msg in summary.events
        )

    content = dedent(f"""
        当前状态: {status_text}
        当前响应: {current_response}
        24小时平均响应: {avg_response_24h}
        24小时可用率: {uptime_24h}
        30天可用率: {uptime_30d}
        1年可用率: {uptime_365d}

        状态\t时间\t信息
        {rows}
    """).strip()

    if getattr(event, "group_id", None):
        content = "\n" + content
    await api_status.finish(content)
