import json

with open("data/gokz_maps.json", "r", encoding="utf-8") as f:
    maps_data = json.load(f)

MAP_TIERS = {
    map_info["name"]: map_info["difficulty"]
    for map_info in maps_data
    if map_info.get("name") and map_info.get("difficulty") is not None
}
