"""Physical MLB standings board — port of design `standingsBig`
(dc.html:434-450) and `standingsLong` (dc.html:451-473). 256x64 (bigsign)
gets the "big" 6-column layout (rank/chip/abbr, combined W-L record, GB,
STRK); 512x64 (longboi) gets the "long" 8-column layout (rank/chip/abbr,
split W, split L, PCT, GB, L10, STRK). Selected by `real.width >= 400`,
the same threshold `layouts/__init__.resolve_layout` uses for scores.

Held board (no scroll/paging) — the caller decides how long to hold it and
whether to rotate divisions; this module only draws one division's rows.

CRITICAL vertical-metrics conversion (CLAUDE.md "Hi-res fonts" invariant;
hardware finding fixed on a separate branch — PR #68, NOT in this
worktree's history): dc.html's y coordinates are the glyphs' VISUAL top
under the prototype's own canvas rasterizer, but `_paint.hires()` treats y
as the ASCENT-box top (baseline = y + ascent, ascent == the requested px
size for Inter). Those two mostly cancel out on the sibling renderers
(two_row.py / scoreboard.py) because every text draw within one row shares
a single size there — but THIS board mixes rank(px8)/abbr(px10)/
record(px10) on one 10px-pitch row, so a naive port bleeds a row's glyphs
into its neighbor's band. `_paint.cap_top(y_target, size)` is the ONE
conversion formula (dc.html's y_target -> `hires`'s ascent-box-top y,
originally derived here and later promoted to `_paint` — task 2 of the
promotions uplift — so `_mask.py` could share it); `_t(...)` (single hires
call) routes every plain text draw through it, and the `draw_record` call
site computes the same converted y once and passes it straight through
(draw_record itself forwards y unmodified — see its docstring in
`_primitives.py`) so the formula can't drift per call site.
"""

from typing import TYPE_CHECKING

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import cap_top, hires, phys_wrap
from led_ticker_baseball._primitives import chip, draw_record

if TYPE_CHECKING:
    # Deferred: led_ticker_baseball.standings imports MLBStandingsBoard
    # (_standings_card.py), which imports render_standings_board from this
    # module — an eager top-level import here would be circular. TeamStanding
    # is only used for the type hint below, QUOTED (a string literal): a bare
    # deferred reference would make typing.get_type_hints() / __annotations__
    # introspection raise NameError under PEP 649 evaluation; the string form
    # is introspection-safe and still breaks the cycle.
    from led_ticker_baseball.standings import TeamStanding

_WIDE_MIN_W = 400
_MAX_ROWS = 5
_MIN_ROWS = 3
# Leader has no games-back figure. Our model defaults `division_gb` to "-"
# (hyphen); the dc.html prototype's own STANDINGS fixture used "—" (em
# dash). Treat both as "leader" so real API data and our default agree.
_LEADER_GB = ("-", "—")

# Per-`board_rows` geometry. The 5-row entries are BYTE-IDENTICAL to the
# pre-#72 hardcoded values (pitch/text/rank/chip/row0/abbr_x/gb_x/strk_x) —
# the 5-row layout tests assert this unchanged. 4/3-row entries scale
# pitch/text/rank/chip up as `board_rows` shrinks so fewer rows still fill
# the panel readably; row0 (first row's y) and the header (division name +
# column labels, drawn separately in `_render_big`/`_render_long`) are
# UNTOUCHED by row count except where noted.
#
# `abbr_x` = chip_x + chip_h + 3 (chip_x is fixed per variant: 11 for big,
# 18 for long) for every entry EXCEPT long's 5-row, which is the pre-#72
# handoff value (32) preserved exactly for byte-identical output — the
# formula would give 30 there; the discrepancy is a pre-existing handoff
# quirk, not a bug introduced here.
#
# `gb_x`/`strk_x` (big only; long's column x positions are fixed across all
# counts, verified by the collision test below) default to the original
# 180/212 and only move for 3-row: at px15, "16.0" (worst-case GB) run up
# against a fixed STRK column at the original x — both columns are nudged
# out to 172/216 to keep a dark gap between them (verified empirically by
# the collision test, not just the arithmetic).
_BIG_GEOMETRY: dict[int, dict[str, int]] = {
    5: dict(
        pitch=10, text=10, rank=8, chip=8, row0=12, abbr_x=22, gb_x=180, strk_x=212
    ),
    4: dict(
        pitch=13, text=12, rank=9, chip=10, row0=12, abbr_x=24, gb_x=180, strk_x=212
    ),
    3: dict(
        pitch=17, text=15, rank=10, chip=13, row0=13, abbr_x=27, gb_x=172, strk_x=216
    ),
}

_LONG_GEOMETRY: dict[int, dict[str, int]] = {
    5: dict(pitch=10, text=10, rank=8, chip=9, row0=14, abbr_x=32),
    4: dict(pitch=12, text=12, rank=9, chip=11, row0=14, abbr_x=32),
    3: dict(pitch=16, text=14, rank=10, chip=13, row0=14, abbr_x=34),
}


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, cap_top(y_target, size), color, size, bold=bold)


def _strk_color(streak: str):
    return pal.WIN if streak[:1] == "W" else pal.LOSS


# Sane range for a real MLB division_rank. TeamStanding defaults it to 99
# (unknown/unset) for synthetic/legacy rows; anything outside 1-15 is
# treated as "not a real rank" and falls back to row index instead of
# printing a nonsense digit.
_SANE_RANK_MAX = 15


def _rank_label(row: "TeamStanding", index: int) -> str:  # noqa: UP037
    """The board's rank digit is the team's TRUE `division_rank`, not the
    row's position in the (post-pinning) list — `standings.py`'s
    `_select_division_rows` can select rows [1, 2, 5] for a 3-row board
    (tracked-team pinning keeps a lower-ranked tracked team visible), and
    printing the row INDEX there mislabels the pinned team "3" instead of
    "5". Falls back to `index + 1` (the pre-#72 behavior — a faithful port
    of the prototype, which only ever rendered an unbroken top-N) when
    `division_rank` is outside the sane 1-`_SANE_RANK_MAX` range — covers
    synthetic/legacy rows carrying TeamStanding's `division_rank: int = 99`
    default.
    """
    if 1 <= row.division_rank <= _SANE_RANK_MAX:
        return str(row.division_rank)
    return str(index + 1)


def render_standings_board(
    canvas,
    division_name: str,
    rows: "list[TeamStanding]",  # noqa: UP037 — introspection-safe forward ref
    *,
    y_offset: int = 0,
    max_rows: int = _MAX_ROWS,
) -> None:
    """Renderer stays config-agnostic: `max_rows` selects a geometry-table
    entry (`_BIG_GEOMETRY`/`_LONG_GEOMETRY`, keyed 3-5) rather than reading
    config itself — the card (`_standings_card.py`) is what forwards the
    widget's `board_rows` through. A `max_rows` outside 3-5 falls back to 5
    (validated upstream in `standings.py`'s `validate_config`; this is just
    a defensive floor so a bad direct call degrades instead of KeyError'ing).
    """
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    if max_rows not in _BIG_GEOMETRY:
        max_rows = _MAX_ROWS
    capped_rows = rows[:max_rows]
    if real.width >= _WIDE_MIN_W:
        _render_long(
            shim, real, division_name, capped_rows, yo, _LONG_GEOMETRY[max_rows]
        )
    else:
        _render_big(shim, real, division_name, capped_rows, yo, _BIG_GEOMETRY[max_rows])


def _render_big(shim, real, division_name, rows, yo, geo):
    _t(shim, division_name, 4, 1 + yo, pal.CYAN, 8)
    _t(shim, "W-L", 112, 1 + yo, pal.LABEL, 8)
    _t(shim, "GB", 180, 1 + yo, pal.LABEL, 8)
    _t(shim, "STRK", 210, 1 + yo, pal.LABEL, 8)
    pitch, text, rank, chip_h, row0 = (
        geo["pitch"],
        geo["text"],
        geo["rank"],
        geo["chip"],
        geo["row0"],
    )
    abbr_x, gb_x, strk_x = geo["abbr_x"], geo["gb_x"], geo["strk_x"]
    for i, r in enumerate(rows):
        y = row0 + i * pitch + yo
        _t(shim, _rank_label(r, i), 2, y + 1, pal.LABEL, rank)
        chip(real, 11, y, chip_h, r.abbr)
        _t(shim, r.abbr, abbr_x, y, pal.IDENT, text)
        draw_record(shim, 112, cap_top(y, text), r.wins, r.losses, text)
        gb = r.division_gb or "-"
        gb_color = pal.LABEL if gb in _LEADER_GB else pal.AMBER
        _t(shim, gb, gb_x, y, gb_color, text)
        streak = r.streak or ""
        _t(shim, streak, strk_x, y, _strk_color(streak), text)


def _render_long(shim, real, division_name, rows, yo, geo):
    _t(shim, division_name, 6, 2 + yo, pal.CYAN, 9)
    _t(shim, "W", 158, 2 + yo, pal.LABEL, 9)
    _t(shim, "L", 192, 2 + yo, pal.LABEL, 9)
    _t(shim, "PCT", 224, 2 + yo, pal.LABEL, 9)
    _t(shim, "GB", 292, 2 + yo, pal.LABEL, 9)
    _t(shim, "L10", 350, 2 + yo, pal.LABEL, 9)
    _t(shim, "STRK", 420, 2 + yo, pal.LABEL, 9)
    pitch, text, rank, chip_h, row0 = (
        geo["pitch"],
        geo["text"],
        geo["rank"],
        geo["chip"],
        geo["row0"],
    )
    abbr_x = geo["abbr_x"]
    for i, r in enumerate(rows):
        y = row0 + i * pitch + yo
        _t(shim, _rank_label(r, i), 6, y + 1, pal.LABEL, rank)
        chip(real, 18, y, chip_h, r.abbr)
        _t(shim, r.abbr, abbr_x, y, pal.IDENT, text)
        _t(shim, str(r.wins), 158, y, pal.WIN, text)
        _t(shim, str(r.losses), 192, y, pal.LOSS, text)
        _t(shim, r.pct or "", 224, y, pal.AMBER, text)
        gb = r.division_gb or "-"
        gb_color = pal.LABEL if gb in _LEADER_GB else pal.IDENT
        _t(shim, gb, 292, y, gb_color, text)
        _t(shim, r.l10 or "", 350, y, pal.CYAN, text, bold=False)
        streak = r.streak or ""
        _t(shim, streak, 420, y, _strk_color(streak), text)
