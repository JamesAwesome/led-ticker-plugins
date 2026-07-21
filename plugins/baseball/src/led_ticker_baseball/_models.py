"""Pure data models and helper functions for MLB scores.

Contains: GameInfo, SeriesInfo, and the pure utility helpers (_ordinal,
_format_inning, _format_game_time, _classify_postponement, _parse_team_abbr,
_fit_team_name) that have no dependency on display classes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from led_ticker.plugin import Canvas, Font

from led_ticker_baseball.teams import MLB_TEAM_NAMES


@dataclass
class GameInfo:
    home_abbr: str
    away_abbr: str
    home_score: int | None = None
    away_score: int | None = None
    state: str = "preview"  # "final", "live", "preview", "postponed"
    game_type: str = "R"  # R=regular, S=spring, A=all-star, P+=postseason
    inning: str | None = None
    balls: int = 0
    strikes: int = 0
    outs: int = 0
    on_first: bool = False
    on_second: bool = False
    on_third: bool = False
    start_time: datetime | None = None
    game_pk: int = 0
    # For state="postponed": short reason like "Rain" or "" if unknown
    postpone_reason: str = ""
    # For state="postponed": short tag like "PPD", "SUSP", "CANC"
    postpone_tag: str = "PPD"
    # ABS challenge counts (None = system not in effect / data unavailable)
    home_challenges: int | None = None
    away_challenges: int | None = None
    # Series win counts by SIDE (away/home), not by monitored-team
    # perspective — set by MLBScoreMonitor._series_sides() before handing
    # the game to MLBGameCard, so the two_row legacy delegation can map
    # them back onto whichever side is "our" team.
    series_away_wins: int = 0
    series_home_wins: int = 0


@dataclass
class SeriesInfo:
    opponent_abbr: str
    games: list[GameInfo] = field(default_factory=list)
    team_wins: int = 0
    team_losses: int = 0


def _ordinal(n: int) -> str:
    """Convert integer to ordinal string: 1st, 2nd, 3rd, etc."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd'][min(n % 10, 4)] if n % 10 < 4 else 'th'}"


def _format_inning(inning_num: int, half: str) -> str:
    """Format inning display: '▲5', '▼7'."""
    arrow = "▲" if half == "top" else "▼"
    return f"{arrow}{inning_num}"


def _format_game_time(dt: datetime, tz: ZoneInfo) -> str:
    """Format game time relative to now."""
    now = datetime.now(tz)
    local = dt.astimezone(tz)

    if local.date() == now.date():
        return f"Today {local.strftime('%-I:%M %p')}"
    if local.date() == (now + timedelta(days=1)).date():
        return f"Tmrw {local.strftime('%-I:%M %p')}"
    days_out = (local.date() - now.date()).days
    if days_out <= 6:
        return local.strftime("%a %-I:%M %p")
    return local.strftime("%b %-d %-I:%M %p")


def _classify_postponement(detailed_state: str) -> tuple[str | None, str]:
    """Map a `status.detailedState` string to (game_state, short_tag).

    Returns (None, "PPD") for non-postponement states; the caller should
    fall back to abstractGameState in that case.

    Examples of detailedState values from the MLB API:
      "Postponed"                  → ("postponed", "PPD")
      "Cancelled"                  → ("postponed", "CANC")
      "Suspended"                  → ("postponed", "SUSP")
      "Suspended: Rain"            → ("postponed", "SUSP")
      "Completed Early"            → ("postponed", "EARLY")
      "Completed Early: Rain"      → ("postponed", "EARLY")
    """
    s = detailed_state.lower()
    if "postponed" in s:
        return "postponed", "PPD"
    if "cancelled" in s or "canceled" in s:
        return "postponed", "CANC"
    if "suspended" in s:
        return "postponed", "SUSP"
    if "completed early" in s:
        return "postponed", "EARLY"
    return None, "PPD"


def _parse_team_abbr(team_data: dict[str, Any]) -> str:
    """Extract team abbreviation from MLB API team data."""
    return team_data.get("abbreviation", "???")


def _fit_team_name(abbr: str, zone_w: int, font: Font, canvas: Canvas) -> str:
    """Return the short team name if it fits in zone_w logical pixels, else abbr."""
    from led_ticker.plugin import measure_width

    name = MLB_TEAM_NAMES.get(abbr, abbr)
    return name if measure_width(font, name, canvas) <= zone_w else abbr


# --- demo=true fixture data (baseball.scores) ---
#
# Curated for the docs showcase + on-demand hardware validation: one
# fictional home series (BOS hosting NYY) whose three games span every
# GameInfo state the card renderers (scoreboard / two_row / crawl, plus the
# legacy scale-1 text builders) branch on — an already-decided opener, a
# live nightcap with runners on and a full count, and a still-to-come
# getaway game. All three share the same home/away pairing so
# `_build_series_title`'s "AWAY @ HOME" naming (rather than the neutral
# "vs" fallback) and the series win/loss record both render.
DEMO_TEAM: str = "NYY"
DEMO_OPPONENT: str = "BOS"


def build_demo_series(tz: ZoneInfo) -> SeriesInfo:
    """Build a fresh demo SeriesInfo (NYY @ BOS) for `demo = true` widgets.

    A function, not a static module list, for two reasons: GameInfo is a
    plain MUTABLE dataclass (the real update() path mutates
    `series_away_wins`/`series_home_wins` in place via `_series_sides`), so
    sharing one module-level list across widget instances/tests would let
    them stomp on each other's state; and `start_time` is relative to
    "now" so the live/final/preview game times keep reading as
    yesterday/right-now/tomorrow regardless of when the demo is loaded.
    """
    now = datetime.now(tz)
    game_final = GameInfo(
        home_abbr=DEMO_OPPONENT,
        away_abbr=DEMO_TEAM,
        home_score=2,
        away_score=7,
        state="final",
        start_time=now - timedelta(days=1, hours=3),
        game_pk=1,
    )
    game_live = GameInfo(
        home_abbr=DEMO_OPPONENT,
        away_abbr=DEMO_TEAM,
        home_score=4,
        away_score=3,
        state="live",
        inning="▼8",
        balls=3,
        strikes=2,
        outs=2,
        on_first=True,
        on_second=True,
        on_third=False,
        start_time=now - timedelta(hours=2),
        game_pk=2,
        home_challenges=1,
        away_challenges=2,
    )
    game_preview = GameInfo(
        home_abbr=DEMO_OPPONENT,
        away_abbr=DEMO_TEAM,
        state="preview",
        start_time=now + timedelta(days=1, hours=4),
        game_pk=3,
    )
    return SeriesInfo(
        opponent_abbr=DEMO_OPPONENT,
        games=[game_final, game_live, game_preview],
        team_wins=1,
        team_losses=0,
    )
