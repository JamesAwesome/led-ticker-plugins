"""Shared MLB team data, lazy color palette, and team-ID resolution.

This module owns what the scores, standings, and promotions widgets share:
the MLB API base URLs, the per-team primary-color / name tables, the
name->abbreviation lookup, the lazy WIN/LOSS/LIVE/CHALLENGE palette, the
color helpers built on top of them, and the async `resolve_team_id()`
abbreviation->ID lookup. Keeping them here means no widget reaches into
another widget for shared data.
"""

import logging

import aiohttp
from led_ticker.plugin import Color, colors, make_color

logger: logging.Logger = logging.getLogger(__name__)

# ColorTuple is a plain type alias; it is not on the public surface, so define
# it locally (was led_ticker._types.ColorTuple).
ColorTuple = tuple[int, int, int]

MLB_API: str = "https://statsapi.mlb.com/api/v1"
_MLB_LIVE_API: str = "https://statsapi.mlb.com/api/v1.1"

_team_palette = colors.lazy_palette(
    {
        "WIN_COLOR": (46, 200, 46),
        "LOSS_COLOR": (220, 30, 30),
        "LIVE_COLOR": (255, 40, 40),
        "CHALLENGE_COLOR": (255, 140, 0),  # orange — remaining ABS challenge dash
        "CHALLENGE_USED": (140, 140, 140),  # grey — used ABS challenge dash
    }
)


# PEP 562: external imports of palette names (e.g. WIN_COLOR) from this
# module resolve through __getattr__ on first access. Bare-name use inside this
# module must call `_team_palette(...)` directly because PEP 562 doesn't
# fire for in-module name lookups.
def __getattr__(name: str) -> Color:
    return _team_palette(name)


# All 30 MLB team primary colors
MLB_TEAM_COLORS: dict[str, ColorTuple] = {
    "ARI": (167, 25, 48),
    "ATL": (206, 17, 65),
    "BAL": (223, 70, 1),
    "BOS": (189, 48, 57),
    "CHC": (14, 51, 134),
    "CIN": (198, 1, 31),
    "CLE": (0, 56, 93),
    "COL": (51, 0, 111),
    "CWS": (39, 37, 31),
    "DET": (12, 35, 64),
    "HOU": (235, 110, 31),
    "KC": (0, 70, 135),
    "LAA": (186, 0, 33),
    "LAD": (0, 90, 156),
    "MIA": (0, 163, 224),
    "MIL": (18, 40, 75),
    "MIN": (0, 43, 92),
    "NYM": (0, 45, 114),
    "NYY": (0, 48, 135),
    "OAK": (0, 56, 49),
    "PHI": (228, 24, 40),
    "PIT": (253, 184, 39),
    "SD": (47, 36, 28),
    "SEA": (0, 92, 92),
    "SF": (253, 90, 30),
    "STL": (196, 30, 58),
    "TB": (9, 44, 92),
    "TEX": (0, 50, 120),
    "TOR": (19, 74, 142),
    "WSH": (171, 0, 3),
}

# Full team names for display
MLB_TEAM_NAMES: dict[str, str] = {
    "ARI": "D-backs",
    "ATL": "Braves",
    "BAL": "Orioles",
    "BOS": "Red Sox",
    "CHC": "Cubs",
    "CIN": "Reds",
    "CLE": "Guardians",
    "COL": "Rockies",
    "CWS": "White Sox",
    "DET": "Tigers",
    "HOU": "Astros",
    "KC": "Royals",
    "LAA": "Angels",
    "LAD": "Dodgers",
    "MIA": "Marlins",
    "MIL": "Brewers",
    "MIN": "Twins",
    "NYM": "Mets",
    "NYY": "Yankees",
    "OAK": "Athletics",
    "PHI": "Phillies",
    "PIT": "Pirates",
    "SD": "Padres",
    "SEA": "Mariners",
    "SF": "Giants",
    "STL": "Cardinals",
    "TB": "Rays",
    "TEX": "Rangers",
    "TOR": "Blue Jays",
    "WSH": "Nationals",
}


# API team name -> abbreviation (standings API returns short names)
MLB_NAME_TO_ABBR: dict[str, str] = {v: k for k, v in MLB_TEAM_NAMES.items()}


def _lift_color(r: int, g: int, b: int, min_max: int = 120) -> tuple[int, int, int]:
    """Scale dark colors proportionally so the brightest channel >= min_max.

    Preserves hue and saturation; teams already above the threshold are unchanged.
    At display brightness=60, min_max=120 ensures the peak channel renders at ~72
    on the physical panel — clearly legible against a black background.
    """
    peak = max(r, g, b)
    if peak == 0 or peak >= min_max:
        return r, g, b
    scale = min_max / peak
    return (
        min(255, round(r * scale)),
        min(255, round(g * scale)),
        min(255, round(b * scale)),
    )


def _team_color(abbr: str) -> Color:
    """Get graphics.Color for a team abbreviation."""
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    r, g, b = _lift_color(r, g, b)
    return make_color(r, g, b)


def _team_color_by_name(name: str) -> Color:
    """Get graphics.Color for an API team name (e.g. 'Mets')."""
    abbr = MLB_NAME_TO_ABBR.get(name, "")
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    r, g, b = _lift_color(r, g, b)
    return make_color(r, g, b)


async def resolve_team_id(session: aiohttp.ClientSession, abbr: str) -> int | None:
    """Resolve a team abbreviation (e.g. "TOR") to its MLB StatsAPI team ID.

    Returns None when the abbreviation is unknown or the request fails.
    """
    url = f"{MLB_API}/teams?sportId=1"
    try:
        async with session.get(url) as resp:
            data = await resp.json()
    except Exception:
        logger.exception("Failed to resolve team ID for %s", abbr)
        return None
    for t in data.get("teams", []):
        if t.get("abbreviation") == abbr:
            team_id = t.get("id")
            return team_id if isinstance(team_id, int) else None
    logger.warning("Team %s not found in MLB API", abbr)
    return None
