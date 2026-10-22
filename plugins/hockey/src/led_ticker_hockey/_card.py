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

Goal celebrations: `queue_goals` routes a tracked team's goal to `pending`
(newest `MAX_QUEUED` kept) and any other goal to a brief score
`highlight`. While `pending`, `draw()` plays the celebration timeline off
`_frame_count` (held, on every layout) and `hold_time` stretches to cover
it. A goal is CONSUMED at the next visit-entry `reset_frame()` only once
it was actually shown on a live (unpaused, ticking) frame, so a stale
frame count from an earlier visit or transition compositing never eats
an unseen celebration.
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

from led_ticker_hockey._celebration import (
    CELEBRATION_FRAMES,
    HIGHLIGHT_FRAMES,
    MAX_QUEUED,
    phase_at,
    render_detail,
    render_flash,
)
from led_ticker_hockey._models import GameInfo, Goal
from led_ticker_hockey._palette import chip
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
    pending: list[Goal] = attrs.field(init=False, factory=list)
    highlight: tuple[str, int] | None = attrs.field(init=False, default=None)
    _shown: set[str] = attrs.field(init=False, factory=set)
    # The visit's celebration snapshot, taken at visit entry. None = no
    # visit yet. Goals queued mid-visit wait for the next turn.
    _playing: list[Goal] | None = attrs.field(init=False, default=None)
    _hl_shown: bool = attrs.field(init=False, default=False)
    _hl_frame: int = attrs.field(init=False, default=-1)
    _legacy: Any = attrs.field(init=False, default=None)
    _legacy_for: tuple[str, GameInfo] | None = attrs.field(init=False, default=None)

    @property
    def hold_time(self) -> float:
        """Per-story hold the engine reads (`max(section, widget)`),
        stretched to play every pending celebration."""
        n = len(self._playing if self._playing is not None else self.pending)
        return self.base_hold + n * CELEBRATION_FRAMES * 0.05

    def queue_goals(self, goals: list[Goal]) -> None:
        """Tracked-team goals celebrate; any other goal highlights the
        score. No tracked teams means nothing celebrates."""
        for g in goals:
            if g.team in self.tracked:
                self.pending.append(g)
            else:
                self.highlight = (g.team, HIGHLIGHT_FRAMES)
        del self.pending[:-MAX_QUEUED]

    def drop_overturned(self) -> None:
        """Drop pending goals the current score no longer supports."""
        g = self.game
        self.pending = [
            p
            for p in self.pending
            if p.away_score <= g.away_score and p.home_score <= g.home_score
        ]

    def _board_highlight(self) -> tuple[str, float] | None:
        """The fade to pass the board this draw. The countdown ticks only
        on live frames that actually draw it (not paused, not frame 0,
        once per frame), so a celebration painting over it or transition
        compositing never burns it unseen."""
        if self.highlight is None:
            return None
        team, left = self.highlight
        fade = (team, 1 - left / HIGHLIGHT_FRAMES)
        n = self._frame_count
        if not self._frame_paused and n > 0 and n != self._hl_frame:
            self._hl_frame = n
            self._hl_shown = True
            self.highlight = (team, left - 1) if left > 1 else None
        return fade

    def _celebrate(self, canvas: Any, y_offset: int) -> bool:
        """Paint the celebration frame if one is due; True when painted."""
        playing = self._playing
        if not playing:
            return False
        phase = phase_at(self._frame_count, len(playing))
        if phase is None:
            return False
        idx, name, f = phase
        goal = playing[idx]
        if not self._frame_paused and self._frame_count > 0:
            self._shown.add(goal.key)
        if name == "detail":
            if self.bg_color is not None:
                bg = self.bg_color
                canvas.Fill(bg.red, bg.green, bg.blue)
            render_detail(
                canvas, self.game, goal, f, y_offset=y_offset, font=self.small_font
            )
        else:
            render_flash(
                canvas, chip(goal.team)[0], name == "flash_on", y_offset=y_offset
            )
        return True

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
        if self._celebrate(canvas, y_offset):
            return canvas, canvas.width
        scale = safe_scale(canvas)
        real = unwrap_to_real(canvas)
        layout = resolve_layout(self.cfg_layout, scale, real.width)
        if scale <= 1:
            story = self._legacy_story(layout)
            if isinstance(story, HockeyBandBoard):
                story.highlight = self._board_highlight()
            return story.draw(
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
            highlight=self._board_highlight(),
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
        if self._shown:
            self.pending = [g for g in self.pending if g.key not in self._shown]
            self._shown.clear()
        self._playing = list(self.pending)
        if self._hl_shown:
            self.highlight = None  # it was on screen: consumed
        self._hl_shown = False
        self._hl_frame = -1
        super().reset_frame()
        if self._legacy is not None:
            self._legacy.reset_frame()
