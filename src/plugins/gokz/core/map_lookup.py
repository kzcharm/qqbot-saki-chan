from difflib import SequenceMatcher
from src.plugins.gokz.core.kreedz import search_map

MAX_MAP_CHOICES = 5
_STRONG_MATCH_MIN_SCORE = 0.9
_STRONG_MATCH_GAP = 0.1


def _map_basename(map_name: str) -> str:
    """Return the map name without its mode/source prefix."""
    return map_name.split("_", 1)[1] if "_" in map_name else map_name


def resolve_map_name(query: str) -> tuple[str | None, list[str]]:
    """Resolve a map query or return its ranked ambiguous candidates.

    Exact full-name and unique prefix-stripped matches bypass the picker.
    Strong fuzzy leaders are also selected directly; otherwise the second
    tuple item contains the ranked candidates for the picker.
    """
    matches = search_map(query)
    if not matches:
        return None, []

    normalized_query = query.casefold().strip()

    exact_match = next((name for name in matches if name.casefold() == normalized_query), None)
    if exact_match is not None or len(matches) == 1:
        return exact_match or matches[0], []

    # Users commonly omit the mode/source prefix (for example, ``sewer`` for
    # ``vnl_sewer``).  Treat a unique exact basename as an exact match too.
    basename_matches = [
        name for name in matches if _map_basename(name).casefold() == normalized_query
    ]
    if len(basename_matches) == 1:
        return basename_matches[0], []
    if basename_matches:
        return None, basename_matches[:MAX_MAP_CHOICES]

    # ``search_map`` may return fuzzy matches padded with weak alternatives.
    # Compare the user query with the basename so a typo such as ``lionhert``
    # prioritizes ``kz_lionheart`` over unrelated maps.  If the leader is
    # clearly ahead, either select it directly or keep only the close leaders.
    ranked = sorted(
        matches,
        key=lambda name: SequenceMatcher(
            None, normalized_query, _map_basename(name).casefold()
        ).ratio(),
        reverse=True,
    )
    scores = [
        SequenceMatcher(None, normalized_query, _map_basename(name).casefold()).ratio()
        for name in ranked
    ]
    if scores and scores[0] >= _STRONG_MATCH_MIN_SCORE:
        if len(scores) == 1 or scores[0] - scores[1] >= _STRONG_MATCH_GAP:
            return ranked[0], []
        strong = [
            name
            for name, score in zip(ranked, scores)
            if score >= scores[0] - _STRONG_MATCH_GAP
        ]
        if strong:
            return None, strong[:MAX_MAP_CHOICES]

    return None, ranked[:MAX_MAP_CHOICES]

