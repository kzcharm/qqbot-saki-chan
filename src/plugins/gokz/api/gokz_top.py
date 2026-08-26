"""GOKZ.TOP v1 queries used by the QQ command handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from .helper import fetch_json


BASE_URL = "https://api.gokz.top/v1"


class GOKZTopAPIError(RuntimeError):
    """The v1 API could not provide a valid response."""


def _scope(mode: str) -> str:
    scopes = {
        "kz_timer": "KZT",
        "kz_simple": "SKZ",
        "kz_vanilla": "VNL",
    }
    return scopes.get(mode.lower(), mode.upper())


def _record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the v1 player reference for legacy command formatters."""
    player = record.get("player")
    player = player if isinstance(player, Mapping) else {}
    return {
        **record,
        "player_name": player.get("display_name") or "未知玩家",
        "steam_id": record.get("steam_id") or player.get("steamid64"),
    }


async def _pb_records(**params: Any) -> list[dict[str, Any]]:
    data = await fetch_json(f"{BASE_URL}/records/pb", params=params)
    if not isinstance(data, list):
        raise GOKZTopAPIError("invalid PB response")
    return [_record(item) for item in data if isinstance(item, Mapping)]


async def fetch_personal_best(
    steamid64: str, map_name: str, scope: str, record_type: str,
) -> dict[str, Any] | None:
    records = await _pb_records(
        identifier=steamid64,
        map_name=map_name,
        scope=_scope(scope),
        type=record_type,
        stage=0,
        limit=1,
    )
    return records[0] if records else None


async def fetch_personal_recent(steamid64: str, scope: str) -> dict[str, Any] | None:
    common = {
        "identifier": steamid64,
        "scope": _scope(scope),
        "stage": 0,
        "sort_by": "created_at",
        "sort_order": "desc",
        "limit": 1,
    }
    nub_records, pro_records = await asyncio.gather(
        _pb_records(**common, type="NUB"),
        _pb_records(**common, type="PRO"),
    )
    records = nub_records + pro_records
    return max(records, key=lambda record: str(record.get("created_on") or "")) if records else None


async def fetch_world_record(
    map_name: str, scope: str, record_type: str,
) -> dict[str, Any] | None:
    records = await _pb_records(
        map_name=map_name,
        scope=_scope(scope),
        type=record_type,
        stage=0,
        sort_by="time",
        sort_order="asc",
        limit=1,
    )
    return records[0] if records else None


async def fetch_personal_bans(steamid64: str) -> list[dict[str, Any]]:
    data = await fetch_json(
        f"{BASE_URL}/bans",
        params={"steamid64": steamid64},
    )
    bans = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(bans, list):
        raise GOKZTopAPIError("invalid bans response")
    return [ban for ban in bans if isinstance(ban, dict)]


async def fetch_run_history(
    steamid64: str, map_id: int, scope: str, record_type: str,
) -> dict[str, Any]:
    data = await fetch_json(
        f"{BASE_URL}/records/run-history",
        params={
            "identifier": steamid64,
            "map_id": map_id,
            "stage": 0,
            "scope": _scope(scope),
            "type": record_type,
        },
    )
    if not isinstance(data, Mapping) or not isinstance(data.get("data"), list):
        raise GOKZTopAPIError("invalid run history response")
    return dict(data)
