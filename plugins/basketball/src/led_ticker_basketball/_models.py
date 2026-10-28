"""Pure data model + helpers for basketball.scores.

`GameInfo` is the one shape every renderer consumes. `parse_event` builds it
from one ESPN scoreboard event (and, through the same code, from one event of
the per-team `schedule` feed, whose scores are objects rather than strings and
whose records live under `record` rather than `records`). Every field is read
through `.get` with a default: a sparse or junk payload degrades to defaults,
never raises.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_STATE_MAP: dict[str, str] = {"pre": "future", "in": "live", "post": "final"}
_SHORT_STATUS: dict[str, str] = {
    "STATUS_HALFTIME": "HALF",
    "STATUS_DELAYED": "DELAY",
    "STATUS_SUSPENDED": "SUSP",
    "STATUS_POSTPONED": "PPD",
    "STATUS_CANCELED": "CANC",
}
_NO_CLOCK_STATUSES = frozenset(
    {"STATUS_HALFTIME", "STATUS_END_PERIOD", "STATUS_DELAYED", "STATUS_SUSPENDED"}
)
_PERIODS = 4
_CLUTCH_SECONDS = 120.0
_CLUTCH_MARGIN = 5
_ESPN_TZ = ZoneInfo("America/New_York")  # the feed's anchor for date-only tipoffs

# The feed carries no end time: a final's hold runs from tip-off + this.
GAME_LENGTH = timedelta(hours=2, minutes=30)


@dataclass(frozen=True)
class Leader:
    name: str  # ESPN athlete.shortName upper-cased, e.g. "J. EMBIID"
    points: int


@dataclass(frozen=True)
class FinalEvent:
    key: str
    game_id: str
    winner: str
    loser: str
    away_score: int
    home_score: int
    final_ot: bool
    leader: Leader | None  # the winner's points leader


@dataclass(frozen=True)
class GameInfo:
    game_id: str
    state: str  # "future" | "live" | "final"
    status: str  # ESPN status name, e.g. STATUS_HALFTIME
    away: str
    home: str
    away_score: int
    home_score: int
    period: int
    clock: str
    start_utc: datetime | None
    time_tbd: bool
    venue: str
    broadcast: str
    away_record: str
    home_record: str
    final_ot: bool
    neutral_site: bool
    away_leader: Leader | None = None
    home_leader: Leader | None = None
    away_linescores: tuple[int, ...] = ()
    home_linescores: tuple[int, ...] = ()
    polled_at: float = 0.0


# ---------------------------------------------------------------- helpers


def _dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _int(v: Any, default: int | None = 0) -> int | None:
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    try:
        if isinstance(v, (float, str)):
            return int(float(v))
    except ValueError, OverflowError:
        return default
    return default


def _score(v: Any) -> int:
    """Scoreboard scores are strings ("98"); schedule scores are objects
    ({"value": 106.0, "displayValue": "106"}); pre-game both may be absent."""
    if isinstance(v, dict):
        v = v.get("value", v.get("displayValue"))
    return _int(v) or 0


def _parse_start(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def period_label(period: int, status: str) -> str:
    short = _SHORT_STATUS.get(status)
    if short is not None:
        return short
    if status == "STATUS_END_PERIOD":
        return f"END {period_label(period, '')}"
    if period > _PERIODS:
        n = period - _PERIODS
        return "OT" if n <= 1 else f"{n}OT"
    return f"Q{max(period, 1)}"


def clock_seconds(clock: str) -> float | None:
    """`"2:13"` -> 133.0, `"45.3"` -> 45.3 (sub-minute clocks drop the colon),
    anything unparseable -> None."""
    text = clock.strip() if isinstance(clock, str) else ""
    if not text:
        return None
    try:
        if ":" in text:
            mins, _, secs = text.partition(":")
            return int(mins) * 60 + float(secs)
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------- parsing


def _record(k: dict) -> str:
    """Scoreboard: `records[]{type, summary}`; schedule: `record[]{type,
    displayValue}`. Take the `total` entry of whichever is present."""
    for r in _list(k.get("records")) + _list(k.get("record")):
        r = _dict(r)
        if r.get("type") == "total":
            text = _str(r.get("summary")) or _str(r.get("displayValue"))
            if text:
                return text
    return ""


def _leader(k: dict) -> Leader | None:
    """The in-game/final `points` leader. Pregame competitors carry
    `pointsPerGame` (a season average) instead, which is deliberately ignored."""
    for entry in _list(k.get("leaders")):
        entry = _dict(entry)
        if entry.get("name") != "points":
            continue
        top = _list(entry.get("leaders"))
        if not top:
            return None
        top0 = _dict(top[0])
        name = _str(_dict(top0.get("athlete")).get("shortName")).upper()
        points = _int(top0.get("displayValue"), None)
        if not name or points is None:
            return None
        return Leader(name, points)
    return None


def _linescores(k: dict) -> tuple[int, ...]:
    return tuple(_int(_dict(ls).get("value")) or 0 for ls in _list(k.get("linescores")))


def parse_event(e: dict, *, polled_at: float) -> GameInfo | None:
    e = _dict(e)
    game_id = _str(e.get("id")) or (str(e["id"]) if "id" in e else "")
    comps = _list(e.get("competitions"))
    c = _dict(comps[0]) if comps else {}
    sides: dict[str, dict] = {}
    for k in _list(c.get("competitors")):
        k = _dict(k)
        ha = _str(k.get("homeAway"))
        if ha in ("home", "away") and ha not in sides:
            sides[ha] = k
    away_k, home_k = _dict(sides.get("away")), _dict(sides.get("home"))
    away = _str(_dict(away_k.get("team")).get("abbreviation")).upper()
    home = _str(_dict(home_k.get("team")).get("abbreviation")).upper()
    if not game_id or not away or not home:
        return None

    status = _dict(e.get("status")) or _dict(c.get("status"))
    stype = _dict(status.get("type"))
    name = _str(stype.get("name"))
    state = _STATE_MAP.get(_str(stype.get("state")), "future")
    if name == "STATUS_POSTPONED":
        state = "future"
    elif name == "STATUS_CANCELED":
        state = "final"
    period = _int(status.get("period")) or 0
    detail = _str(stype.get("detail"))
    short_detail = _str(stype.get("shortDetail"))
    alt_detail = _str(stype.get("altDetail"))
    final_ot = state == "final" and (
        period > _PERIODS or "OT" in alt_detail or "/OT" in detail
    )
    time_tbd = (
        name == "STATUS_POSTPONED"
        or short_detail.upper() == "TBD"
        or detail.upper().endswith("TBD")
    )

    broadcasts = _list(c.get("broadcasts"))
    names = _list(_dict(broadcasts[0]).get("names")) if broadcasts else []
    broadcast = _str(names[0]) if names else ""
    if not broadcast and broadcasts:
        broadcast = _str(_dict(_dict(broadcasts[0]).get("media")).get("shortName"))

    return GameInfo(
        game_id=game_id,
        state=state,
        status=name,
        away=away,
        home=home,
        away_score=_score(away_k.get("score")),
        home_score=_score(home_k.get("score")),
        period=period,
        clock=_str(status.get("displayClock")),
        start_utc=_parse_start(e.get("date") or c.get("date")),
        time_tbd=time_tbd,
        venue=_str(_dict(c.get("venue")).get("fullName")),
        broadcast=broadcast,
        away_record=_record(away_k),
        home_record=_record(home_k),
        final_ot=final_ot,
        neutral_site=c.get("neutralSite") is True,
        away_leader=_leader(away_k),
        home_leader=_leader(home_k),
        away_linescores=_linescores(away_k),
        home_linescores=_linescores(home_k),
        polled_at=polled_at,
    )


# ---------------------------------------------------------------- display


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
        label = period_label(game.period, game.status)
        if game.status in _NO_CLOCK_STATUSES:
            return (label, "")
        return (label, game.clock)
    if game.state == "final":
        if game.status == "STATUS_CANCELED":
            return ("CANC", "")
        return ("FINAL", "OT" if game.final_ot else "")
    if game.status == "STATUS_POSTPONED":
        return ("PPD", "")
    if game.start_utc is None:
        return ("TBD", "")
    if game.time_tbd:
        # ESPN's TBD sentinel is 05:00Z = midnight Eastern: the game's date
        # is the Eastern date whatever the user's zone, and never TONIGHT.
        start = game.start_utc.astimezone(_ESPN_TZ)
        return (f"{start:%a %b} {start.day}".upper(), "TBD")
    now_utc = datetime.fromtimestamp(now, UTC)
    day = day_label(game.start_utc, now_utc, tz)
    return (day, _clock_12h(game.start_utc.astimezone(tz)))


def final_in_hold(g: GameInfo, now_dt: datetime, hold_hours: int) -> bool:
    """A final is still shown `hold_hours` after its estimated end. The ONE
    predicate shared by `scores.select_stories` and the source's next-game
    lookup, so a team never falls between the two."""
    if g.start_utc is None:
        return True  # the source already drops games unseen past the hold
    return now_dt - (g.start_utc + GAME_LENGTH) < timedelta(hours=hold_hours)


def winner(game: GameInfo) -> str | None:
    if game.state != "final" or game.status == "STATUS_CANCELED":
        return None
    if game.away_score == game.home_score:
        return None
    return game.away if game.away_score > game.home_score else game.home


def is_clutch(game: GameInfo) -> bool:
    """Live, Q4 or later, two minutes or less, within five points."""
    if game.state != "live" or game.status != "STATUS_IN_PROGRESS":
        return False
    if game.period < _PERIODS:
        return False
    secs = clock_seconds(game.clock)
    if secs is None or secs > _CLUTCH_SECONDS:
        return False
    return abs(game.away_score - game.home_score) <= _CLUTCH_MARGIN


def leader_text(leader: Leader | None, *, style: str) -> str:
    """`full` -> "J. EMBIID 31 PTS"; `short` -> "EMBIID 31" (initial dropped)."""
    if leader is None:
        return ""
    if style == "full":
        return f"{leader.name} {leader.points} PTS"
    first, _, rest = leader.name.partition(" ")
    surname = rest if first.endswith(".") and rest else leader.name
    return f"{surname} {leader.points}"


def final_event(game: GameInfo) -> FinalEvent | None:
    win = winner(game)
    if win is None:
        return None
    away_won = win == game.away
    return FinalEvent(
        key=game.game_id,
        game_id=game.game_id,
        winner=win,
        loser=game.home if away_won else game.away,
        away_score=game.away_score,
        home_score=game.home_score,
        final_ot=game.final_ot,
        leader=game.away_leader if away_won else game.home_leader,
    )


# ------------------------------------------------------------------- demo


def _demo_game(
    game_id: str,
    state: str,
    status: str,
    *,
    away: str = "PHI",
    home: str = "NY",
    away_score: int = 0,
    home_score: int = 0,
    period: int = 0,
    clock: str = "",
    start_utc: datetime | None = None,
    final_ot: bool = False,
    venue: str = "Madison Square Garden",
    broadcast: str = "ESPN",
    away_record: str = "5-2",
    home_record: str = "4-3",
    away_leader: Leader | None = None,
    home_leader: Leader | None = None,
    away_linescores: tuple[int, ...] = (),
    home_linescores: tuple[int, ...] = (),
    now: float,
) -> GameInfo:
    return GameInfo(
        game_id=game_id,
        state=state,
        status=status,
        away=away,
        home=home,
        away_score=away_score,
        home_score=home_score,
        period=period,
        clock=clock,
        start_utc=start_utc,
        time_tbd=False,
        venue=venue,
        broadcast=broadcast,
        away_record=away_record,
        home_record=home_record,
        final_ot=final_ot,
        neutral_site=False,
        away_leader=away_leader,
        home_leader=home_leader,
        away_linescores=away_linescores,
        home_linescores=home_linescores,
        polled_at=now,
    )


def build_demo_games(now: float) -> tuple[list[GameInfo], FinalEvent]:
    """Four PHI/NY cards: live clutch Q4, halftime, OT final, next game; plus
    the live card's final-score celebration event."""
    tz = ZoneInfo("America/New_York")
    embiid = Leader("J. EMBIID", 31)
    live = _demo_game(
        "demo-live",
        "live",
        "STATUS_IN_PROGRESS",
        away_score=98,
        home_score=101,
        period=4,
        clock="1:48",  # inside the 2:00 clutch window so the demo shows it
        away_leader=embiid,
        home_leader=Leader("J. BRUNSON", 28),
        away_linescores=(24, 26, 25, 23),
        home_linescores=(28, 24, 27, 22),
        now=now,
    )
    halftime = _demo_game(
        "demo-half",
        "live",
        "STATUS_HALFTIME",
        away_score=54,
        home_score=52,
        period=2,
        clock="0.0",
        away_linescores=(28, 26),
        home_linescores=(26, 26),
        now=now,
    )
    final = _demo_game(
        "demo-final-ot",
        "final",
        "STATUS_FINAL",
        away_score=115,
        home_score=118,
        period=5,
        clock="0.0",
        final_ot=True,
        away_leader=Leader("J. EMBIID", 33),
        home_leader=Leader("J. BRUNSON", 36),
        away_linescores=(24, 26, 25, 25, 15),
        home_linescores=(28, 24, 27, 22, 17),
        now=now,
    )
    local = datetime.fromtimestamp(now, UTC).astimezone(tz)
    tomorrow = (local + timedelta(days=1)).replace(
        hour=19, minute=30, second=0, microsecond=0
    )
    future = _demo_game(
        "demo-next",
        "future",
        "STATUS_SCHEDULED",
        away="NY",
        home="PHI",
        away_record="4-3",
        home_record="5-2",
        venue="Xfinity Mobile Arena",
        start_utc=tomorrow.astimezone(UTC),
        now=now,
    )
    celebration = FinalEvent(
        key="demo-live",
        game_id="demo-live",
        winner="PHI",
        loser="NY",
        away_score=112,
        home_score=108,
        final_ot=False,
        leader=embiid,
    )
    return [live, halftime, final, future], celebration
