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
into its neighbor's band. `_cap_top(y_target, size)` is the ONE conversion
formula (dc.html's y_target -> `hires`'s ascent-box-top y); `_t(...)`
(single hires call) routes every plain text draw through it, and the
`draw_record` call site computes the same converted y once and passes it
straight through (draw_record itself forwards y unmodified — see its
docstring in `_primitives.py`) so the formula can't drift per call site.
"""

from typing import TYPE_CHECKING

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import hires, js_round, phys_wrap
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
# Leader has no games-back figure. Our model defaults `division_gb` to "-"
# (hyphen); the dc.html prototype's own STANDINGS fixture used "—" (em
# dash). Treat both as "leader" so real API data and our default agree.
_LEADER_GB = ("-", "—")


def _cap_top(y_target: int, size: int) -> int:
    """dc.html visual-cap-top y -> `_paint.hires`'s ascent-box-top y."""
    return y_target - size + js_round(size * 0.72)


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, _cap_top(y_target, size), color, size, bold=bold)


def _strk_color(streak: str):
    return pal.WIN if streak[:1] == "W" else pal.LOSS


def render_standings_board(
    canvas,
    division_name: str,
    rows: "list[TeamStanding]",  # noqa: UP037 — introspection-safe forward ref
    *,
    y_offset: int = 0,
) -> None:
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    capped_rows = rows[:_MAX_ROWS]
    if real.width >= _WIDE_MIN_W:
        _render_long(shim, real, division_name, capped_rows, yo)
    else:
        _render_big(shim, real, division_name, capped_rows, yo)


def _render_big(shim, real, division_name, rows, yo):
    _t(shim, division_name, 4, 1 + yo, pal.CYAN, 8)
    _t(shim, "W-L", 112, 1 + yo, pal.LABEL, 8)
    _t(shim, "GB", 180, 1 + yo, pal.LABEL, 8)
    _t(shim, "STRK", 210, 1 + yo, pal.LABEL, 8)
    for i, r in enumerate(rows):
        y = 12 + i * 10 + yo
        _t(shim, str(i + 1), 2, y + 1, pal.LABEL, 8)
        chip(real, 11, y, 8, r.abbr)
        _t(shim, r.abbr, 22, y, pal.IDENT, 10)
        draw_record(shim, 112, _cap_top(y, 10), r.wins, r.losses, 10)
        gb = r.division_gb or "-"
        gb_color = pal.LABEL if gb in _LEADER_GB else pal.AMBER
        _t(shim, gb, 180, y, gb_color, 10)
        streak = r.streak or ""
        _t(shim, streak, 212, y, _strk_color(streak), 10)


def _render_long(shim, real, division_name, rows, yo):
    _t(shim, division_name, 6, 2 + yo, pal.CYAN, 9)
    _t(shim, "W", 158, 2 + yo, pal.LABEL, 9)
    _t(shim, "L", 192, 2 + yo, pal.LABEL, 9)
    _t(shim, "PCT", 224, 2 + yo, pal.LABEL, 9)
    _t(shim, "GB", 292, 2 + yo, pal.LABEL, 9)
    _t(shim, "L10", 350, 2 + yo, pal.LABEL, 9)
    _t(shim, "STRK", 420, 2 + yo, pal.LABEL, 9)
    for i, r in enumerate(rows):
        y = 14 + i * 10 + yo
        _t(shim, str(i + 1), 6, y + 1, pal.LABEL, 8)
        chip(real, 18, y, 9, r.abbr)
        _t(shim, r.abbr, 32, y, pal.IDENT, 10)
        _t(shim, str(r.wins), 158, y, pal.WIN, 10)
        _t(shim, str(r.losses), 192, y, pal.LOSS, 10)
        _t(shim, r.pct or "", 224, y, pal.AMBER, 10)
        gb = r.division_gb or "-"
        gb_color = pal.LABEL if gb in _LEADER_GB else pal.IDENT
        _t(shim, gb, 292, y, gb_color, 10)
        _t(shim, r.l10 or "", 350, y, pal.CYAN, 10, bold=False)
        streak = r.streak or ""
        _t(shim, streak, 420, y, _strk_color(streak), 10)
