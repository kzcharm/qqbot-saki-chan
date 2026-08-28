import json

with open("data/gokz_maps.json", "r", encoding="utf-8") as f:
    maps_data = json.load(f)

MAP_TIERS = {
    map_info["name"]: map_info["difficulty"]
    for map_info in maps_data
    if map_info.get("name") and map_info.get("difficulty") is not None
}


def update_map_catalog(maps: list[dict], *, replace: bool = False) -> None:
    """Merge validated GOKZ.TOP map records into the runtime catalog.

    The checked-in map file is only a bootstrap fallback.  GOKZ.TOP is the
    source of truth for current names and tiers, so callers can refresh this
    mapping from the persisted API cache without changing command code.
    """
    if replace:
        MAP_TIERS.clear()
    for map_info in maps:
        name = map_info.get("name")
        tier = map_info.get("tier")
        if isinstance(name, str) and isinstance(tier, int) and tier >= 1:
            MAP_TIERS[name] = tier
