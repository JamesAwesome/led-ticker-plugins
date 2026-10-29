"""Physical (scale>1) held scoreboard: one game, bigsign or longboi.

The arrangement follows `live-board.html` (live) and `states.html` §2
(final) / §3 (next game); the mockup's hi-res y values are BASELINES,
painted here through the font's ascent (`_base`, the celebration
convention). Two geometries, picked by physical width (`_WIDE_MIN_W`):

- bigsign (< 400px): two 32px team rows (logo | abbrev | score | PP/EN
  badge | SOG) beside a right-aligned status column (period / clock / PP).
  The dotted row divider stops >= `_MIN_GAP` short of any status line
  sharing its row (measured).
- longboi (>= 400px): away on the left, home mirrored on the right (a 48px
  logo at each edge), the period / clock / power play centered at x=256.

Layout invariant (CONTRIBUTING.md): every variable-length text is
measured with core's `hires_text_width`, shrinks through a ladder via
`fit_text_size` (ROW-UNIFORM for the two team abbrevs and nicknames),
ellipsizes at the floor, and keeps >= `_MIN_GAP` px from any neighbour
sharing its vertical band. Budgets come from the measured extents of the
fixed-anchor texts (scores, SOG), so the clearance holds by construction;
`tests/test_layout_scoreboard.py` spies on `hires()` and asserts it on
worst-case data, and on `rect()` / `_dotted()` for the shapes (chips,
badges, divider) plus the panel's vertical bounds.

A logo that cannot be drawn (`logos=False`, unknown team, missing asset)
falls back to the two-tone team chip, and that side's abbrev moves back
beside the chip (`name_x`) with the budget it frees.

Never raises on sparse `GameInfo` (no SOG, no clock, no situation, no
start time, unknown teams): a missing value is simply not drawn.
"""

from dataclasses import dataclass

from led_ticker.plugin import Color, make_color, resolve_font, safe_scale

from led_ticker_hockey import _palette as pal
from led_ticker_hockey._logos import LOGO_LONG, LOGO_ROW, paint_logo, sprite
from led_ticker_hockey._models import (
    GameInfo,
    fmt_clock,
    live_pp_seconds,
    status_lines,
    winner,
)
from led_ticker_hockey._paint import (
    fit_size,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    px,
    rect,
    text_width,
)
from led_ticker_hockey.teams import team

_WIDE_MIN_W = 400
_MIN_GAP = 6
_FONT = "Inter-Bold"
_BLACK = make_color(0, 0, 0)
_NICK_DIM = 0.65  # next-game nickname: team primary, dimmed


@dataclass(frozen=True)
class _Geom:
    wide: bool
    chip_x: tuple[int, int]  # inclusive x span of the (away) chip
    name_x: int  # away abbrev left edge beside the chip
    logo_size: int
    logo_x: int  # away logo left edge
    logo_y: int  # logo top, relative to its team row (bigsign) / the panel
    name_sizes: tuple[int, ...]  # abbrev shrink ladder (row-uniform)
    score_x: int  # bigsign: right edge (both rows); longboi: away right edge
    score_size: int
    sog_size: int
    badge_w: int
    badge_size: int
    status_x: int  # bigsign: right edge; longboi: center
    stale_size: int


_BIG = _Geom(
    wide=False,
    chip_x=(2, 7),  # 6 px wide; >= _MIN_GAP before the abbrev at x14
    name_x=14,
    logo_size=LOGO_ROW,
    logo_x=2,  # 2..29, rows 2..29 / 34..61: clear of the divider at y32
    logo_y=2,
    name_sizes=(22, 20, 18, 16, 14),
    score_x=108,
    score_size=26,
    sog_size=11,
    badge_w=23,
    badge_size=11,
    status_x=251,
    stale_size=9,
)

_LONG = _Geom(
    wide=True,
    chip_x=(6, 13),
    name_x=22,
    logo_size=LOGO_LONG,
    logo_x=6,  # 6..53, y 8..55: the chip's footprint, widened
    logo_y=8,
    name_sizes=(28, 24, 22, 20, 18),
    score_x=168,
    score_size=46,
    sog_size=13,
    badge_w=23,
    badge_size=11,
    status_x=256,
    stale_size=9,
)

# bigsign: row 2 baselines are row 1's + 32
_BIG_ROW_H = 32
_BIG_BADGE_X = 114
_BIG_SOG_X = 144
_BIG_DIVIDER_X1 = 195
# longboi: the home side mirrors the away side
_LONG_HOME_CHIP_X = (498, 505)
_LONG_HOME_LOGO_X = 458  # 458..505
_LONG_HOME_NAME_R = 490
_LONG_HOME_SCORE_X = 344
_LONG_NEXT_NAME_BUDGET = 160  # no scores in the next-game layout


def geometry_for(phys_w: int) -> _Geom:
    return _LONG if phys_w >= _WIDE_MIN_W else _BIG


# ------------------------------------------------------------- helpers


def _base(shim, text: str, x: int, base: int, color: Color, size: int) -> int:
    """Paint at the mockup's BASELINE `base`; return the advance (0 if empty)."""
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


def _score_color(game: GameInfo, abbrev: str, highlight) -> Color:
    """Matches `HockeyBandBoard._score_color`."""
    if highlight is not None and highlight[0] == abbrev:
        return pal.lerp(pal.AMBER, pal.WHITE, highlight[1])
    if game.state == "final":
        win = winner(game)
        if win is not None:
            return pal.GREEN if win == abbrev else pal.LOSER
    return pal.WHITE


def _chip(real, abbrev: str, x: tuple[int, int], y0: int, y1: int, sec_rows: int):
    """Team chip: primary, with the bottom `sec_rows` in the secondary."""
    primary, secondary = pal.chip(abbrev)
    rect(real, x[0], y0, x[1], y1, primary)
    rect(real, x[0], y1 - sec_rows + 1, x[1], y1, secondary)


def _logo(real, abbrev: str, size: int, x: int, y: int, logos: bool) -> bool:
    """Paint `abbrev`'s logo sprite at (x, y); True when one was painted."""
    if not logos or not abbrev:
        return False
    s = sprite(abbrev, size)
    if s is None:
        return False
    paint_logo(real, s, x, y)
    return True


def _slot(real, abbrev, logos, g: _Geom, logo_xy, chip_x, chip_y, sec_rows) -> bool:
    """The team's logo, else its chip. True when the logo went in."""
    if _logo(real, abbrev, g.logo_size, logo_xy[0], logo_xy[1], logos):
        return True
    _chip(real, abbrev, chip_x, chip_y[0], chip_y[1], sec_rows)
    return False


def _badge(shim, real, label: str, x0: int, y0: int, text_base: int, g: _Geom):
    """Amber rect (14 rows) with the label knocked out (unlit)."""
    x1 = x0 + g.badge_w - 1
    rect(real, x0, y0, x1, y0 + 13, pal.AMBER)
    _center(shim, label, (x0 + x1 + 1) // 2, text_base, _BLACK, g.badge_size)


def _situation_live(game: GameInfo) -> bool:
    return game.state == "live" and not game.in_intermission


def _pp_clock(game: GameInfo, now: float) -> str | None:
    """`m:ss` (or "") of the live power play, None when there isn't one."""
    sit = game.situation
    if not _situation_live(game) or sit is None or not sit.pp_team:
        return None
    return fmt_clock(live_pp_seconds(game, now))


def _row_badge(game: GameInfo, abbrev: str) -> str | None:
    """Bigsign per-row badge: EN wins over PP on the same row (the goalie
    is pulled on the PP team)."""
    sit = game.situation
    if not _situation_live(game) or sit is None or not abbrev:
        return None
    if sit.en_team == abbrev:
        return "EN"
    if sit.pp_team == abbrev:
        return "PP"
    return None


def _sog(v: int | None) -> str:
    return f"SOG {v}" if v is not None else ""


def _dotted(real, y: int, x1: int) -> None:
    for x in range(0, x1 + 1, 3):
        px(real, x, y, pal.DIM)


# ------------------------------------------------------------- bigsign


def _big_slots(real, game, yo, logos) -> tuple[int, int]:
    """Both rows' logo-or-chip; returns each row's abbrev left edge."""
    g = _BIG
    xs = []
    for row, abbrev in enumerate((game.away, game.home)):
        dy = row * _BIG_ROW_H + yo
        logo_xy = (g.logo_x, g.logo_y + dy)
        logo = _slot(real, abbrev, logos, g, logo_xy, g.chip_x, (5 + dy, 26 + dy), 4)
        xs.append(g.logo_x + g.logo_size + _MIN_GAP if logo else g.name_x)
    return xs[0], xs[1]


def _big_board(shim, real, game, now, tz, yo, stale, highlight, logos):
    g = _BIG
    abbrevs = (game.away, game.home)
    scores = (str(game.away_score), str(game.home_score))
    name_xs = _big_slots(real, game, yo, logos)
    budgets = (
        g.score_x - text_width(g.score_size, scores[0]) - _MIN_GAP - name_xs[0],
        g.score_x - text_width(g.score_size, scores[1]) - _MIN_GAP - name_xs[1],
    )
    names, name_size = _fit_uniform(abbrevs, g.name_sizes, budgets)
    sogs = (_sog(game.away_sog), _sog(game.home_sog))
    col_left = _BIG_BADGE_X + g.badge_w - 1  # status clears the badge...
    for row, abbrev in enumerate(abbrevs):
        dy = row * _BIG_ROW_H + yo
        _base(shim, names[row], name_xs[row], 25 + dy, pal.chip(abbrev)[0], name_size)
        color = _score_color(game, abbrev, highlight)
        _right(shim, scores[row], g.score_x, 26 + dy, color, g.score_size)
        badge = _row_badge(game, abbrev)
        if badge:
            _badge(shim, real, badge, _BIG_BADGE_X, 9 + dy, 20 + dy, g)
        if sogs[row]:
            w = _base(shim, sogs[row], _BIG_SOG_X, 21 + dy, pal.CYAN, g.sog_size)
            col_left = max(col_left, _BIG_SOG_X + w)  # ...and the SOG

    budget = g.status_x - (col_left + _MIN_GAP)
    line1, line2 = status_lines(game, now, tz)
    if game.state == "final":
        lines = [
            (line1, pal.WHITE, 24, (16, 14, 12, 10)),
            (line2, pal.AMBER, 46, (16, 14, 12, 10)),
        ]
    else:
        lines = [
            (line1, pal.AMBER, 19, (15, 14, 13, 12, 11, 10)),
            (line2, pal.WHITE, 40, (18, 16, 14, 12, 11)),
        ]
        pp = _pp_clock(game, now)
        if pp is not None:
            lines.append((f"PP {pp}".rstrip(), pal.AMBER, 59, (12, 11, 10)))
    divider_y = 32 + yo
    divider_x1 = _BIG_DIVIDER_X1
    for text, color, base, sizes in lines:
        text, size = _fit(text, sizes, budget)
        x0 = _right(shim, text, g.status_x, base + yo, color, size)
        cap_top = base + yo - js_round(size * 0.72)
        if text and cap_top <= divider_y <= base + yo:
            # A status line shares the divider's row: stop >= _MIN_GAP
            # short of its MEASURED left edge.
            divider_x1 = min(divider_x1, x0 - _MIN_GAP - 1)
    _dotted(real, divider_y, divider_x1)
    if stale:
        _right(shim, "STALE", g.status_x, 7 + yo, pal.DIM, g.stale_size)


def _big_next(shim, real, game, now, tz, yo, stale, logos):
    g = _BIG
    right = g.status_x
    top_limit = _right(shim, "NEXT GAME", right, 12 + yo, pal.GRAY, 9)
    if stale:
        stale_x0 = _right(shim, "STALE", right, 23 + yo, pal.DIM, g.stale_size)
        top_limit = min(top_limit, stale_x0)
    logo_xy = (g.logo_x, g.logo_y + yo)
    away_logo = _slot(
        real, game.away, logos, g, logo_xy, g.chip_x, (5 + yo, 26 + yo), 4
    )
    name_x = g.logo_x + g.logo_size + _MIN_GAP if away_logo else g.name_x
    # The home logo rides in the run, just before the home name.
    home_sprite = sprite(game.home, g.logo_size) if logos and game.home else None
    home_logo_w = g.logo_size + _MIN_GAP if home_sprite is not None else 0

    # PHI @ NYI: one size for both names, shrunk until the run fits.
    budget = top_limit - _MIN_GAP - name_x
    at_size, at_gap = 14, 8
    fixed = text_width(at_size, "@") + 2 * at_gap + home_logo_w
    away, home = game.away, game.home
    size, fitted = g.name_sizes[-1], False
    for s in g.name_sizes:
        if text_width(s, away) + text_width(s, home) + fixed <= budget:
            size, fitted = s, True
            break
    if not fitted:  # even the floor is too wide: ellipsize each to half
        half = max(1, (budget - fixed) // 2)
        away = fit_text(away, half, size) if away else ""
        home = fit_text(home, half, size) if home else ""
    x = name_x
    x += _base(shim, away, x, 26 + yo, pal.chip(game.away)[0], size) + at_gap
    x += _base(shim, "@", x, 24 + yo, pal.GRAY, at_size) + at_gap
    if home_sprite is not None:
        paint_logo(real, home_sprite, x, g.logo_y + yo)
        x += home_logo_w
    _base(shim, home, x, 26 + yo, pal.chip(game.home)[0], size)
    _dotted(real, 32 + yo, real.width - 1)

    day, clock = status_lines(game, now, tz)
    time_x0 = _right(shim, clock, right, 52 + yo, pal.WHITE, 15)
    day, day_size = _fit(day, (15, 14, 13, 12), time_x0 - _MIN_GAP - name_x)
    _base(shim, day, name_x, 52 + yo, pal.AMBER, day_size)
    if game.venue:
        venue = fit_text(game.venue.upper(), right - name_x, 8)
        _base(shim, venue, name_x, 62 + yo, pal.DIM, 8)


# ------------------------------------------------------------- longboi


def _long_slots(real, game, yo, logos) -> tuple[int, int]:
    """Both edge logos-or-chips. Returns (away abbrev left edge, home
    abbrev RIGHT edge): beside the logo, else beside the chip."""
    g = _LONG
    chip_y = (8 + yo, 56 + yo)
    logo_y = g.logo_y + yo
    away = _slot(real, game.away, logos, g, (g.logo_x, logo_y), g.chip_x, chip_y, 9)
    home_xy = (_LONG_HOME_LOGO_X, logo_y)
    home = _slot(real, game.home, logos, g, home_xy, _LONG_HOME_CHIP_X, chip_y, 9)
    return (
        g.logo_x + g.logo_size + _MIN_GAP if away else g.name_x,
        _LONG_HOME_LOGO_X - _MIN_GAP if home else _LONG_HOME_NAME_R,
    )


def _long_sides(shim, game, yo, limits, names, *, sog: bool) -> tuple[int, int]:
    """Both abbrevs (+ SOG), fitted between `names` (the abbrevs' outer
    edges, from `_long_slots`) and `limits` (away right / home left).
    Returns (away abbrev x1, home x0)."""
    g = _LONG
    name_l, name_r = names
    budgets = (limits[0] - name_l, name_r - limits[1])
    (away, home), size = _fit_uniform((game.away, game.home), g.name_sizes, budgets)
    away_c, home_c = pal.chip(game.away)[0], pal.chip(game.home)[0]
    away_x1 = name_l + _base(shim, away, name_l, 32 + yo, away_c, size)
    home_x0 = _right(shim, home, name_r, 32 + yo, home_c, size)
    if sog:
        _base(shim, _sog(game.away_sog), name_l, 54 + yo, pal.CYAN, g.sog_size)
        _right(shim, _sog(game.home_sog), name_r, 54 + yo, pal.CYAN, g.sog_size)
    return away_x1, home_x0


def _long_stale(shim, top_right: int, yo: int) -> None:
    """STALE at the top, just right of the center column's first line."""
    x = max(top_right, _LONG.status_x) + _MIN_GAP + 2
    _base(shim, "STALE", x, 10 + yo, pal.DIM, _LONG.stale_size)


def _long_pp_line(shim, real, game, now, budget: int, yo: int) -> None:
    """[PP] TEAM m:ss  [EN] TEAM, centered under the clock."""
    g = _LONG
    sit = game.situation
    if not _situation_live(game) or sit is None:
        return
    groups: list[tuple[str, str]] = []
    pp = _pp_clock(game, now)
    if pp is not None and sit.pp_team:
        groups.append(("PP", f"{sit.pp_team} {pp}".rstrip()))
    if sit.en_team:
        groups.append(("EN", sit.en_team))
    if not groups:
        return
    group_gap = 8

    def total(size: int) -> int:
        widths = (g.badge_w + _MIN_GAP + text_width(size, lbl) for _, lbl in groups)
        return sum(widths) + group_gap * (len(groups) - 1)

    size = 10
    for s in (12, 11, 10):
        if total(s) <= budget:
            size = s
            break
    while len(groups) > 1 and total(size) > budget:
        groups.pop()
    if total(size) > budget:
        lbl_budget = max(1, budget - g.badge_w - _MIN_GAP)
        groups = [(groups[0][0], fit_text(groups[0][1], lbl_budget, size))]
    x = js_round(g.status_x - total(size) / 2)
    for label, text in groups:
        _badge(shim, real, label, x, 49 + yo, 60 + yo, g)
        x += g.badge_w + _MIN_GAP
        x += _base(shim, text, x, 60 + yo, pal.AMBER, size) + group_gap


def _long_board(shim, real, game, now, tz, yo, stale, highlight, logos):
    g = _LONG
    away_s, home_s = str(game.away_score), str(game.home_score)
    away_x0 = g.score_x - text_width(g.score_size, away_s)
    home_x1 = _LONG_HOME_SCORE_X + text_width(g.score_size, home_s)
    limits = (away_x0 - _MIN_GAP, home_x1 + _MIN_GAP)
    names = _long_slots(real, game, yo, logos)
    _long_sides(shim, game, yo, limits, names, sog=True)
    away_c = _score_color(game, game.away, highlight)
    home_c = _score_color(game, game.home, highlight)
    _base(shim, away_s, away_x0, 52 + yo, away_c, g.score_size)
    _base(shim, home_s, _LONG_HOME_SCORE_X, 52 + yo, home_c, g.score_size)

    half = min(
        g.status_x - (g.score_x + _MIN_GAP),
        _LONG_HOME_SCORE_X - _MIN_GAP - g.status_x,
    )
    budget = 2 * half
    line1, line2 = status_lines(game, now, tz)
    if game.state == "final":
        lines = [
            (line1, pal.WHITE, 34, (24, 22, 20, 18)),
            (line2, pal.AMBER, 56, (16, 14, 12)),
        ]
    else:
        lines = [
            (line1, pal.AMBER, 17, (15, 14, 13, 12)),
            (line2, pal.WHITE, 44, (26, 24, 22, 20)),
        ]
    top_right = g.status_x
    for i, (text, color, base, sizes) in enumerate(lines):
        text, size = _fit(text, sizes, budget)
        _, x1 = _center(shim, text, g.status_x, base + yo, color, size)
        if i == 0 and text:
            top_right = x1
    if game.state != "final":
        _long_pp_line(shim, real, game, now, budget, yo)
    if stale:
        _long_stale(shim, top_right, yo)


def _long_next(shim, real, game, now, tz, yo, stale, logos):
    g = _LONG
    # The names end where they did beside the chips: a logo eats into the
    # names' budget, never the centre column's.
    limits = (
        g.name_x + _LONG_NEXT_NAME_BUDGET,
        _LONG_HOME_NAME_R - _LONG_NEXT_NAME_BUDGET,
    )
    names = _long_slots(real, game, yo, logos)
    name_l, name_r = names
    away_x1, home_x0 = _long_sides(shim, game, yo, limits, names, sog=False)
    budget = 2 * min(g.status_x - (away_x1 + _MIN_GAP), home_x0 - _MIN_GAP - g.status_x)
    day, clock = status_lines(game, now, tz)
    day, day_size = _fit(day, (14, 13, 12, 11), budget)
    _, day_x1 = _center(shim, day, g.status_x, 17 + yo, pal.AMBER, day_size)
    clock, clock_size = _fit(clock, (26, 24, 22, 20), budget)
    t0, t1 = _center(shim, clock, g.status_x, 44 + yo, pal.WHITE, clock_size)

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
        v_half = min(g.status_x - (a1 + _MIN_GAP), h0 - _MIN_GAP - g.status_x)
        venue = fit_text(game.venue.upper(), max(1, 2 * v_half), 10)
        _center(shim, venue, g.status_x, 60 + yo, pal.DIM, 10)
    if stale:
        _long_stale(shim, day_x1 if day else g.status_x, yo)


# --------------------------------------------------------------- entry


def render_scoreboard(
    canvas,
    game: GameInfo,
    now: float,
    tz,
    *,
    y_offset: int = 0,
    stale: bool = False,
    highlight: tuple[str, float] | None = None,
    logos: bool = True,
    x_offset: int = 0,
) -> None:
    """Paint the scoreboard for `game` on a scale>1 canvas, its left edge at
    LOGICAL `x_offset` (0 = held; a scroll section's cursor otherwise).
    `highlight` = (team, f): that team's score fades amber -> white.
    `logos=False` draws the chips."""
    shim, real = phys_wrap(canvas, x_offset * safe_scale(canvas))
    yo = y_offset * safe_scale(canvas)
    g = geometry_for(real.width)
    if game.state == "future":
        nxt = _long_next if g.wide else _big_next
        nxt(shim, real, game, now, tz, yo, stale, logos)
    else:
        board = _long_board if g.wide else _big_board
        board(shim, real, game, now, tz, yo, stale, highlight, logos)
