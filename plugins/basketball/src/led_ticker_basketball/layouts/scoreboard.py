"""Physical (scale>1) held scoreboard: the horizontal arena board.

One game across the whole panel, the way an arena's centre-hung board
reads: away logo | away score | centre column (period / clock) | home
score | home logo. The hi-res y values are BASELINES painted through the
font's ascent (`_base`). Two geometries, picked by physical width
(`_WIDE_MIN_W`):

- bigsign (256x64): 36px logos at the edges, size-30 scores, the centre
  column at x=128 (period over clock; HALF / END Q3 / FINAL take the clock
  slot), the two points leaders (short style) along the bottom.
- longboi (512x64): 48px logos, size-46 scores, the centre column at
  x=256 with an ORANGE per-period linescore strip under the clock (as wide
  as the two scores' footprint, so overtime columns fit), and one
  line along the bottom of each side (from under the logo toward the
  centre): abbrev + record + full-style points leader.

A logo that cannot be drawn (`logos=False`, unknown team, missing asset)
falls back to a two-tone team chip plus the abbreviation in team colour in
the logo's slot.

Layout invariant (CONTRIBUTING.md): every variable-length text is
measured with core's `hires_text_width`, shrinks through a ladder via
`fit_text_size` (ROW-UNIFORM for the two scores and the two fallback
abbrevs), ellipsizes at the floor or is dropped where an ellipsis would be
meaningless (bigsign leader names below the floor, the linescore strip),
and keeps >= `_MIN_GAP` px from any neighbour sharing its vertical band.
Budgets come from the measured extents of the fixed-anchor texts and
shapes, so the clearance holds by construction;
`tests/test_layout_scoreboard.py` spies on `hires()` / `rect()` /
`paint_logo()` and asserts it on worst-case data.

Never raises on sparse `GameInfo` (no clock, no leaders, no linescores, no
start time, unknown teams): a missing value is simply not drawn.
"""

from dataclasses import dataclass

from led_ticker.plugin import Color, resolve_font, safe_scale

from led_ticker_basketball import _palette as pal
from led_ticker_basketball._logos import LOGO_BIG, LOGO_LONG, paint_logo, sprite
from led_ticker_basketball._models import (
    _NO_CLOCK_STATUSES,
    GameInfo,
    is_clutch,
    leader_text,
    period_label,
    status_lines,
    winner,
)
from led_ticker_basketball._paint import (
    fit_size,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    rect,
    text_width,
)
from led_ticker_basketball.teams import team

_WIDE_MIN_W = 400
_MIN_GAP = 6
_FONT = "Inter-Bold"
_NICK_DIM = 0.65  # next-game nickname: team primary, dimmed
_CAP = 0.72  # cap height / font size: the band a text occupies above its baseline
_LEADER_SIZES = (9, 8)  # bigsign leader lines; 8 is core's legible floor
_LEADER_KEEP = 6  # longboi: ellipsize a leader only while >= this many chars remain
_SIDE_SIZE = 10  # longboi side line


@dataclass(frozen=True)
class _Geom:
    wide: bool
    logo_size: int
    logo_x: tuple[int, int]  # away / home logo left edges
    logo_y: int
    chip_x: tuple[tuple[int, int], tuple[int, int]]  # inclusive x spans
    chip_y: tuple[int, int]  # inclusive y span
    chip_sec_rows: int
    abbrev_x: tuple[int, int]  # fallback abbrev: away left edge, home RIGHT edge
    abbrev_sizes: tuple[int, ...]
    abbrev_base: int
    score_x: tuple[int, int]  # away score RIGHT edge, home score left edge
    score_sizes: tuple[int, ...]
    score_base: int
    center_x: int
    period_base: int
    period_sizes: tuple[int, ...]
    clock_base: int
    clock_sizes: tuple[int, ...]
    slot_sizes: tuple[int, ...]  # HALF / END Q3 / FINAL in the clock slot
    ot_base: int
    ot_size: int
    stale_right: int
    stale_base: int
    stale_size: int

    @property
    def inner(self) -> tuple[int, int]:
        """(away logo slot's right edge + gap, home logo slot's left - gap):
        the x-range everything between the two logos lives in."""
        return (
            self.logo_x[0] + self.logo_size + _MIN_GAP,
            self.logo_x[1] - _MIN_GAP,
        )


_BIG = _Geom(
    wide=False,
    logo_size=LOGO_BIG,
    logo_x=(4, 216),  # 4px margins: 4..39 and 216..251
    logo_y=14,  # vertically centred in 64
    chip_x=((4, 9), (246, 251)),
    chip_y=(14, 49),
    chip_sec_rows=8,
    abbrev_x=(16, 239),  # _MIN_GAP (+1) clear of the 6px chip
    abbrev_sizes=(22, 20, 18, 16, 14),
    abbrev_base=42,
    score_x=(96, 160),  # widest score clears the logo by _MIN_GAP
    score_sizes=(30, 28, 26, 24),
    score_base=46,
    center_x=128,
    period_base=22,
    period_sizes=(14, 12, 10),
    clock_base=46,
    clock_sizes=(20, 18, 16, 14, 12),
    slot_sizes=(18, 16, 14, 12),
    ot_base=60,
    ot_size=12,
    stale_right=251,
    stale_base=8,
    stale_size=9,
)

_LONG = _Geom(
    wide=True,
    logo_size=LOGO_LONG,
    logo_x=(8, 456),  # 8..55 and 456..503
    logo_y=4,  # 4..51: the side lines run underneath, edge to centre
    chip_x=((8, 15), (496, 503)),
    chip_y=(4, 51),
    chip_sec_rows=8,
    abbrev_x=(24, 487),
    abbrev_sizes=(28, 24, 22, 20, 18),
    abbrev_base=38,
    score_x=(190, 322),
    score_sizes=(46, 42, 38),
    score_base=50,
    center_x=256,
    period_base=16,
    period_sizes=(15, 14, 12),
    clock_base=42,
    clock_sizes=(26, 24, 22, 20),
    slot_sizes=(26, 24, 22, 20),
    ot_base=60,
    ot_size=14,
    stale_right=450,
    stale_base=8,
    stale_size=9,
)

_LONG_STRIP_BASE = 60
_LONG_STRIP_SIZES = (10, 9, 8)
_BIG_LEADER_BASE = 61
_LONG_SIDE_BASE = 62

# next-game card
_BIG_NEXT_LABEL_BASE = 12
_LONG_NEXT_LABEL_BASE = 7
_NEXT_AT_GAP = 8
_LONG_NEXT_CENTRE_HALF = 100  # names leave the centre column >= 200 px

Box = tuple[int, int, int, int]  # (x0, x1_excl, cap_top, baseline)


def geometry_for(phys_w: int) -> _Geom:
    return _LONG if phys_w >= _WIDE_MIN_W else _BIG


# ------------------------------------------------------------- helpers


def _band_top(base: int, size: int) -> int:
    return base - js_round(size * _CAP)


def _base(shim, text: str, x: int, base: int, color: Color, size: int) -> int:
    """Paint at BASELINE `base`; return the advance (0 if empty)."""
    if not text:
        return 0
    return hires(shim, text, x, base - resolve_font(_FONT, size).ascent, color, size)


def _right(shim, text: str, right: int, base: int, color: Color, size: int) -> int:
    """Right-aligned at `right`; return the left edge."""
    x = right - text_width(size, text) if text else right
    _base(shim, text, x, base, color, size)
    return x


def _center(
    shim, text: str, cx: int, base: int, color: Color, size: int
) -> tuple[int, int]:
    """Centered on `cx`; return (x0, x1)."""
    w = text_width(size, text) if text else 0
    x = js_round(cx - w / 2)
    _base(shim, text, x, base, color, size)
    return x, x + w


def _fit(text: str, sizes: tuple[int, ...], budget: int) -> tuple[str, int]:
    if not text:
        return "", sizes[0]
    budget = max(1, budget)
    size = fit_size(text, sizes, budget)
    return fit_text(text, budget, size), size


def _fit_uniform(
    texts: tuple[str, str], sizes: tuple[int, ...], budgets: tuple[int, int]
) -> tuple[tuple[str, str], int]:
    """Row-uniform shrink: one size for both, each ellipsized to its budget."""
    pairs = list(zip(texts, (max(1, b) for b in budgets), strict=True))
    size = min((fit_size(t, sizes, b) for t, b in pairs if t), default=sizes[0])
    a, b = (fit_text(t, w, size) if t else "" for t, w in pairs)
    return (a, b), size


def _shares_band(box: Box, top: int, base: int) -> bool:
    return not (box[2] > base or top > box[3])


def _score_color(game: GameInfo, abbrev: str, highlight) -> Color:
    """A highlight (team -> fade t) fades that score from the team's
    primary toward the colour it rests at (green / gray on a final)."""
    rest = pal.WHITE
    if game.state == "final":
        win = winner(game)
        if win is not None:
            rest = pal.GREEN if win == abbrev else pal.LOSER
    if highlight and abbrev in highlight:
        return pal.lerp(pal.chip(abbrev)[0], rest, highlight[abbrev])
    return rest


def _logo(real, abbrev: str, size: int, x: int, y: int, logos: bool) -> bool:
    """Paint `abbrev`'s logo sprite at (x, y); True when one was painted."""
    if not logos or not abbrev:
        return False
    s = sprite(abbrev, size)
    if s is None:
        return False
    paint_logo(real, s, x, y)
    return True


def _chip(real, abbrev: str, x: tuple[int, int], y0: int, y1: int, sec_rows: int):
    """Team chip: primary, with the bottom `sec_rows` in the secondary."""
    primary, secondary = pal.chip(abbrev)
    rect(real, x[0], y0, x[1], y1, primary)
    rect(real, x[0], y1 - sec_rows + 1, x[1], y1, secondary)


def _slots(real, game: GameInfo, g: _Geom, yo: int, logos: bool) -> tuple[bool, bool]:
    """Both logo slots: the sprite, else the chip. Returns (away, home)
    logo-painted flags (False = the chip went in, the abbrev is the
    caller's)."""
    painted = []
    for side, abbrev in enumerate((game.away, game.home)):
        ok = _logo(real, abbrev, g.logo_size, g.logo_x[side], g.logo_y + yo, logos)
        if not ok:
            _chip(
                real,
                abbrev,
                g.chip_x[side],
                g.chip_y[0] + yo,
                g.chip_y[1] + yo,
                g.chip_sec_rows,
            )
        painted.append(ok)
    return painted[0], painted[1]


def _slot_abbrevs(shim, game, g, yo, painted, budgets) -> None:
    """The fallback abbrevs beside the chips, one size for both."""
    texts = tuple(
        "" if ok else abbrev
        for ok, abbrev in zip(painted, (game.away, game.home), strict=True)
    )
    (away, home), size = _fit_uniform((texts[0], texts[1]), g.abbrev_sizes, budgets)
    # Not even one letter + ellipsis fits: the chip alone carries the team.
    away = away if text_width(size, away) <= budgets[0] else ""
    home = home if text_width(size, home) <= budgets[1] else ""
    base = g.abbrev_base + yo
    _base(shim, away, g.abbrev_x[0], base, pal.chip(game.away)[0], size)
    _right(shim, home, g.abbrev_x[1], base, pal.chip(game.home)[0], size)


def _ot_label(game: GameInfo) -> str:
    return period_label(game.period, "") if game.period > 4 else "OT"


def _next_label(game: GameInfo) -> str:
    return "PPD" if game.status == "STATUS_POSTPONED" else "NEXT GAME"


def _linescore(game: GameInfo) -> str:
    pairs = zip(game.away_linescores, game.home_linescores, strict=False)
    return " · ".join(f"{a}-{h}" for a, h in pairs)


# --------------------------------------------------------------- board


def _scores(shim, game, g, yo, highlight) -> tuple[int, int]:
    """Both scores, one size, each clearing its logo slot by _MIN_GAP.
    Returns (away score x0, home score x1)."""
    texts = (str(game.away_score), str(game.home_score))
    inner0, inner1 = g.inner
    budgets = (g.score_x[0] - inner0, inner1 - g.score_x[1])
    size = min(
        fit_size(t, g.score_sizes, b) for t, b in zip(texts, budgets, strict=True)
    )
    base = g.score_base + yo
    away_x0 = _right(
        shim,
        texts[0],
        g.score_x[0],
        base,
        _score_color(game, game.away, highlight),
        size,
    )
    adv = _base(
        shim,
        texts[1],
        g.score_x[1],
        base,
        _score_color(game, game.home, highlight),
        size,
    )
    return away_x0, g.score_x[1] + adv


def _centre(shim, game, now, tz, g: _Geom, yo: int, budget: int) -> list[Box]:
    """Period over clock (or the status label in the clock slot; FINAL with
    the OT label beneath). Returns the painted boxes."""
    line1, line2 = status_lines(game, now, tz)
    boxes: list[Box] = []

    def put(text: str, base: int, color: Color, sizes: tuple[int, ...]) -> None:
        text, size = _fit(text, sizes, budget)
        if text:
            x0, x1 = _center(shim, text, g.center_x, base + yo, color, size)
            boxes.append((x0, x1, _band_top(base + yo, size), base + yo))

    if game.state == "final":
        put(line1, g.clock_base, pal.WHITE, g.slot_sizes)
        if game.final_ot:
            put(_ot_label(game), g.ot_base, pal.AMBER, (g.ot_size,))
    elif game.status in _NO_CLOCK_STATUSES:
        put(line1, g.clock_base, pal.AMBER, g.slot_sizes)
    else:
        put(line1, g.period_base, pal.AMBER, g.period_sizes)
        clock_color = pal.RED if is_clutch(game) else pal.WHITE
        put(line2, g.clock_base, clock_color, g.clock_sizes)
    return boxes


def _row_limits(boxes: list[Box], top: int, base: int, cx: int) -> tuple[int, int]:
    """(away right limit, home left limit) for a bottom line: _MIN_GAP short
    of the centre boxes sharing its band, else either side of `cx`."""
    shared = [b for b in boxes if _shares_band(b, top, base)]
    if shared:
        return (
            min(b[0] for b in shared) - _MIN_GAP,
            max(b[1] for b in shared) + _MIN_GAP,
        )
    half = _MIN_GAP // 2
    return cx - half, cx + _MIN_GAP - half


def _stale(shim, g: _Geom, right: int, base: int) -> int:
    return _right(shim, "STALE", right, base, pal.DIM, g.stale_size)


def _big_leaders(shim, game, yo, boxes) -> None:
    g = _BIG
    base = _BIG_LEADER_BASE + yo
    top = _band_top(base, _LEADER_SIZES[0])
    left_lim, right_lim = _row_limits(boxes, top, base, g.center_x)
    away_x = g.logo_x[0]
    home_r = g.logo_x[1] + g.logo_size - 1
    for leader, budget, side in (
        (game.away_leader, left_lim - away_x, 0),
        (game.home_leader, home_r - right_lim, 1),
    ):
        text = leader_text(leader, style="short")
        if not text:
            continue
        size = fit_size(text, _LEADER_SIZES, max(1, budget))
        if text_width(size, text) > budget:
            continue  # never ellipsize a name below the floor: drop it
        if side == 0:
            _base(shim, text, away_x, base, pal.CYAN, size)
        else:
            _right(shim, text, home_r, base, pal.CYAN, size)


def _big_board(shim, real, game, now, tz, yo, stale, highlight, logos):
    g = _BIG
    painted = _slots(real, game, g, yo, logos)
    away_x0, home_x1 = _scores(shim, game, g, yo, highlight)
    _slot_abbrevs(
        shim,
        game,
        g,
        yo,
        painted,
        (away_x0 - _MIN_GAP - g.abbrev_x[0], g.abbrev_x[1] - (home_x1 + _MIN_GAP)),
    )
    half = min(
        g.center_x - (g.score_x[0] + _MIN_GAP),
        (g.score_x[1] - _MIN_GAP) - g.center_x,
    )
    boxes = _centre(shim, game, now, tz, g, yo, 2 * half)
    _big_leaders(shim, game, yo, boxes)
    if stale:
        _stale(shim, g, g.stale_right, g.stale_base + yo)


def _side_pieces(
    abbrev: str, record: str, leader: str, budget: int
) -> list[tuple[str, Color]]:
    """`ABBR REC · LEADER` fitted to `budget` at `_SIDE_SIZE`: the leader
    is ellipsized first, then the record dropped, then the leader dropped."""
    size = _SIDE_SIZE

    def width(pieces) -> int:
        return sum(text_width(size, t) for t, _ in pieces) + _MIN_GAP * (
            len(pieces) - 1
        )

    team_c = pal.chip(abbrev)[0]
    head_full = [(abbrev, team_c)] + ([(record, pal.GRAY)] if record else [])
    heads = [head_full] + ([[(abbrev, team_c)]] if record else [])
    heads = [[p for p in h if p[0]] for h in heads]
    if leader:
        dot = ("·", pal.GRAY)
        for head in heads:
            full = [*head, dot, (leader, pal.CYAN)] if head else [(leader, pal.CYAN)]
            if width(full) <= budget:
                return full
            lead_in = [*head, dot] if head else []
            room = budget - width(lead_in) - (_MIN_GAP if lead_in else 0)
            cut = fit_text(leader, max(1, room), size)
            if len(cut.rstrip("…")) >= _LEADER_KEEP and text_width(size, cut) <= room:
                return [*lead_in, (cut, pal.CYAN)]
    for head in heads:
        if head and width(head) <= budget:
            return head
    if abbrev and text_width(size, abbrev) <= budget:
        return [(abbrev, team_c)]
    return []


def _long_side_lines(shim, game, yo, boxes) -> None:
    g = _LONG
    base = _LONG_SIDE_BASE + yo
    top = _band_top(base, _SIDE_SIZE)
    left_lim, right_lim = _row_limits(boxes, top, base, g.center_x)
    away_x, home_r = g.logo_x[0], g.logo_x[1] + g.logo_size - 1  # under the logos
    away = _side_pieces(
        game.away,
        game.away_record,
        leader_text(game.away_leader, style="full"),
        left_lim - away_x,
    )
    home = _side_pieces(
        game.home,
        game.home_record,
        leader_text(game.home_leader, style="full"),
        home_r - right_lim,
    )
    x = away_x
    for text, color in away:
        x += _base(shim, text, x, base, color, _SIDE_SIZE) + _MIN_GAP
    x = home_r
    for text, color in reversed(home):
        x = _right(shim, text, x, base, color, _SIDE_SIZE) - _MIN_GAP


def _strip_budget(cx: int, away_x0: int, home_x1: int, centre: int) -> int:
    """Width the longboi linescore strip may take, centred on `cx`.

    The strip's cap band (y~53-60) sits BELOW the size-46 scores' band
    (which ends ~y50) and below the logos (y4..51), so it is not confined
    to the centre column between the scores (~120 px: too narrow for even
    five periods at the floor). It spans the scores' measured footprint
    (away score's left edge .. home score's right edge), symmetric about
    the centre; never narrower than the centre column."""
    return max(centre, 2 * min(cx - away_x0, home_x1 - cx))


def _long_board(shim, real, game, now, tz, yo, stale, highlight, logos):
    g = _LONG
    painted = _slots(real, game, g, yo, logos)
    away_x0, home_x1 = _scores(shim, game, g, yo, highlight)
    _slot_abbrevs(
        shim,
        game,
        g,
        yo,
        painted,
        (away_x0 - _MIN_GAP - g.abbrev_x[0], g.abbrev_x[1] - (home_x1 + _MIN_GAP)),
    )
    half = min(
        g.center_x - (g.score_x[0] + _MIN_GAP),
        (g.score_x[1] - _MIN_GAP) - g.center_x,
    )
    budget = 2 * half
    boxes = _centre(shim, game, now, tz, g, yo, budget)

    strip = _linescore(game) if game.away_linescores and game.home_linescores else ""
    base = _LONG_STRIP_BASE + yo
    top = _band_top(base, _LONG_STRIP_SIZES[0])
    if strip and not any(_shares_band(b, top, base) for b in boxes):
        # Recorded in `boxes` BEFORE the side lines are fitted, so they
        # shrink around it (`_row_limits`).
        strip_budget = _strip_budget(g.center_x, away_x0, home_x1, budget)
        size = fit_size(strip, _LONG_STRIP_SIZES, strip_budget)
        if text_width(size, strip) <= strip_budget:  # never an ellipsized strip
            x0, x1 = _center(shim, strip, g.center_x, base, pal.ORANGE, size)
            boxes.append((x0, x1, _band_top(base, size), base))

    _long_side_lines(shim, game, yo, boxes)
    if stale:
        _stale(shim, g, g.stale_right, g.stale_base + yo)


# ---------------------------------------------------------- next game


def _big_next(shim, real, game, now, tz, yo, stale, logos):
    g = _BIG
    _slots(real, game, g, yo, logos)
    label_base = _BIG_NEXT_LABEL_BASE + yo
    label_x0 = _right(shim, _next_label(game), g.stale_right, label_base, pal.GRAY, 9)
    if stale:
        _stale(shim, g, label_x0 - _MIN_GAP, label_base)

    inner0, inner1 = g.inner
    cx = g.center_x
    budget = 2 * min(cx - inner0, inner1 - cx)

    # PHI 5-2 @ NY 4-3, centred: one size for both names, the records drop
    # first when even the floor is too wide.
    name_sizes, rec_size, at_size = (16, 14, 12, 10), 10, 12
    at = "VS" if game.neutral_site else "@"
    fixed = text_width(at_size, at) + 2 * _NEXT_AT_GAP
    away, home = game.away, game.home
    recs = (game.away_record, game.home_record)

    def rec_w(r: str) -> int:
        return text_width(rec_size, r) + _MIN_GAP if r else 0

    def run_w(size: int, with_recs: bool) -> int:
        extra = sum(rec_w(r) for r in recs) if with_recs else 0
        names = (text_width(size, away) if away else 0) + (
            text_width(size, home) if home else 0
        )
        return names + fixed + extra

    size, show_recs = name_sizes[-1], False
    for with_recs in (True, False) if any(recs) else (False,):
        fits = [s for s in name_sizes if run_w(s, with_recs) <= budget]
        if fits:
            size, show_recs = fits[0], with_recs
            break
    extra = sum(rec_w(r) for r in recs) if show_recs else 0
    half_names = max(1, (budget - fixed - extra) // 2)
    away = fit_text(away, half_names, size) if away else ""
    home = fit_text(home, half_names, size) if home else ""
    total = (
        (text_width(size, away) if away else 0)
        + (text_width(size, home) if home else 0)
        + fixed
        + extra
    )
    base = 25 + yo
    x = js_round(cx - total / 2)
    x += _base(shim, away, x, base, pal.chip(game.away)[0], size)
    if show_recs and recs[0]:
        x += _MIN_GAP
        x += _base(shim, recs[0], x, base, pal.GRAY, rec_size)
    x += _NEXT_AT_GAP
    x += _base(shim, at, x, base, pal.GRAY, at_size) + _NEXT_AT_GAP
    x += _base(shim, home, x, base, pal.chip(game.home)[0], size)
    if show_recs and recs[1]:
        _base(shim, recs[1], x + _MIN_GAP, base, pal.GRAY, rec_size)

    day, clock = status_lines(game, now, tz)
    day, day_size = _fit(day, (11, 10), budget)
    _center(shim, day, cx, 37 + yo, pal.AMBER, day_size)
    clock, clock_size = _fit(clock, (15, 14, 12), budget)
    clock_color = pal.DIM if game.time_tbd else pal.WHITE
    _center(shim, clock, cx, 52 + yo, clock_color, clock_size)
    if game.venue:
        venue_budget = g.logo_x[1] + g.logo_size - g.logo_x[0]
        venue = fit_text(game.venue.upper(), venue_budget, 8)
        _center(shim, venue, cx, 62 + yo, pal.DIM, 8)


def _long_next(shim, real, game, now, tz, yo, stale, logos):
    g = _LONG
    painted = _slots(real, game, g, yo, logos)
    inner0, inner1 = g.inner
    # Names beside the logos, or beside the chips when there is no logo.
    name_l = inner0 if painted[0] else g.abbrev_x[0]
    name_r = inner1 if painted[1] else g.abbrev_x[1]
    cx = g.center_x
    (away, home), size = _fit_uniform(
        (game.away, game.home),
        g.abbrev_sizes,
        (
            cx - _LONG_NEXT_CENTRE_HALF - name_l,
            name_r - (cx + _LONG_NEXT_CENTRE_HALF),
        ),
    )
    away_x1 = name_l + _base(shim, away, name_l, 32 + yo, pal.chip(game.away)[0], size)
    home_x0 = _right(shim, home, name_r, 32 + yo, pal.chip(game.home)[0], size)
    rec_size = 12
    if game.away_record:
        away_x1 += _MIN_GAP
        away_x1 += _base(shim, game.away_record, away_x1, 32 + yo, pal.GRAY, rec_size)
    if game.home_record:
        home_x0 = _right(
            shim, game.home_record, home_x0 - _MIN_GAP, 32 + yo, pal.GRAY, rec_size
        )
    label = _next_label(game)
    label_x1 = name_l + _base(
        shim, label, name_l, _LONG_NEXT_LABEL_BASE + yo, pal.GRAY, 8
    )
    half = min(cx - (away_x1 + _MIN_GAP), home_x0 - _MIN_GAP - cx)
    stale_x0 = g.stale_right
    if stale:
        stale_x0 = _stale(shim, g, g.stale_right, g.stale_base + yo)
    day, clock = status_lines(game, now, tz)
    # The day line's band touches the label's (top-left) and STALE's (top-right).
    day_half = min(half, stale_x0 - _MIN_GAP - cx, cx - (label_x1 + _MIN_GAP))
    day, day_size = _fit(day, (14, 13, 12, 11), 2 * day_half)
    _center(shim, day, cx, 17 + yo, pal.AMBER, day_size)
    clock, clock_size = _fit(clock, (26, 24, 22, 20), 2 * half)
    clock_color = pal.DIM if game.time_tbd else pal.WHITE
    t0, t1 = _center(shim, clock, cx, 44 + yo, clock_color, clock_size)
    if not clock:
        t0 = t1 = cx

    # Nicknames share the clock's bottom rows: clear its measured extent.
    nicks = (
        team(game.away).nickname.upper() if game.away else "",
        team(game.home).nickname.upper() if game.home else "",
    )
    nick_budgets = (t0 - _MIN_GAP - name_l, name_r - (t1 + _MIN_GAP))
    (nick_a, nick_h), nick_size = _fit_uniform(nicks, (12, 11, 10), nick_budgets)
    away_c = pal.dim(pal.chip(game.away)[0], _NICK_DIM)
    home_c = pal.dim(pal.chip(game.home)[0], _NICK_DIM)
    a1 = name_l + _base(shim, nick_a, name_l, 52 + yo, away_c, nick_size)
    h0 = _right(shim, nick_h, name_r, 52 + yo, home_c, nick_size)
    if game.venue:
        v_half = min(cx - (a1 + _MIN_GAP), h0 - _MIN_GAP - cx)
        venue = fit_text(game.venue.upper(), max(1, 2 * v_half), 10)
        _center(shim, venue, cx, 61 + yo, pal.DIM, 10)


# --------------------------------------------------------------- entry


def render_scoreboard(
    canvas,
    game: GameInfo,
    now: float,
    tz,
    *,
    y_offset: int = 0,
    stale: bool = False,
    highlight: dict[str, float] | None = None,
    logos: bool = True,
    x_offset: int = 0,
) -> None:
    """Paint the arena board for `game` on a scale>1 canvas, its left edge
    at LOGICAL `x_offset` (0 = held; a scroll section's cursor otherwise).
    `highlight` maps team -> fade t: that score fades from the team's
    primary toward its resting colour. `logos=False` draws the chips."""
    shim, real = phys_wrap(canvas, x_offset * safe_scale(canvas))
    yo = y_offset * safe_scale(canvas)
    g = geometry_for(real.width)
    if game.state == "future":
        nxt = _long_next if g.wide else _big_next
        nxt(shim, real, game, now, tz, yo, stale, logos)
    else:
        board = _long_board if g.wide else _big_board
        board(shim, real, game, now, tz, yo, stale, highlight, logos)
