"""MLBStandingsBoard — the scale-dispatching story for one division's
standings, replacing the per-team SegmentMessage rows at scale>1.

At draw time: scale > 1 dispatches to the physical
`layouts.standings_board.render_standings_board` renderer (held layout;
returns the WRAPPER's LOGICAL width so the engine's hold-vs-scroll check
takes the hold branch — same phase-1 lesson as `MLBGameCard`, see its
module docstring). scale <= 1 has no hires renderer to fall back to, so
instead of collapsing the division onto one line, the board forwards to
one of its pre-built `legacy_rows` (the same per-team SegmentMessages the
"ticker" layout builds) — one row per SECTION VISIT. This keeps the
smallsign UX (rows cycle one at a time, engine-scrolled via the forwarded
cursor) without needing a canvas at `update()` time to decide anything.

Row-advance semantics (visit-idempotent): core calls `reset_frame()`
TWICE per visit when a widget transition is configured — `run_transition`'s
`_reset_presenter(incoming)` plus `_show_one`'s own visit-entry reset (core
documents the double reset as harmless, so this counter must tolerate it).
A naive "+1 per reset" therefore advances by 2 per transitioned visit and
STICKS on even-length `legacy_rows`. Instead, `reset_frame()` only ARMS a
pending advance; the first UNPAUSED scale<=1 draw consumes it. Compositing
draws are excluded by the pause check: `run_transition` wraps its whole
loop in `pause_frame()` / `resume_frame()` (reset lands between pause and
the loop), so a paused draw renders the CURRENT row without consuming the
pending advance — the two resets collapse to exactly one advance at the
visit's first real draw. `_legacy_idx` starts at -1 with the flag armed so
the first-ever visit renders row 0 (paused compositing before any visit
clamps -1 up to row 0).
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
    # Quoted (not a bare deferred name): keeps class __annotations__ /
    # get_type_hints-style introspection from raising NameError on the
    # TYPE_CHECKING-only import. attrs collects string annotations fine.
    rows: "list[TeamStanding]"  # noqa: UP037 — introspection-safe forward ref
    legacy_rows: list[Any]
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    # Forwarded verbatim to `render_standings_board`'s `max_rows` — the
    # renderer stays config-agnostic (geometry-table lookup only); this
    # field is how the widget's `board_rows` config knob reaches it.
    # Defaults to 5 so direct-construction call sites/tests (pre-#72) are
    # unaffected.
    board_rows: int = attrs.field(default=5, kw_only=True)
    _legacy_idx: int = attrs.field(init=False, default=-1)
    _pending_row_advance: bool = attrs.field(init=False, default=True)

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
                canvas,
                self.division_name,
                self.rows,
                y_offset=y_offset,
                max_rows=self.board_rows,
            )
            # Held layout: return the WRAPPER's logical width (not the real
            # canvas width) so the engine's `cursor_pos > canvas.width`
            # hold-vs-scroll check (core ticker.py) compares like units and
            # takes the hold branch — phase-1 lesson (MLBGameCard).
            return canvas, canvas.width
        if not self.legacy_rows:
            return canvas, 0
        # Consume the visit's pending advance on the first UNPAUSED draw
        # only — paused draws are transition compositing (see module
        # docstring) and must neither advance nor burn the advance.
        if self._pending_row_advance and not self._frame_paused:
            self._legacy_idx += 1
            self._pending_row_advance = False
        return self._active_legacy_row().draw(
            canvas, cursor_pos, y_offset=y_offset, font_color=font_color
        )

    def _active_legacy_row(self) -> Any:
        # max(): before the first visit's consume, _legacy_idx is -1; a
        # paused compositing draw of a board's first-ever appearance
        # clamps up to row 0 instead of -1 % len (== the LAST row).
        idx = max(self._legacy_idx, 0) % len(self.legacy_rows)
        return self.legacy_rows[idx]

    # Forward frame hooks to the currently-selected legacy row (scale<=1
    # only — see module docstring) so its frame-aware effects (rainbow /
    # color_cycle font_color) animate as they did pre-branch, when each row
    # was itself the engine-visited story. Mirrors MLBGameCard's forwarding
    # to its cached `_legacy` story exactly (same guard-then-forward shape).
    # `advance_frame`/`pause_frame`/`resume_frame` always target whichever
    # row is CURRENTLY active (`_legacy_idx` doesn't change until the next
    # visit's first unpaused draw), so a row's counters only advance while
    # its own row is on screen — same as the pre-branch per-row-story
    # behavior.
    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        # super() no-ops while paused (FrameAwareBase.advance_frame) — mirror
        # that here so a paused advance_frame call can't sneak the forwarded
        # row's counter forward during transition compositing.
        if self.legacy_rows and not self._frame_paused:
            self._active_legacy_row().advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        if self.legacy_rows:
            self._active_legacy_row().pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        if self.legacy_rows:
            self._active_legacy_row().resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        # Arm (idempotently) rather than advance — see module docstring.
        self._pending_row_advance = True
        # Forward AFTER the arm-flag logic above so the board's own
        # visit-idempotent row-advance semantics are untouched; the
        # forwarded row is still the pre-advance (currently active) one —
        # the new row isn't selected until the visit's first unpaused draw.
        if self.legacy_rows:
            self._active_legacy_row().reset_frame()
