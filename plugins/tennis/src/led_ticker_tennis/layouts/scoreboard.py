"""Physical (scale>1) held scoreboard — one match per story.

Two rows (player 1 over player 2), each: serve pip | name | numbers.
Numbers are laid out RIGHT-TO-LEFT from a fixed right anchor using
measured widths, one column per value, `_COL_GAP` apart — so the block is
collision-free by construction and the name gets exactly the remaining
width. Right of the numbers: a "BP" badge on the receiver's row (fixed x,
fixed vocabulary), then a right-aligned status column (state / round-or-
time / tournament) whose lines are ladder-fitted and ellipsized to its
budget.

Two geometries, picked by physical width (`_WIDE_MIN_W`):

- longboi (>= 400px): every set's games in its own column, then the
  in-game points.
- bigsign (< 400px): sets won, current-set games, points — the compact
  tennis scoreboard.

Layout invariant (CONTRIBUTING.md): the variable-length hi-res text here
(names, status/tournament lines) is measured with core's
`hires_text_width`, shrinks through a plugin-owned ladder via core's
`fit_text_size` (ROW-UNIFORM for the two names — mixed sizes on the two
rows read as broken typography), and keeps >= `_MIN_GAP` (6px) measured
clearance from its neighbour. `tests/test_layout_scoreboard.py` spies on
`hires()` and asserts those clearances on worst-case data; any geometry
change must pass it.

Never raises on sparse `MatchInfo` fields — every optional read is guarded
(render-loop breaker contract: a visual helper degrades, never crashes).
"""

from dataclasses import dataclass

from led_ticker.plugin import safe_scale

from led_ticker_tennis import _palette as pal
from led_ticker_tennis._models import (
    MatchInfo,
    format_points,
    format_start_time,
    is_break_point,
    receiver,
    status_label,
)
from led_ticker_tennis._paint import (
    cap_top,
    fit_size,
    fit_text,
    hires,
    phys_wrap,
    pip,
    text_width,
)

_WIDE_MIN_W = 400
_MIN_GAP = 6  # CONTRIBUTING.md floor: measured clearance between neighbours
_COL_GAP = 6  # between numeric columns (same floor; digits are fixed-vocab)


@dataclass(frozen=True)
class _Geom:
    per_set_games: bool
    dot_cx: int
    dot_r: int
    name_x: int
    row_y: tuple[int, int]  # visual cap-top of row 1 / row 2
    row_size: int  # design size for names + numbers
    name_sizes: tuple[int, ...]  # shrink ladder (plugin-owned)
    num_r: int  # right edge of the numeric block
    badge_x: int
    badge_size: int
    status_r: int
    status_budget: int
    status_sizes: tuple[int, ...]
    status_y: tuple[int, int, int]


# longboi 512x64
_LONG = _Geom(
    per_set_games=True,
    dot_cx=11,
    dot_r=3,
    name_x=20,
    row_y=(8, 36),
    row_size=20,
    name_sizes=(20, 18, 16, 14),
    num_r=352,
    badge_x=362,
    badge_size=12,
    status_r=504,
    status_budget=108,
    status_sizes=(16, 14, 12),
    status_y=(6, 26, 44),
)

# bigsign 256x64
_BIG = _Geom(
    per_set_games=False,
    dot_cx=6,
    dot_r=2,
    name_x=14,
    row_y=(8, 36),
    row_size=16,
    name_sizes=(16, 14, 12),
    num_r=172,
    badge_x=178,
    badge_size=10,
    status_r=248,
    status_budget=48,
    status_sizes=(12, 11, 10),
    status_y=(6, 24, 42),
)


def geometry_for(phys_w: int) -> _Geom:
    return _LONG if phys_w >= _WIDE_MIN_W else _BIG


def _row_colors(m: MatchInfo, side: int):
    """(name, games, points) colors for one row."""
    if m.state == "final" and m.winner in (1, 2):
        c = pal.WIN if m.winner == side else pal.LABEL_HI
        return c, c, c
    return pal.IDENT, pal.AMBER, pal.CYAN


def _number_columns(m: MatchInfo, g: _Geom) -> list[tuple[str, str, str]]:
    """Numeric columns left-to-right as (p1_text, p2_text, kind); kind in
    {"sets", "games", "points"}. Empty for an upcoming match."""
    if m.state == "upcoming":
        return []
    cols: list[tuple[str, str, str]] = []
    if not m.games:
        cols.append((str(m.sets[0]), str(m.sets[1]), "sets"))
    elif g.per_set_games:
        cols.extend((str(a), str(b), "games") for a, b in m.games)
    else:
        cols.append((str(m.sets[0]), str(m.sets[1]), "sets"))
        ga, gb = m.current_games
        cols.append((str(ga), str(gb), "games"))
    if m.state == "live":
        a, b = m.points
        if format_points(m.points, m.is_tiebreak):
            cols.append((str(a), str(b), "points"))
    return cols


def _status_lines(m: MatchInfo, tz) -> list[tuple[str, object]]:
    """Up to three right-aligned lines: state, round-or-time, tournament."""
    lines: list[tuple[str, object]] = []
    if m.state == "upcoming":
        day, clock = format_start_time(m.start_time, tz)
        lines.append(("STALE" if m.stale else day or "NEXT", pal.AMBER))
        lines.append((clock, pal.AMBER))
    else:
        label = status_label(m)
        lines.append((label, pal.WIN if m.state == "live" else pal.LABEL_HI))
        if m.state == "live" and m.is_tiebreak:
            lines.append(("TB", pal.TB))
        else:
            lines.append((m.round_code, pal.LABEL_HI))
    lines.append((m.tournament.upper(), pal.LABEL))
    return [(t, c) for t, c in lines if t]


def render_scoreboard(
    canvas,
    m: MatchInfo,
    tz,
    *,
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
) -> None:
    """`story_index`/`story_total` are accepted for the uniform renderer
    contract; there are no paging dots (they would collide with row 2)."""
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    g = geometry_for(real.width)
    size = g.row_size

    # --- numeric block: right-to-left, measured column widths --------
    cols = _number_columns(m, g)
    placed: list[tuple[str, str, str, int]] = []  # (p1, p2, kind, right_x)
    x_right = g.num_r
    for p1_t, p2_t, kind in reversed(cols):
        w = max(text_width(size, p1_t), text_width(size, p2_t))
        placed.append((p1_t, p2_t, kind, x_right))
        x_right -= w + _COL_GAP
    numbers_x0 = x_right + _COL_GAP if cols else g.num_r
    placed.reverse()

    # --- names: row-uniform shrink-to-fit, then ellipsize at the floor --
    name_budget = numbers_x0 - _MIN_GAP - g.name_x
    names = (m.p1.upper() or "?", m.p2.upper() or "?")
    name_size = min(fit_size(n, g.name_sizes, name_budget) for n in names)
    names = tuple(fit_text(n, name_budget, name_size) for n in names)

    bp = (
        is_break_point(m.points, m.server, m.is_tiebreak)
        if m.state == "live"
        else False
    )
    rcv = receiver(m.server)

    for side, (name, y_cap) in enumerate(zip(names, g.row_y, strict=True), start=1):
        name_c, games_c, points_c = _row_colors(m, side)
        y = y_cap + yo
        if m.state == "live" and m.server == side:
            pip(real, g.dot_cx, y + size // 2 - 1, g.dot_r, pal.SERVE)
        hires(shim, name, g.name_x, cap_top(y, name_size), name_c, name_size)
        for p1_t, p2_t, kind, right_x in placed:
            t = p1_t if side == 1 else p2_t
            c = points_c if kind == "points" else games_c
            hires(shim, t, right_x - text_width(size, t), cap_top(y, size), c, size)
        if bp and rcv == side:
            hires(
                shim, "BP", g.badge_x, cap_top(y, g.badge_size), pal.LOSS, g.badge_size
            )

    # --- status column: right-aligned, ladder-fitted, ellipsized -------
    for (text, color), y_cap in zip(_status_lines(m, tz), g.status_y, strict=False):
        s = fit_size(text, g.status_sizes, g.status_budget)
        text = fit_text(text, g.status_budget, s)
        w = text_width(s, text)
        hires(shim, text, g.status_r - w, cap_top(y_cap + yo, s), color, s)
