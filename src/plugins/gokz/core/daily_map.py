"""Daily GOKZ map selection and cached source-data access."""

from __future__ import annotations

import asyncio
import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from nonebot import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.plugins.gokz.api.helper import fetch_json
from src.plugins.gokz.db.db import engine
from src.plugins.gokz.db.models import DailyMapAssignment, DailyMapCache


GOKZ_TOP_V1 = "https://api.gokz.top/v1"
MAP_CACHE_TTL = timedelta(hours=1)
FINISHER_CACHE_TTL = timedelta(days=1)
IMPROVEMENT_MIN_AGE = timedelta(days=30)


def utcnow() -> datetime:
    """Use naive UTC datetimes because SQLite does not preserve tzinfo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _load_cache(cache_key: str, max_age: timedelta) -> Any | None:
    with Session(engine) as session:
        row = session.get(DailyMapCache, cache_key)
        if row and utcnow() - row.updated_at < max_age:
            try:
                return json.loads(row.payload)
            except json.JSONDecodeError:
                logger.warning("Discarding malformed daily-map cache: %s", cache_key)
    return None


def _store_cache(cache_key: str, payload: Any) -> None:
    with Session(engine) as session:
        row = session.get(DailyMapCache, cache_key)
        if row is None:
            row = DailyMapCache(cache_key=cache_key, payload=json.dumps(payload))
        else:
            row.payload = json.dumps(payload)
            row.updated_at = utcnow()
        session.add(row)
        session.commit()


async def get_maps(scope: str) -> list[dict[str, Any]] | None:
    cache_key = f"maps:{scope}"
    cached = _load_cache(cache_key, MAP_CACHE_TTL)
    if isinstance(cached, list):
        return cached

    data = await fetch_json(f"{GOKZ_TOP_V1}/maps", params={"scope": scope, "limit": 10000})
    if not isinstance(data, list):
        return None
    maps: list[dict[str, Any]] = []
    for item in data:
        tiers = item.get("tiers") if isinstance(item, dict) else None
        tier = tiers.get(scope) if isinstance(tiers, dict) else None
        if not item.get("validated") or not isinstance(tier, int) or tier < 1:
            continue
        map_id = item.get("id")
        map_name = item.get("name")
        if isinstance(map_id, int) and isinstance(map_name, str):
            maps.append({"id": map_id, "name": map_name, "tier": tier})
    _store_cache(cache_key, maps)
    return maps


async def get_nub_finishers(scope: str) -> dict[int, int] | None:
    cache_key = f"nub_finishers:{scope}"
    cached = _load_cache(cache_key, FINISHER_CACHE_TTL)
    if isinstance(cached, dict):
        return {int(map_id): int(count) for map_id, count in cached.items()}

    data = await fetch_json(f"{GOKZ_TOP_V1}/leaderboards/maps", params={"scope": scope})
    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    finishers = {
        entry["map"]["id"]: int(entry.get("unique_nub_finishes") or 0)
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("map"), dict)
        and isinstance(entry["map"].get("id"), int)
    }
    _store_cache(cache_key, finishers)
    return finishers


async def get_player_nub_pbs(steamid: str, scope: str) -> list[dict[str, Any]] | None:
    data = await fetch_json(
        f"{GOKZ_TOP_V1}/records/pb",
        params={"identifier": steamid, "scope": scope, "type": "NUB", "limit": 10000},
    )
    if not isinstance(data, list):
        return None
    return [record for record in data if record.get("stage") == 0 and isinstance(record.get("map_id"), int)]


def _weighted_choice(items: list[dict[str, Any]], weights: Iterable[float], rng: random.Random) -> dict[str, Any]:
    values = [max(0.0, float(weight)) for weight in weights]
    if not any(values):
        values = [1.0] * len(items)
    return rng.choices(items, weights=values, k=1)[0]


def _choose_tier(
    candidates: list[dict[str, Any]], maps: list[dict[str, Any]], completed_ids: set[int], rng: random.Random
) -> int:
    available_tiers = sorted({item["tier"] for item in candidates})
    tier_items = [{"tier": tier} for tier in available_tiers]
    tier_weights = []
    for tier in available_tiers:
        tier_maps = [item for item in maps if item["tier"] == tier]
        completed = sum(item["id"] in completed_ids for item in tier_maps)
        tier_weights.append(completed / len(tier_maps) if tier_maps else 0.0)
    return _weighted_choice(tier_items, tier_weights, rng)["tier"]


def _normalized_inverse(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [1.0] * len(values)
    return [1.0 + (high - value) / (high - low) for value in values]


def _normalized_direct(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [1.0] * len(values)
    return [1.0 + (value - low) / (high - low) for value in values]


def choose_new_map(
    maps: list[dict[str, Any]], completed_ids: set[int], finishers: dict[int, int], rng: random.Random
) -> dict[str, Any] | None:
    candidates = [item for item in maps if item["id"] not in completed_ids]
    if not candidates:
        return None
    tier = _choose_tier(candidates, maps, completed_ids, rng)
    candidates = [item for item in candidates if item["tier"] == tier]
    selected = _weighted_choice(candidates, [finishers.get(item["id"], 0) + 1 for item in candidates], rng)
    return {**selected, "points": None, "last_pb_at": None, "nub_finishers": finishers.get(selected["id"], 0)}


def choose_improvement_map(
    maps: list[dict[str, Any]], pbs: list[dict[str, Any]], finishers: dict[int, int], now: datetime, rng: random.Random
) -> dict[str, Any] | None:
    map_by_id = {item["id"]: item for item in maps}
    candidates = []
    for pb in pbs:
        last_pb_at = parse_timestamp(pb.get("updated_on")) or parse_timestamp(pb.get("created_on"))
        map_data = map_by_id.get(pb["map_id"])
        if map_data and last_pb_at and now - last_pb_at >= IMPROVEMENT_MIN_AGE:
            candidates.append({
                **map_data,
                "points": float(pb.get("points") or 0),
                "last_pb_at": last_pb_at,
                "nub_finishers": finishers.get(map_data["id"], 0),
            })
    if not candidates:
        return None

    completed_ids = {pb["map_id"] for pb in pbs}
    tier = _choose_tier(candidates, maps, completed_ids, rng)
    candidates = [item for item in candidates if item["tier"] == tier]
    point_weights = _normalized_inverse([item["points"] for item in candidates])
    age_weights = _normalized_direct([(now - item["last_pb_at"]).total_seconds() for item in candidates])
    popularity_weights = _normalized_direct([float(item["nub_finishers"]) for item in candidates])
    selected = _weighted_choice(
        candidates,
        [point * age * popularity for point, age, popularity in zip(point_weights, age_weights, popularity_weights)],
        rng,
    )
    return selected


def stored_assignments(qid: str, assignment_date: date) -> dict[str, DailyMapAssignment]:
    with Session(engine) as session:
        rows = session.exec(
            select(DailyMapAssignment).where(
                DailyMapAssignment.qid == qid,
                DailyMapAssignment.assignment_date == assignment_date,
            )
        ).all()
        return {row.daily_type: row for row in rows}


def save_assignments(qid: str, assignment_date: date, scope: str, selections: dict[str, dict[str, Any]]) -> None:
    with Session(engine) as session:
        existing = {
            row.daily_type
            for row in session.exec(
                select(DailyMapAssignment).where(
                    DailyMapAssignment.qid == qid,
                    DailyMapAssignment.assignment_date == assignment_date,
                )
            )
        }
        for daily_type, item in selections.items():
            if daily_type in existing:
                continue
            session.add(DailyMapAssignment(
                qid=qid,
                assignment_date=assignment_date,
                daily_type=daily_type,
                mode=scope,
                map_id=item["id"],
                map_name=item["name"],
                map_tier=item["tier"],
                points=round(item["points"]) if item.get("points") is not None else None,
                last_pb_at=item.get("last_pb_at"),
                nub_finishers=item.get("nub_finishers", 0),
            ))
        try:
            session.commit()
        except IntegrityError:
            # Another command generated this player's same-day result first.
            session.rollback()


async def get_daily_maps(qid: str, steamid: str, scope: str) -> dict[str, DailyMapAssignment] | None:
    assignment_date = utc_today()
    existing = stored_assignments(qid, assignment_date)
    if {"improvement", "new"}.issubset(existing):
        return existing

    maps, finishers, pbs = await asyncio.gather(
        get_maps(scope),
        get_nub_finishers(scope),
        get_player_nub_pbs(steamid, scope),
    )
    if maps is None or finishers is None or pbs is None:
        return None
    completed_ids = {pb["map_id"] for pb in pbs}
    rng = random.SystemRandom()
    selections: dict[str, dict[str, Any]] = {}
    if "improvement" not in existing:
        selected = choose_improvement_map(maps, pbs, finishers, utcnow(), rng)
        if selected:
            selections["improvement"] = selected
    if "new" not in existing:
        selected = choose_new_map(maps, completed_ids, finishers, rng)
        if selected:
            selections["new"] = selected
    save_assignments(qid, assignment_date, scope, selections)
    return stored_assignments(qid, assignment_date)
