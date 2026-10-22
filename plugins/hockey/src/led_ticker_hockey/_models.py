"""Pure data model + helpers for hockey.scores.

`GameInfo` is the one shape every renderer consumes. `parse_game` builds it
from one row of the NHL `score` feed (`/v1/score/{date}`), `parse_situation`
from a game's `landing` payload. Every field is read through `.get` with a
default: a sparse or junk payload degrades to defaults, never raises.

Localized fields (`{"default": "PHI"}`) are accepted as either a dict or a
plain string, since the real feed has sent both.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_STATE_MAP: dict[str, str] = {
    "FUT": "future",
    "PRE": "future",
    "LIVE": "live",
    "CRIT": "live",
    "FINAL": "final",
    "OFF": "final",
}

_ORDINALS: dict[int, str] = {1: "1ST", 2: "2ND", 3: "3RD"}


@dataclass(frozen=True)
class Goal:
    key: str
    team: str
    scorer: str
    season_total: int | None
    assists: tuple[str, ...]
    period_label: str
    time_in_period: str
    strength: str
    empty_net: bool
    away_score: int
    home_score: int


@dataclass(frozen=True)
class Situation:
    pp_team: str | None
    pp_seconds: int | None
    en_team: str | None


@dataclass(frozen=True)
class GameInfo:
    game_id: int
    state: str  # "future" | "live" | "final"
    away: str
    home: str
    away_score: int
    home_score: int
    away_sog: int | None
    home_sog: int | None
    period: int
    period_type: str
    clock_seconds: int | None
    clock_running: bool
    in_intermission: bool
    start_utc: datetime | None
    venue: str
    final_type: str | None  # None | "OT" | "SO"
    goals: tuple[Goal, ...]
    situation: Situation | None = None
    polled_at: float = 0.0


# ---------------------------------------------------------------- helpers


def _dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _loc(v: Any) -> str:
    """A localized field: `{"default": x}` or a bare string."""
    if isinstance(v, dict):
        v = v.get("default")
    return v.strip() if isinstance(v, str) else ""


def _int(v: Any, default: int | None = 0) -> int | None:
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return default
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return default
    return default


def _last_name(d: Any) -> str:
    """Upper-cased last name from `lastName`, else the tail of `name`."""
    if isinstance(d, str):
        full = d.strip()
        return full.split()[-1].upper() if full else ""
    d = _dict(d)
    last = _loc(d.get("lastName"))
    if last:
        return last.upper()
    full = _loc(d.get("name"))
    return full.split()[-1].upper() if full else ""


def _parse_start(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def period_label(period: int, period_type: str) -> str:
    if period_type == "SO":
        return "SO"
    if period_type == "OT":
        n = period - 3
        if n <= 1:
            return "OT"
        return f"{n}OT"
    return _ORDINALS.get(period, f"P{period}")


# ---------------------------------------------------------------- parsing


def _parse_goal(g: Any) -> Goal | None:
    if not isinstance(g, dict):
        return None
    desc = _dict(g.get("periodDescriptor"))
    period = _int(g.get("period"), None)
    if period is None:
        period = _int(desc.get("number"), 0)
    ptype = desc.get("periodType")
    ptype = ptype if isinstance(ptype, str) and ptype else "REG"
    time_in = g.get("timeInPeriod")
    time_in = time_in if isinstance(time_in, str) else ""
    assists_raw = g.get("assists")
    assists = tuple(
        n
        for n in (
            _last_name(a)
            for a in (assists_raw if isinstance(assists_raw, list) else [])
        )
        if n
    )
    strength = g.get("strength")
    return Goal(
        key=f"{period}:{time_in}:{g.get('playerId', '')}",
        team=_loc(g.get("teamAbbrev")),
        scorer=_last_name(g),
        season_total=_int(g.get("goalsToDate"), None),
        assists=assists,
        period_label=period_label(period or 0, ptype),
        time_in_period=time_in,
        strength=strength if isinstance(strength, str) and strength else "ev",
        empty_net=g.get("goalModifier") == "empty-net",
        away_score=_int(g.get("awayScore")) or 0,
        home_score=_int(g.get("homeScore")) or 0,
    )


def parse_game(row: dict, *, polled_at: float) -> GameInfo | None:
    row = _dict(row)
    game_id = _int(row.get("id"), None)
    away_t = _dict(row.get("awayTeam"))
    home_t = _dict(row.get("homeTeam"))
    away = _loc(away_t.get("abbrev"))
    home = _loc(home_t.get("abbrev"))
    if not game_id or not away or not home:
        return None

    raw_state = row.get("gameState")
    state = (
        _STATE_MAP.get(raw_state, "future") if isinstance(raw_state, str) else "future"
    )

    desc = _dict(row.get("periodDescriptor"))
    period = _int(desc.get("number"), None)
    if period is None:
        period = _int(row.get("period"), 0) or 0
    ptype = desc.get("periodType")
    ptype = ptype if isinstance(ptype, str) and ptype else "REG"

    clock = _dict(row.get("clock"))
    final_type = None
    if state == "final":
        last = _dict(row.get("gameOutcome")).get("lastPeriodType") or ptype
        final_type = last if last in ("OT", "SO") else None

    goals_raw = row.get("goals")
    goals = tuple(
        g
        for g in (
            _parse_goal(x) for x in (goals_raw if isinstance(goals_raw, list) else [])
        )
        if g is not None
    )

    return GameInfo(
        game_id=game_id,
        state=state,
        away=away,
        home=home,
        away_score=_int(away_t.get("score")) or 0,
        home_score=_int(home_t.get("score")) or 0,
        away_sog=_int(away_t.get("sog"), None),
        home_sog=_int(home_t.get("sog"), None),
        period=period,
        period_type=ptype,
        clock_seconds=_int(clock.get("secondsRemaining"), None),
        clock_running=clock.get("running") is True,
        in_intermission=clock.get("inIntermission") is True,
        start_utc=_parse_start(row.get("startTimeUTC")),
        venue=_loc(row.get("venue")),
        final_type=final_type,
        goals=goals,
        polled_at=polled_at,
    )


def parse_situation(landing: dict) -> Situation | None:
    sit = _dict(_dict(landing).get("situation"))
    code = sit.get("situationCode")
    if not isinstance(code, str) or len(code) != 4 or not code.isdigit():
        return None
    away_g, away_s, home_s, home_g = (int(c) for c in code)
    away = _loc(_dict(sit.get("awayTeam")).get("abbrev")) or None
    home = _loc(_dict(sit.get("homeTeam")).get("abbrev")) or None

    # Zero skaters is a nonsense code, not an empty net.
    en_team = None
    if away_g == 0 and away_s > 0:
        en_team = away
    elif home_g == 0 and home_s > 0:
        en_team = home

    # Power play = more EFFECTIVE skaters (a pulled goalie's extra attacker
    # doesn't count, so 6v5 with an empty net is 5v5, not a PP).
    eff_away = away_s - (1 if away_g == 0 else 0)
    eff_home = home_s - (1 if home_g == 0 else 0)
    pp_team = None
    if eff_away != eff_home and away_s > 0 and home_s > 0:
        pp_team = home if eff_home > eff_away else away
    pp_seconds = _int(sit.get("secondsRemaining"), None) if pp_team else None
    return Situation(pp_team=pp_team, pp_seconds=pp_seconds, en_team=en_team)


# ---------------------------------------------------------------- display


def _tick(seconds: int | None, game: GameInfo, now: float) -> int | None:
    if seconds is None:
        return None
    if game.clock_running:
        return max(0, seconds - int(max(0.0, now - game.polled_at)))
    return seconds


def live_clock_seconds(game: GameInfo, now: float) -> int | None:
    return _tick(game.clock_seconds, game, now)


def live_pp_seconds(game: GameInfo, now: float) -> int | None:
    if game.situation is None:
        return None
    return _tick(game.situation.pp_seconds, game, now)


def fmt_clock(seconds: int | None) -> str:
    if seconds is None:
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


def day_label(start_utc: datetime, now_utc: datetime, tz: ZoneInfo) -> str:
    start = start_utc.astimezone(tz)
    if start.date() == now_utc.astimezone(tz).date():
        return "TONIGHT" if start.hour >= 17 else "TODAY"
    return f"{start:%a %b} {start.day}".upper()


def _clock_12h(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def status_lines(game: GameInfo, now: float, tz: ZoneInfo) -> tuple[str, str]:
    if game.state == "live":
        label = period_label(game.period, game.period_type)
        if game.in_intermission:
            label = f"{label} INT"
        return (label, fmt_clock(live_clock_seconds(game, now)))
    if game.state == "final":
        return ("FINAL", game.final_type or "")
    if game.start_utc is None:
        return ("TBD", "")
    now_utc = datetime.fromtimestamp(now, UTC)
    return (
        day_label(game.start_utc, now_utc, tz),
        _clock_12h(game.start_utc.astimezone(tz)),
    )


def winner(game: GameInfo) -> str | None:
    if game.state != "final" or game.away_score == game.home_score:
        return None
    return game.away if game.away_score > game.home_score else game.home


# ------------------------------------------------------------------- demo


def build_demo_games(now: float) -> list[GameInfo]:
    """Four PHI/NYI games covering live, intermission, OT final, and future."""
    tz = ZoneInfo("America/New_York")
    goals = (
        Goal(
            key="2:7:26:8477404",
            team="PHI",
            scorer="KONECNY",
            season_total=5,
            assists=("MICHKOV", "SANHEIM"),
            period_label="2ND",
            time_in_period="7:26",
            strength="ev",
            empty_net=False,
            away_score=2,
            home_score=1,
        ),
    )
    base = {
        "away": "PHI",
        "home": "NYI",
        "venue": "UBS Arena",
        "polled_at": now,
    }
    live = GameInfo(
        game_id=1,
        state="live",
        away_score=2,
        home_score=1,
        away_sog=18,
        home_sog=22,
        period=2,
        period_type="REG",
        clock_seconds=754,
        clock_running=True,
        in_intermission=False,
        start_utc=None,
        final_type=None,
        goals=goals,
        situation=Situation(pp_team="NYI", pp_seconds=102, en_team=None),
        **base,
    )
    intermission = GameInfo(
        game_id=2,
        state="live",
        away_score=1,
        home_score=1,
        away_sog=11,
        home_sog=9,
        period=1,
        period_type="REG",
        clock_seconds=1020,
        clock_running=False,
        in_intermission=True,
        start_utc=None,
        final_type=None,
        goals=(),
        **base,
    )
    final = GameInfo(
        game_id=3,
        state="final",
        away_score=3,
        home_score=2,
        away_sog=31,
        home_sog=27,
        period=4,
        period_type="OT",
        clock_seconds=None,
        clock_running=False,
        in_intermission=False,
        start_utc=None,
        final_type="OT",
        goals=(),
        **base,
    )
    local = datetime.fromtimestamp(now, UTC).astimezone(tz)
    days = (4 - local.weekday()) % 7 or 7  # next Friday, never today
    friday = (local + timedelta(days=days)).replace(
        hour=19, minute=0, second=0, microsecond=0
    )
    future = GameInfo(
        game_id=4,
        state="future",
        away_score=0,
        home_score=0,
        away_sog=None,
        home_sog=None,
        period=0,
        period_type="REG",
        clock_seconds=None,
        clock_running=False,
        in_intermission=False,
        start_utc=friday.astimezone(UTC),
        final_type=None,
        goals=(),
        **base,
    )
    return [live, intermission, final, future]
