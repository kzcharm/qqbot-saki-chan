import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, List, Tuple, Dict

import aiohttp
from nonebot import logger

from .helper import fetch_json

STATUS_LABELS = {
    0: "故障",
    1: "正常",
    2: "等待",
    3: "维护",
}


@dataclass
class UptimeKumaSummary:
    status_code: Optional[int]
    current_response_ms: Optional[float]
    avg_response_24h: Optional[str]
    uptime_24h: Optional[float]
    uptime_30d: Optional[str]
    uptime_365d: Optional[str]
    events: List[Tuple[int, str, str]]


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _format_datetime(value: Optional[str]) -> str:
    if not value:
        return ""
    if "T" not in value:
        return value
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return value


def _parse_badge_value(svg_text: Optional[str]) -> Optional[str]:
    if not svg_text:
        return None
    match = re.search(r'aria-label="[^"]*?:\s*([^"]+)"', svg_text)
    if match:
        return match.group(1).strip()
    match = re.search(r"<title>[^<]*?:\s*([^<]+)</title>", svg_text)
    if match:
        return match.group(1).strip()
    texts = re.findall(r"<text[^>]*>([^<]+)</text>", svg_text)
    if texts:
        return texts[-1].strip()
    return None


async def _fetch_text(url: str, timeout: int = 15, auth: Optional[aiohttp.BasicAuth] = None) -> Optional[str]:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url, auth=auth) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"Uptime Kuma request failed {response.status}: {url}")
                return None
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return None


async def fetch_entry_page_slug(base_url: str) -> Optional[str]:
    base_url = _normalize_base_url(base_url)
    data = await fetch_json(f"{base_url}/api/entry-page", timeout=10)
    if not isinstance(data, dict):
        return None
    if data.get("type") == "statusPageMatchedDomain":
        return data.get("statusPageSlug")
    if data.get("type") == "entryPage":
        entry_page = data.get("entryPage", "")
        if entry_page.startswith("statusPage-"):
            return entry_page.replace("statusPage-", "", 1)
    return None


def find_monitor(status_page_data: Dict[str, Any], monitor_name: str) -> Optional[Dict[str, Any]]:
    for group in status_page_data.get("publicGroupList", []) or []:
        for monitor in group.get("monitorList", []) or []:
            if monitor.get("name", "").lower() == monitor_name.lower():
                return monitor
    return None


async def fetch_metrics_status(base_url: str, api_key: str, monitor_name: str) -> Tuple[Optional[int], Optional[float]]:
    if not api_key:
        return None, None
    base_url = _normalize_base_url(base_url)
    auth = aiohttp.BasicAuth("", api_key)
    metrics_text = await _fetch_text(f"{base_url}/metrics", auth=auth)
    if not metrics_text:
        return None, None
    status_value = None
    response_value = None
    for line in metrics_text.splitlines():
        if line.startswith("#") or "monitor_name" not in line:
            continue
        if f'monitor_name="{monitor_name}"' not in line:
            continue
        if line.startswith("monitor_status"):
            try:
                status_value = int(float(line.rsplit(" ", 1)[-1]))
            except ValueError:
                pass
        elif line.startswith("monitor_response_time"):
            try:
                response_value = float(line.rsplit(" ", 1)[-1])
                if response_value <= 0:
                    response_value = None
            except ValueError:
                pass
    return status_value, response_value


async def fetch_badge_value(base_url: str, monitor_id: int, path: str) -> Optional[str]:
    base_url = _normalize_base_url(base_url)
    svg_text = await _fetch_text(f"{base_url}/api/badge/{monitor_id}/{path}")
    return _parse_badge_value(svg_text)


def extract_events(heartbeat_list: Optional[List[Dict[str, Any]]], limit: int = 4) -> List[Tuple[int, str, str]]:
    if not heartbeat_list:
        return []
    beats = list(heartbeat_list)
    beats.sort(key=lambda beat: beat.get("time") or beat.get("localDateTime") or "")
    events: List[Tuple[int, str, str]] = []
    last_status = None
    for beat in beats:
        status = beat.get("status")
        if status is None:
            continue
        if status != last_status:
            time_value = beat.get("localDateTime") or _format_datetime(beat.get("time"))
            msg = beat.get("msg", "")
            events.append((status, time_value, msg))
            last_status = status
    if not events:
        return []
    events = events[-limit:]
    events.reverse()
    return events


async def fetch_uptime_kuma_summary(
    base_url: str,
    monitor_name: str,
    api_key: str = "",
) -> Tuple[Optional[UptimeKumaSummary], Optional[str]]:
    base_url = _normalize_base_url(base_url)
    slug = await fetch_entry_page_slug(base_url)
    if not slug:
        slug = "default"

    status_page_data = await fetch_json(f"{base_url}/api/status-page/{slug}", timeout=15)
    if not isinstance(status_page_data, dict) or "publicGroupList" not in status_page_data:
        return None, "无法获取状态页数据"

    monitor = find_monitor(status_page_data, monitor_name)
    if not monitor:
        return None, f"未找到监控: {monitor_name}"

    monitor_id = monitor.get("id")
    if monitor_id is None:
        return None, "监控 ID 缺失"

    status_code = monitor.get("status")
    metrics_status, current_response = await fetch_metrics_status(base_url, api_key, monitor_name)
    if metrics_status is not None:
        status_code = metrics_status

    heartbeat_data = await fetch_json(f"{base_url}/api/status-page/heartbeat/{slug}", timeout=15)
    heartbeat_list = None
    uptime_24h = None
    if isinstance(heartbeat_data, dict):
        heartbeat_list = heartbeat_data.get("heartbeatList", {}).get(str(monitor_id))
        if heartbeat_list is None:
            heartbeat_list = heartbeat_data.get("heartbeatList", {}).get(monitor_id)
        uptime_list = heartbeat_data.get("uptimeList", {})
        uptime_24h = uptime_list.get(f"{monitor_id}_24")
        if uptime_24h is None:
            uptime_24h = uptime_list.get(str(monitor_id))

    if status_code is None and heartbeat_list:
        latest = max(
            heartbeat_list,
            key=lambda beat: beat.get("time") or beat.get("localDateTime") or "",
        )
        status_code = latest.get("status")

    events = extract_events(heartbeat_list)

    avg_response_24h = await fetch_badge_value(base_url, monitor_id, "avg-response/24")
    if not avg_response_24h:
        avg_response_24h = await fetch_badge_value(base_url, monitor_id, "ping/24")

    uptime_24h_badge = await fetch_badge_value(base_url, monitor_id, "uptime/24")
    uptime_30d = await fetch_badge_value(base_url, monitor_id, "uptime/720")
    uptime_365d = await fetch_badge_value(base_url, monitor_id, "uptime/8760")

    if uptime_24h is None and uptime_24h_badge:
        try:
            uptime_24h = float(uptime_24h_badge.replace("%", "")) / 100
        except ValueError:
            uptime_24h = None

    if current_response is None:
        response_badge = await fetch_badge_value(base_url, monitor_id, "response")
        if not response_badge:
            response_badge = await fetch_badge_value(base_url, monitor_id, "ping")
        if response_badge and response_badge.lower() != "n/a":
            try:
                current_response = float(response_badge.replace("ms", "").strip())
            except ValueError:
                current_response = None

    return (
        UptimeKumaSummary(
            status_code=status_code,
            current_response_ms=current_response,
            avg_response_24h=avg_response_24h,
            uptime_24h=uptime_24h,
            uptime_30d=uptime_30d,
            uptime_365d=uptime_365d,
            events=events,
        ),
        None,
    )
