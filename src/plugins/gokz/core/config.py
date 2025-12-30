import json
from ..api.helper import fetch_json
from ..config import GOKZ_TOP_API_KEY

with open("data/gokz_maps.json", "r", encoding="utf-8") as f:
    maps_data = json.load(f)

MAP_TIERS = {
    map_info["name"]: map_info["difficulty"]
    for map_info in maps_data
    if map_info.get("name") and map_info.get("difficulty") is not None
}


async def get_map_tier(map_name: str) -> int | str:
    """
    Get map tier from gokz.top API, falling back to local MAP_TIERS if API fails.
    
    Args:
        map_name: The name of the map
        
    Returns:
        Map tier (difficulty) as int, or '未知' if not found
    """
    BASE_URL = "https://api.gokz.top/api/v1"
    map_url = f"{BASE_URL}/maps/name/{map_name}"
    
    # Prepare headers with API key if available
    headers = {}
    if GOKZ_TOP_API_KEY:
        headers["Authorization"] = f"Bearer {GOKZ_TOP_API_KEY}"
    
    try:
        map_data = await fetch_json(map_url, headers=headers, timeout=10)
        if map_data and isinstance(map_data, dict):
            difficulty = map_data.get("difficulty")
            if difficulty is not None:
                return difficulty
    except Exception:
        # Fall back to local MAP_TIERS if API call fails
        pass
    
    # Fallback to local MAP_TIERS
    return MAP_TIERS.get(map_name, '未知')
