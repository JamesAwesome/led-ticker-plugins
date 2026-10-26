"""Pure data model + helpers for football.scores.

`GameInfo` is the one shape every renderer consumes. `parse_event` builds it
from one ESPN scoreboard event (and, through the same code, from one event of
the per-team `schedule` feed, whose scores are objects rather than strings).
Every field is read through `.get` with a default: a sparse or junk payload
degrades to defaults, never raises.

Scoring plays are NOT in the scoreboard payload. `diff_scores` derives them
from the change in a team's score between two polls (the table in the design
spec) and decorates them with `situation.lastPlay` when that play matches.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from led_ticker_football.teams import team_by_id

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


@dataclass(frozen=True)
class LastPlay:
    text: str
    score_value: int
    team: str
    type_text: str


@dataclass(frozen=True)
class Situation:
    possession: str | None
    down_distance: str
    spot: str
    red_zone: bool
    away_timeouts: int | None
    home_timeouts: int | None
    last_play: LastPlay | None


@dataclass(frozen=True)
class ScoringPlay:
    key: str
    team: str
    kind: str  # "TD" | "FG" | "SAFETY"
    extra: str  # "" | "+PAT" | "+2PT"
    text: str
    period_label: str
    clock: str
    away_score: int
    home_score: int


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
    week: int | None
    situation: Situation | None = None
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
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return default
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except ValueError:
            return default
    return default


def _score(v: Any) -> int:
    """Scoreboard scores are strings ("24"); schedule scores are objects
    ({"value": 24.0, "displayValue": "24"}); pre-game both may be absent."""
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
        return f"END Q{period}"
    if period > _PERIODS:
        n = period - _PERIODS
        return "OT" if n <= 1 else f"{n}OT"
    return f"Q{max(period, 1)}"


# ---------------------------------------------------------------- parsing


def _parse_last_play(v: Any) -> LastPlay | None:
    lp = _dict(v)
    if not lp:
        return None
    return LastPlay(
        text=_str(lp.get("text")),
        score_value=_int(lp.get("scoreValue")) or 0,
        team=team_by_id(_str(_dict(lp.get("team")).get("id"))) or "",
        type_text=_str(_dict(lp.get("type")).get("text")),
    )


def _parse_situation(
    c: dict, ids: dict[str, str], away: str, home: str
) -> Situation | None:
    """`ids` maps ESPN team id -> abbreviation for the two competitors (the
    payload's own ids win over the static table so a relocated team still
    resolves)."""
    sit = _dict(c.get("situation"))
    if not sit:
        return None
    poss_id = sit.get("possession")
    possession = None
    if poss_id is not None:
        pid = str(poss_id)
        possession = ids.get(pid) or team_by_id(pid)
        if possession not in (away, home):
            possession = None
    down = _int(sit.get("down"), None)
    dd = _str(sit.get("shortDownDistanceText")).upper()
    if down is not None and down < 0 and not dd:
        dd = ""
    return Situation(
        possession=possession,
        down_distance=dd,
        spot=_str(sit.get("possessionText")),
        red_zone=sit.get("isRedZone") is True,
        away_timeouts=_int(sit.get("awayTimeouts"), None),
        home_timeouts=_int(sit.get("homeTimeouts"), None),
        last_play=_parse_last_play(sit.get("lastPlay")),
    )


def _record(k: dict) -> str:
    for r in _list(k.get("records")):
        r = _dict(r)
        if r.get("type") == "total":
            return _str(r.get("summary"))
    return ""


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
    raw_state = _str(stype.get("state"))
    state = _STATE_MAP.get(raw_state, "future")
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

    ids = {
        _str(_dict(k.get("team")).get("id")) or _str(k.get("id")): ab
        for k, ab in ((away_k, away), (home_k, home))
    }
    ids.pop("", None)
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
        week=_int(_dict(e.get("week")).get("number"), None),
        situation=_parse_situation(c, ids, away, home) if state == "live" else None,
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
    now_utc = datetime.fromtimestamp(now, UTC)
    day = day_label(game.start_utc, now_utc, tz)
    if game.time_tbd:
        return (day, "TBD")
    return (day, _clock_12h(game.start_utc.astimezone(tz)))


# The feed carries no end time: a final's hold runs from kickoff + this.
GAME_LENGTH = timedelta(hours=3, minutes=30)


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


# ----------------------------------------------------------------- scoring


def _play_text(game: GameInfo, team: str) -> str:
    """Upper-cased `lastPlay.text` with the kick/conversion parenthetical
    stripped, when the last play was this team's score; else ""."""
    sit = game.situation
    lp = sit.last_play if sit is not None else None
    if lp is None or lp.score_value <= 0 or lp.team != team:
        return ""
    text = lp.text
    if "(" in text:
        text = text[: text.index("(")]
    return " ".join(text.upper().split())


def _play(game: GameInfo, team: str, kind: str, extra: str) -> ScoringPlay:
    return ScoringPlay(
        key=f"{game.game_id}:{game.away_score}:{game.home_score}",
        team=team,
        kind=kind,
        extra=extra,
        text=_play_text(game, team),
        period_label=period_label(game.period, game.status),
        clock=game.clock,
        away_score=game.away_score,
        home_score=game.home_score,
    )


def diff_scores(
    game: GameInfo, prev: tuple[int, int], last_td: ScoringPlay | None
) -> tuple[list[ScoringPlay], ScoringPlay | None]:
    """Scoring plays implied by the score change `prev` -> `game`.

    Returns `(new_plays, follow_up)`: `follow_up` is `last_td` re-keyed at
    the new score with its `extra` filled in when the change is that
    touchdown's extra point (+1) or two-point conversion (+2). A negative
    change is a correction: nothing is produced. Never raises.
    """
    new: list[ScoringPlay] = []
    follow: ScoringPlay | None = None
    for team, old, cur in (
        (game.away, prev[0], game.away_score),
        (game.home, prev[1], game.home_score),
    ):
        delta = cur - old
        if delta <= 0:
            continue
        open_td = last_td if last_td is not None and last_td.team == team else None
        if delta in (1, 2) and open_td is not None and not open_td.extra:
            follow = ScoringPlay(
                key=f"{game.game_id}:{game.away_score}:{game.home_score}",
                team=team,
                kind="TD",
                extra="+PAT" if delta == 1 else "+2PT",
                text=open_td.text,
                period_label=open_td.period_label,
                clock=open_td.clock,
                away_score=game.away_score,
                home_score=game.home_score,
            )
            continue
        if delta == 3:
            new.append(_play(game, team, "FG", ""))
        elif delta == 2:
            new.append(_play(game, team, "SAFETY", ""))
        elif delta == 6:
            new.append(_play(game, team, "TD", ""))
        elif delta == 7:
            new.append(_play(game, team, "TD", "+PAT"))
        elif delta == 8:
            new.append(_play(game, team, "TD", "+2PT"))
        elif delta >= 6:
            new.append(_play(game, team, "TD", ""))  # two scores in one poll
        else:  # +1, +4, +5 with nothing to attach to: a correction-shaped bump
            new.append(_play(game, team, "FG" if delta >= 3 else "SAFETY", ""))
    return new, follow


# ------------------------------------------------------------------- demo


def _demo_game(
    game_id: str,
    state: str,
    status: str,
    *,
    away: str = "PHI",
    home: str = "NYG",
    away_score: int = 0,
    home_score: int = 0,
    period: int = 0,
    clock: str = "",
    start_utc: datetime | None = None,
    final_ot: bool = False,
    venue: str = "MetLife Stadium",
    away_record: str = "5-2",
    home_record: str = "4-3",
    week: int = 8,
    situation: Situation | None = None,
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
        broadcast="FOX",
        away_record=away_record,
        home_record=home_record,
        final_ot=final_ot,
        neutral_site=False,
        week=week,
        situation=situation,
        polled_at=now,
    )


def build_demo_games(now: float) -> tuple[list[GameInfo], ScoringPlay]:
    """Five PHI/NYG cards: live Q4, halftime, OT final, next game, bye week;
    plus the live card's touchdown play for the celebration."""
    tz = ZoneInfo("America/New_York")
    td_play = LastPlay(
        text="Jalen Hurts 12 Yd Rush (Jake Elliott Kick)",
        score_value=6,
        team="PHI",
        type_text="Rushing Touchdown",
    )
    live = _demo_game(
        "demo-live",
        "live",
        "STATUS_IN_PROGRESS",
        away_score=20,
        home_score=17,
        period=4,
        clock="2:13",
        situation=Situation(
            possession="NYG",
            down_distance="2ND & 7",
            spot="PHI 24",
            red_zone=False,
            away_timeouts=1,
            home_timeouts=2,
            last_play=td_play,
        ),
        now=now,
    )
    halftime = _demo_game(
        "demo-half",
        "live",
        "STATUS_HALFTIME",
        away_score=10,
        home_score=10,
        period=2,
        clock="0:00",
        now=now,
    )
    final = _demo_game(
        "demo-final",
        "final",
        "STATUS_FINAL",
        away_score=24,
        home_score=27,
        period=5,
        clock="0:00",
        final_ot=True,
        now=now,
    )
    local = datetime.fromtimestamp(now, UTC).astimezone(tz)
    days = (6 - local.weekday()) % 7 or 7  # next Sunday, never today
    sunday = (local + timedelta(days=days)).replace(
        hour=13, minute=0, second=0, microsecond=0
    )
    future = _demo_game(
        "demo-next",
        "future",
        "STATUS_SCHEDULED",
        away="NYG",
        home="PHI",
        away_record="4-3",
        home_record="5-2",
        venue="Lincoln Financial Field",
        start_utc=sunday.astimezone(UTC),
        now=now,
    )
    bye = _demo_game(
        "demo-bye",
        "future",
        "STATUS_SCHEDULED",
        start_utc=(sunday + timedelta(days=7)).astimezone(UTC),
        week=10,
        now=now,
    )
    td = ScoringPlay(
        key="demo-live:20:17",
        team="PHI",
        kind="TD",
        extra="+PAT",
        text="JALEN HURTS 12 YD RUSH",
        period_label="Q4",
        clock="9:41",
        away_score=20,
        home_score=17,
    )
    return [live, halftime, final, future, bye], td
