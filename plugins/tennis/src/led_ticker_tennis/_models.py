"""Pure data model + helpers for tennis.scores.

`MatchInfo` is the one shape every renderer consumes; `parse_match` builds it
from a Live Tennis API `Match` object (`GET /matches`), null-safe on every
field the schema marks nullable. The scoring helpers (`format_points`,
`is_break_point`, `status_label`, ...) are pure functions so the renderers
and the tests share one definition of "what does this score mean".

Score arrays from the API are PLAYER-MAJOR: `sets = [1, 0]`, `games =
[[6, 3], [4, 4]]` reads 6-4 then 3-4 (first list is player 1's games per
set), `points = ["15", "40"]`, `server = 1`. `MatchInfo` re-shapes `games`
into per-SET pairs (`[(6, 4), (3, 4)]`) because that is how every renderer
walks it (one column per set).
"""

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# Tour vocabulary of the `tour` filter (and `Match.tour`). `Fixture.tour`
# uses a granular vocabulary (`challenger_men`, `juniors_girls`, ...) that
# PREFIX-matches these; `_tour_matches` handles both.
TOURS: tuple[str, ...] = ("atp", "wta", "challenger", "itf", "juniors")

# Display order when several tours are live at once: main tours first.
_TOUR_RANK: dict[str, int] = {t: i for i, t in enumerate(TOURS)}

# Points vocabulary during a normal game. Anything else (tiebreak counts,
# junk) is passed through as-is by `format_points`.
_GAME_POINTS: tuple[str, ...] = ("0", "15", "30", "40", "AD")


@dataclass
class MatchInfo:
    match_id: int = 0
    p1: str = ""  # display name (surname, or the "A/B" doubles pairing)
    p2: str = ""
    p1_full: str = ""
    p2_full: str = ""
    p1_rank: int | None = None  # official singles ranking position (not seed)
    p2_rank: int | None = None
    state: str = "upcoming"  # "live", "final", "upcoming"
    # For state="final": "completed", "retired", "walkover", "default",
    # "abandoned", "cancelled", "unresolved" (or "" when the API said nothing).
    outcome: str = ""
    # Raw `event_status` ("Interrupted", "Postponed", ...) — "Interrupted"
    # on a live match means the match is suspended, not over.
    event_status: str = ""
    sets: tuple[int, int] = (0, 0)
    games: list[tuple[int, int]] = field(default_factory=list)  # per set (p1, p2)
    points: tuple[str | None, str | None] = (None, None)
    server: int | None = None  # 1 | 2 | None
    is_tiebreak: bool = False
    winner: int | None = None
    tour: str = ""
    tournament: str = ""
    round_code: str = ""
    start_time: datetime | None = None
    is_doubles: bool = False
    stale: bool = False

    @property
    def current_set(self) -> int:
        """1-based index of the set in progress (0 when no set has started)."""
        return len(self.games)

    @property
    def current_games(self) -> tuple[int, int]:
        return self.games[-1] if self.games else (0, 0)


# --- pure helpers -------------------------------------------------------


def surname(name: str) -> str:
    """Display name for a participant: the surname of a singles player, the
    whole "A/B" pairing for a doubles team, the input unchanged when it is a
    single token. Never empty for a non-empty input."""
    s = (name or "").strip()
    if not s or "/" in s:
        return s
    parts = s.split()
    return parts[-1] if parts else s


def format_points(points: tuple[str | None, str | None]) -> str:
    """The two point strings joined as they arrive ("15-40", or "6-6" in a
    tiebreak), "" when either side is missing.

    No tiebreak handling is needed: the wire already sends game points and
    tiebreak counts as display strings. A half score ("40-") would read as
    a defect on the panel, so it renders nothing.
    """
    a, b = points if len(points) == 2 else (None, None)
    if a is None or b is None:
        return ""
    return f"{a}-{b}"


def is_break_point(
    points: tuple[str | None, str | None], server: int | None, is_tiebreak: bool
) -> bool:
    """Break point = the RECEIVER is at AD, or the receiver is at 40 while
    the server is at 0/15/30. Never in a tiebreak. False on any null.

    (Same rule the vendor's own `polymarket-tennis` package documents; kept
    conservative so a partial payload never lights the BP marker.)
    """
    if is_tiebreak or server not in (1, 2):
        return False
    if len(points) != 2 or points[0] is None or points[1] is None:
        return False
    srv = str(points[0] if server == 1 else points[1])
    rcv = str(points[1] if server == 1 else points[0])
    if rcv == "AD":
        return True
    return rcv == "40" and srv in ("0", "15", "30")


def receiver(server: int | None) -> int | None:
    return {1: 2, 2: 1}.get(server) if server in (1, 2) else None


_OUTCOME_LABELS: dict[str, str] = {
    "retired": "RET",
    "walkover": "W/O",
    "default": "DEF",
    "abandoned": "ABD",
    "cancelled": "CANC",
    "unresolved": "FINAL",
    "completed": "FINAL",
    "": "FINAL",
}


def status_label(m: MatchInfo) -> str:
    """The one-word match state: "SET 2" / "SUSP" for live, "FINAL" /
    "RET" / "W/O" / "DEF" / "ABD" / "CANC" for a finished match, "" for an
    upcoming one (the renderers show the start time instead).

    Staleness is not a state: renderers add a separate `STALE` label next
    to this one when `m.stale` is set."""
    if m.state == "live":
        if m.event_status.lower() == "interrupted":
            return "SUSP"
        return f"SET {m.current_set}" if m.current_set else "LIVE"
    if m.state == "final":
        return _OUTCOME_LABELS.get(m.outcome, "FINAL")
    return ""


def format_start_time(dt: datetime | None, tz: ZoneInfo) -> tuple[str, str]:
    """("Today", "3:00 PM") / ("Tmrw", ...) / ("Tue", ...) / ("Sep 14", ...);
    ("", "TBD") when the order of play has not assigned a time yet."""
    if dt is None:
        return "", "TBD"
    now = datetime.now(tz)
    local = dt.astimezone(tz)
    if local.date() == now.date():
        day = "Today"
    elif local.date() == (now + timedelta(days=1)).date():
        day = "Tmrw"
    elif 0 < (local.date() - now.date()).days <= 6:
        day = local.strftime("%a")
    else:
        day = local.strftime("%b %-d")
    return day, local.strftime("%-I:%M %p")


def score_line(m: MatchInfo) -> str:
    """ "6-4 3-4 (15-40)" — the tennis-notation one-liner for the ticker."""
    parts = [f"{a}-{b}" for a, b in m.games]
    pts = format_points(m.points)
    if m.state == "live" and pts:
        parts.append(f"({pts})")
    return " ".join(parts)


def tour_matches(tour: str | None, wanted: list[str] | tuple[str, ...]) -> bool:
    """True when `tour` (filter vocabulary OR the granular record vocabulary,
    e.g. "challenger_men") belongs to one of `wanted`; an empty `wanted`
    admits everything, an unknown/None tour only passes the empty filter."""
    if not wanted:
        return True
    t = (tour or "").lower()
    return any(t == w or t.startswith(w + "_") for w in wanted)


def sort_key(m: MatchInfo) -> tuple[int, float]:
    """Main tours first, then earliest scheduled."""
    ts = m.start_time.timestamp() if m.start_time else float("inf")
    return _TOUR_RANK.get(m.tour, len(TOURS)), ts


# --- parsing ------------------------------------------------------------


def _int(v: Any) -> int | None:
    with contextlib.suppress(TypeError, ValueError):
        return int(v)
    return None


def _dt(v: Any) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    with contextlib.suppress(ValueError, TypeError):
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _pair_games(raw: Any) -> list[tuple[int, int]]:
    """[[6, 3, 2], [4, 6, 2]] (player-major) -> [(6, 4), (3, 6), (2, 2)].
    A ragged or malformed payload yields the sets both sides agree on."""
    if not isinstance(raw, list) or len(raw) != 2:
        return []
    a, b = raw
    if not isinstance(a, list) or not isinstance(b, list):
        return []
    out: list[tuple[int, int]] = []
    for ga, gb in zip(a[:5], b[:5], strict=False):
        ia, ib = _int(ga), _int(gb)
        if ia is None or ib is None:
            break
        out.append((ia, ib))
    return out


def _points(raw: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw, list) or len(raw) != 2:
        return None, None
    a, b = raw
    return (None if a is None else str(a)), (None if b is None else str(b))


def _sets(raw: Any, games: list[tuple[int, int]]) -> tuple[int, int]:
    if isinstance(raw, list) and len(raw) == 2:
        a, b = _int(raw[0]), _int(raw[1])
        if a is not None and b is not None:
            return a, b
    # Derive from completed sets when the tally is missing.
    p1 = sum(1 for ga, gb in games if ga > gb and ga >= 6)
    p2 = sum(1 for ga, gb in games if gb > ga and gb >= 6)
    return p1, p2


def _state(status: str) -> tuple[str, str]:
    s = (status or "").lower()
    if s == "live":
        return "live", ""
    if s == "completed":
        return "final", ""
    if s == "cancelled":
        return "final", "cancelled"
    return "upcoming", ""


def parse_match(raw: dict[str, Any]) -> MatchInfo:
    """Build a `MatchInfo` from one `GET /matches` row. Never raises on a
    missing or null field — every read is guarded, so a sparse row still
    renders (as "?" names / empty score) instead of dropping the story."""
    players = raw.get("players") or {}
    p1 = players.get("p1") or {}
    p2 = players.get("p2") or {}
    score = raw.get("score") or {}
    games = _pair_games(score.get("games"))
    state, forced_outcome = _state(str(raw.get("status") or ""))
    outcome = forced_outcome or str(raw.get("outcome") or "")
    p1_full = str(p1.get("name") or "?")
    p2_full = str(p2.get("name") or "?")
    return MatchInfo(
        match_id=_int(raw.get("id")) or 0,
        p1=surname(p1_full),
        p2=surname(p2_full),
        p1_full=p1_full,
        p2_full=p2_full,
        p1_rank=_int(p1.get("ranking")),
        p2_rank=_int(p2.get("ranking")),
        state=state,
        outcome=outcome if state == "final" else "",
        event_status=str(raw.get("event_status") or ""),
        sets=_sets(score.get("sets"), games),
        games=games,
        points=_points(score.get("points")),
        server=_int(score.get("server")) if score.get("server") in (1, 2) else None,
        is_tiebreak=bool(score.get("is_tiebreak")),
        winner=_int(raw.get("winner")) if raw.get("winner") in (1, 2) else None,
        tour=str(raw.get("tour") or "").lower(),
        tournament=str(raw.get("tournament") or ""),
        round_code=str(raw.get("round_code") or ""),
        start_time=_dt(raw.get("scheduled_time")),
        is_doubles=bool(raw.get("is_doubles")) or "/" in p1_full,
        stale=bool(raw.get("_stale")),
    )


# --- demo=true fixture data ----------------------------------------------
#
# Curated so a sign (and the docs GIFs) can render every renderer branch
# without a key: a live match at break point, a live tiebreak, a retirement
# and an upcoming fixture. Built by a function (not a module-level list)
# because MatchInfo is mutable and start_time is relative to "now".


def build_demo_matches(tz: ZoneInfo) -> list[MatchInfo]:
    now = datetime.now(tz)
    return [
        MatchInfo(
            match_id=1,
            p1="Lehecka",
            p2="Fils",
            p1_full="Jiri Lehecka",
            p2_full="Arthur Fils",
            p1_rank=21,
            p2_rank=15,
            state="live",
            sets=(0, 1),
            games=[(4, 6), (3, 4)],
            points=("15", "40"),
            server=1,
            tour="atp",
            tournament="Cincinnati Open",
            round_code="R16",
            start_time=now - timedelta(hours=1),
        ),
        MatchInfo(
            match_id=2,
            p1="Swiatek",
            p2="Sabalenka",
            p1_full="Iga Swiatek",
            p2_full="Aryna Sabalenka",
            p1_rank=2,
            p2_rank=1,
            state="live",
            sets=(1, 1),
            games=[(6, 3), (4, 6), (6, 6)],
            points=("5", "6"),
            server=2,
            is_tiebreak=True,
            tour="wta",
            tournament="Cincinnati Open",
            round_code="SF",
            start_time=now - timedelta(hours=2),
        ),
        MatchInfo(
            match_id=3,
            p1="Paul",
            p2="Vallejo",
            p1_full="Tommy Paul",
            p2_full="Adolfo Vallejo",
            p1_rank=12,
            p2_rank=480,
            state="final",
            outcome="retired",
            sets=(1, 0),
            games=[(6, 2), (3, 1)],
            winner=1,
            tour="atp",
            tournament="Cincinnati Open",
            round_code="R32",
            start_time=now - timedelta(hours=5),
        ),
        MatchInfo(
            match_id=4,
            p1="Alcaraz",
            p2="Sinner",
            p1_full="Carlos Alcaraz",
            p2_full="Jannik Sinner",
            p1_rank=2,
            p2_rank=1,
            state="upcoming",
            tour="atp",
            tournament="Cincinnati Open",
            round_code="QF",
            start_time=now + timedelta(days=1, hours=3),
        ),
    ]
