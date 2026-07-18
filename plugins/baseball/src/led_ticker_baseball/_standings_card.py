"""MLBStandingsBoard — the scale-dispatching story for one division's
standings, replacing the per-team SegmentMessage rows at scale>1.

At draw time: scale > 1 dispatches to the physical
`layouts.standings_board.render_standings_board` renderer (held layout;
returns the WRAPPER's LOGICAL width so the engine's hold-vs-scroll check
takes the hold branch — same phase-1 lesson as `MLBGameCard`, see its
module docstring). scale <= 1 has no hires renderer to fall back to, so
instead of collapsing the division onto one line, the board forwards to
one of its pre-built `legacy_rows` (the same per-team SegmentMessages the
"ticker" layout builds) — one row per SECTION VISIT, advancing via
`reset_frame()` (core calls this once per visit). This keeps the
smallsign UX (rows cycle one at a time, engine-scrolled via the forwarded
cursor) without needing a canvas at `update()` time to decide anything.
"""

from typing import TYPE_CHECKING, Any

import attrs
from led_ticker.plugin import (
    Color,
    ColorProvider,
    DrawResult,
    FrameAwareBase,
    safe_scale,
)

from led_ticker_baseball.layouts.standings_board import render_standings_board

if TYPE_CHECKING:
    from led_ticker_baseball.standings import TeamStanding


@attrs.define
class MLBStandingsBoard(FrameAwareBase):
    division_name: str
    rows: list[TeamStanding]
    legacy_rows: list[Any]
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _legacy_idx: int = attrs.field(init=False, default=0)

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        scale = safe_scale(canvas)
        if scale > 1:
            render_standings_board(
                canvas, self.division_name, self.rows, y_offset=y_offset
            )
            # Held layout: return the WRAPPER's logical width (not the real
            # canvas width) so the engine's `cursor_pos > canvas.width`
            # hold-vs-scroll check (core ticker.py) compares like units and
            # takes the hold branch — phase-1 lesson (MLBGameCard).
            return canvas, canvas.width
        if not self.legacy_rows:
            return canvas, 0
        idx = self._legacy_idx % len(self.legacy_rows)
        return self.legacy_rows[idx].draw(
            canvas, cursor_pos, y_offset=y_offset, font_color=font_color
        )

    def reset_frame(self) -> None:
        super().reset_frame()
        self._legacy_idx += 1
