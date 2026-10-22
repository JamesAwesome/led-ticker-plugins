"""HockeyGameCard — the scale-dispatching story for hockey.scores (the
tennis `TennisMatchCard` pattern).

One card per game. `draw()` resolves `(cfg_layout, scale, phys width)` via
`layouts.resolve_layout` on every call: scale <= 1 delegates to the
bitmap renderers in `_scoreboard.py` (cached on `self._legacy`); scale > 1
dispatches to the physical renderers in `layouts/`. A held layout returns
`cursor = canvas.width`, the WRAPPER's LOGICAL width (what the engine's
hold-vs-scroll check compares against). The crawl adds `self.padding`.

The widget reuses a card across polls and assigns `game` / `stale` in
place. The cached legacy story must never show an old game: the band board
is re-synced on every draw, the ticker message is rebuilt when `game` or
the layout changes.
"""

import time
from collections.abc import Callable
from typing import Any

import attrs
from led_ticker.plugin import (
    FONT_SMALL,
    Color,
    ColorProvider,
    DrawResult,
    Font,
    FrameAwareBase,
    safe_scale,
    unwrap_to_real,
)

from led_ticker_hockey._models import GameInfo, Goal
from led_ticker_hockey._scoreboard import HockeyBandBoard, build_ticker_message
from led_ticker_hockey.layouts import resolve_layout
from led_ticker_hockey.layouts.crawl import render_crawl
from led_ticker_hockey.layouts.scoreboard import render_scoreboard


@attrs.define
class HockeyGameCard(FrameAwareBase):
    game: GameInfo
    tz: Any
    cfg_layout: str = "auto"
    padding: int = 6
    now_fn: Callable[[], float] = time.time
    tracked: frozenset[str] = frozenset()
    stale: bool = False
    base_hold: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    pending_goals: list[Goal] = attrs.field(init=False, factory=list)
    _legacy: Any = attrs.field(init=False, default=None)
    _legacy_for: tuple[str, GameInfo] | None = attrs.field(init=False, default=None)

    @property
    def hold_time(self) -> float:
        """Per-story hold the engine reads (`max(section, widget)`)."""
        return self.base_hold

    def queue_goals(self, goals: list[Goal]) -> None:
        """Goals to celebrate (stub: stored only until celebrations land)."""
        self.pending_goals.extend(goals)

    def _legacy_story(self, layout: str) -> Any:
        if layout == "scoreboard":
            board = self._legacy
            if not isinstance(board, HockeyBandBoard):
                board = HockeyBandBoard(
                    self.game,
                    now_fn=self.now_fn,
                    tz=self.tz,
                    bg_color=self.bg_color,
                    font=self.small_font if self.small_font is not None else FONT_SMALL,
                )
                self._legacy = board
            board.game = self.game
            board.stale = self.stale
            self._legacy_for = (layout, self.game)
            return board
        built = self._legacy_for
        if (
            self._legacy is None
            or built is None
            or built[0] != layout
            or (built[1] is not self.game)
        ):
            self._legacy = build_ticker_message(
                self.game,
                self.now_fn(),
                self.tz,
                font=self.font,
                bg_color=self.bg_color,
                font_color=self.font_color,
            )
            self._legacy_for = (layout, self.game)
        return self._legacy

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        scale = safe_scale(canvas)
        real = unwrap_to_real(canvas)
        layout = resolve_layout(self.cfg_layout, scale, real.width)
        if scale <= 1:
            return self._legacy_story(layout).draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        now = self.now_fn()
        if layout == "ticker":
            w = render_crawl(
                canvas,
                self.game,
                now,
                self.tz,
                cursor_pos,
                y_offset=y_offset,
                hold_padding=self.padding,
            )
            return canvas, w + self.padding
        render_scoreboard(
            canvas,
            self.game,
            now,
            self.tz,
            y_offset=y_offset,
            stale=self.stale,
            highlight=None,
        )
        return canvas, canvas.width

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        if self._legacy is not None:
            self._legacy.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        if self._legacy is not None:
            self._legacy.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        if self._legacy is not None:
            self._legacy.resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        if self._legacy is not None:
            self._legacy.reset_frame()
