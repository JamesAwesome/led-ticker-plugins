"""HockeyGameCard — the scale-dispatching story for hockey.scores (the
tennis `TennisMatchCard` pattern).

One card per game. `draw()` resolves `(cfg_layout, scale, phys width)` via
`layouts.resolve_layout` on every call: scale <= 1 delegates to the
bitmap renderers in `_scoreboard.py` (cached on `self._legacy`); scale > 1
dispatches to the physical renderers in `layouts/`. The returned cursor
is ABSOLUTE and LOGICAL (core's draw contract): a held layout paints at
`cursor_pos` and returns `cursor_pos + canvas.width` (the WRAPPER's
logical width, what the engine's hold-vs-scroll check compares against);
the crawl returns `cursor_pos + run + self.padding`. Core ends a widget in
a scroll section only once that end goes negative.

The widget reuses a card across polls and assigns `game` / `stale` in
place. The cached legacy story must never show an old game: the band board
is re-synced on every draw, the ticker message is rebuilt when `game`,
`stale` or the layout changes.

Goal celebrations: `queue_goals` routes a tracked team's goal to `pending`
(newest `MAX_QUEUED` kept) and any other goal to a brief score
`highlight`. A goal with the same `(away_score, home_score)` snapshot as
one already pending is a scoring change and REPLACES it (`replace_goals`
does the same for corrections the widget knows were already celebrated,
and never queues). While `pending`, `draw()` plays the celebration
timeline off `_frame_count` (held, on every layout; the board while the
frame counter is paused, i.e. transition compositing) and `hold_time`
covers it plus the board's own hold. A goal is CONSUMED only once it was
actually shown on a live (unpaused, ticking) frame, so a stale frame count
from an earlier visit or transition compositing never eats an unseen
celebration. Two kinds of run:

- a VISIT run (slideshow): a live `reset_frame()` snapshots `pending`
  into `_playing` at frame 0; consumption happens at the next visit
  entry. A PAUSED `reset_frame()` (a transition's) consumes but leaves no
  snapshot.
- a SELF-STARTED run (`ticker` / `one_at_a_time` sections, which never
  call `reset_frame()`): with no snapshot, the first live draw snapshots
  `pending` and records `_run_start`; the timeline plays off
  `_run_pos`, which advances only on frames the card is actually drawn
  (a card hidden behind another takeover is still advanced by core), and
  the draw after it ends consumes, clears the snapshot and draws the
  board.

Every celebration frame clears the panel first (to `bg_color` when set,
else black, at every scale) and returns `canvas.width`: a full-panel
takeover, even mid side-by-side scroll. Core keeps decrementing the
cursor beneath it, so a self-started run freezes the card's EFFECTIVE
cursor (`_x_shift`) where the run began, until the raw cursor next
increases (a fresh pass).

Either way, goals queued mid-run wait for the next run.

Demo cards carry `demo_goals`: re-queued after every third completed
visit so a looping demo keeps showing the celebration; in a scroll-mode
section (no visits) `DEMO_REST_FRAMES` live frames after a run ends.
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
    CELEBRATION_SECONDS,
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

# While a celebration is due the card holds for it AND then shows the board
# for at least this long, so the celebration never eats the board's hold.
BOARD_FLOOR = 4.0
DEMO_EVERY = 3  # demo cards re-celebrate after every 3rd completed visit
# Scroll-mode sections have no visits: a demo card re-celebrates this many
# live frames (12 s) after its last self-started run ended.
DEMO_REST_FRAMES = DEMO_EVERY * CELEBRATION_FRAMES


def _score_of(goal: Goal) -> tuple[int, int]:
    return (goal.away_score, goal.home_score)


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
    # Core fills it before every draw, at every scale (`reset_canvas`).
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    demo_goals: tuple[Goal, ...] = attrs.field(default=(), kw_only=True)
    pending: list[Goal] = attrs.field(init=False, factory=list)
    highlight: tuple[str, int] | None = attrs.field(init=False, default=None)
    _shown: set[str] = attrs.field(init=False, factory=set)
    # The visit's celebration snapshot, taken at visit entry. None = no
    # visit yet. Goals queued mid-visit wait for the next turn.
    _playing: list[Goal] | None = attrs.field(init=False, default=None)
    # None = the run's frame origin is 0 (a visit `reset_frame` started).
    # An int = a SELF-STARTED run: no visit snapshot existed (ticker /
    # one_at_a_time sections never reset), so it began at that frame.
    _run_start: int | None = attrs.field(init=False, default=None)
    # Frame the last self-started run ended: a scroll-mode demo card has no
    # visits to count, so it re-arms after `DEMO_REST_FRAMES` from here.
    _demo_rest_from: int | None = attrs.field(init=False, default=None)
    # A self-started run's position: it advances once per frame the card
    # is actually DRAWN, so a run hidden behind another takeover (still
    # advanced by core, not drawn) never burns out unseen.
    _run_pos: int = attrs.field(init=False, default=0)
    _run_frame: int = attrs.field(init=False, default=-1)
    # Scroll sections: the engine keeps decrementing `pos` under a takeover.
    # `_run_cursor` is the EFFECTIVE cursor where a self-started run began;
    # `_x_shift` (effective = raw + shift) freezes the card there until the
    # raw cursor next increases (a fresh pass), tracked in `_last_cursor`.
    _run_cursor: int = attrs.field(init=False, default=0)
    _x_shift: int = attrs.field(init=False, default=0)
    _last_cursor: int | None = attrs.field(init=False, default=None)
    _demo_visits: int = attrs.field(init=False, default=0)
    _hl_shown: bool = attrs.field(init=False, default=False)
    _hl_frame: int = attrs.field(init=False, default=-1)
    _legacy: Any = attrs.field(init=False, default=None)
    # (layout, game, stale) the cached legacy story was built for.
    _legacy_for: tuple[str, GameInfo, bool] | None = attrs.field(
        init=False, default=None
    )

    @property
    def hold_time(self) -> float:
        """Per-story hold the engine reads (`max(section, widget)`): with
        `n` celebrations due, `n * CELEBRATION_SECONDS` for them plus
        `max(base_hold, BOARD_FLOOR)` for the board after; else
        `base_hold`."""
        n = len(self._playing if self._playing is not None else self.pending)
        if not n:
            return self.base_hold
        return n * CELEBRATION_SECONDS + max(self.base_hold, BOARD_FLOOR)

    def queue_goals(self, goals: list[Goal]) -> None:
        """Tracked-team goals celebrate; any other goal highlights the
        score. No tracked teams means nothing celebrates. A goal whose
        score snapshot is already pending replaces it (scoring change)."""
        for g in goals:
            if self._swap(g):
                continue
            if g.team in self.tracked:
                self.pending.append(g)
            else:
                self.highlight = (g.team, HIGHLIGHT_FRAMES)
        del self.pending[:-MAX_QUEUED]

    def replace_goals(self, goals: list[Goal]) -> None:
        """Scoring changes to goals already queued or celebrated: swap a
        matching entry (so the detail shows the corrected scorer), never
        celebrate or highlight again."""
        for g in goals:
            self._swap(g)

    def _swap(self, goal: Goal) -> bool:
        """Replace the pending/playing goal with `goal`'s score snapshot."""
        snap = _score_of(goal)
        swapped = False
        for seq in (self.pending, self._playing or []):
            for i, old in enumerate(seq):
                if _score_of(old) == snap:
                    if old.key in self._shown:
                        self._shown.add(goal.key)
                    seq[i] = goal
                    swapped = True
        return swapped

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

    def _celebrate(self, canvas: Any, y_offset: int, cursor_pos: int) -> bool:
        """Paint the celebration frame if one is due; True when painted.
        `cursor_pos` is the RAW engine cursor of this draw."""
        live = not self._frame_paused and self._frame_count > 0
        rest = self._demo_rest_from
        if (
            live
            and self._playing is None
            and rest is not None
            and not self.pending
            and self._frame_count - rest >= DEMO_REST_FRAMES
        ):
            self._demo_rest_from = None
            self.queue_goals(list(self.demo_goals))
        if self._playing is None and self.pending and live:
            # No visit snapshot: a scroll-mode section. Start on this live frame.
            self._playing = list(self.pending)
            self._run_start = self._frame_count
            self._run_pos, self._run_frame = 0, self._frame_count
            self._run_cursor = cursor_pos + self._x_shift
        playing = self._playing
        if not playing or self._frame_paused:
            return False  # paused = transition compositing: the board
        if self._run_start is None:
            frame = self._frame_count  # a visit run: origin 0
        else:
            if self._frame_count != self._run_frame:
                self._run_pos += 1
                self._run_frame = self._frame_count
            frame = self._run_pos
        phase = phase_at(frame, len(playing))
        if phase is None:
            if self._run_start is not None:
                self._end_self_started_run(cursor_pos)
            return False
        idx, name, f = phase
        goal = playing[idx]
        if self._frame_count > 0:  # a live frame (paused returned above)
            self._shown.add(goal.key)
        # A full-panel takeover: clear what earlier widgets painted this
        # tick (side-by-side scroll), to the configured fill at every scale.
        bg = self.bg_color
        if bg is not None:
            canvas.Fill(bg.red, bg.green, bg.blue)
        else:
            unwrap_to_real(canvas).Clear()
        if name == "detail":
            render_detail(
                canvas, self.game, goal, f, y_offset=y_offset, font=self.small_font
            )
        else:
            render_flash(
                canvas, chip(goal.team)[0], name == "flash_on", y_offset=y_offset
            )
        return True

    def _end_self_started_run(self, cursor_pos: int) -> None:
        """Consume what the run showed, as `reset_frame` does at visit
        entry, and start a demo card's rest. The next live draw may
        self-start again from whatever is still pending. The board resumes
        where the takeover began: effective = raw + `_x_shift`."""
        self._x_shift = self._run_cursor - cursor_pos
        self._consume_shown()
        self._playing = None
        self._run_start = None
        if self.demo_goals:
            self._demo_rest_from = self._frame_count

    def _consume_shown(self) -> None:
        if self._shown:
            self.pending = [g for g in self.pending if g.key not in self._shown]
            self._shown.clear()

    def _count_demo_visit(self) -> None:
        if self.demo_goals:
            self._demo_visits += 1
            if self._demo_visits % DEMO_EVERY == 0 and not self.pending:
                self.queue_goals(list(self.demo_goals))

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
            self._legacy_for = (layout, self.game, self.stale)
            return board
        built = self._legacy_for
        if (
            self._legacy is None
            or built is None
            or built[0] != layout
            or built[1] is not self.game
            or built[2] != self.stale
        ):
            self._legacy = build_ticker_message(
                self.game,
                self.now_fn(),
                self.tz,
                font=self.font,
                bg_color=self.bg_color,
                font_color=self.font_color,
                stale=self.stale,
            )
            self._legacy_for = (layout, self.game, self.stale)
        return self._legacy

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if self._last_cursor is None or cursor_pos > self._last_cursor:
            self._x_shift = 0  # a fresh pass: draw honestly again
            self._run_cursor = cursor_pos  # a run spanning passes resumes here
        self._last_cursor = cursor_pos
        if self._celebrate(canvas, y_offset, cursor_pos):
            return canvas, canvas.width
        cursor_pos += self._x_shift
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
                stale=self.stale,
            )
            return canvas, cursor_pos + w + self.padding
        render_scoreboard(
            canvas,
            self.game,
            now,
            self.tz,
            y_offset=y_offset,
            stale=self.stale,
            highlight=self._board_highlight(),
            x_offset=cursor_pos,
        )
        return canvas, cursor_pos + canvas.width

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
        self._consume_shown()
        if self._hl_shown:
            self.highlight = None  # it was on screen: consumed
        self._hl_shown = False
        self._hl_frame = -1
        # A completed visit ticked frames; a transition's extra reset
        # right before `_show_one`'s does not, so it isn't counted twice.
        if self._frame_count > 0:
            self._count_demo_visit()
        # A paused reset is a transition's (`run_transition` /
        # `_scroll_transition` pause, then reset, the incoming widget). In a
        # slideshow `_show_one` resets again live and snapshots; a scroll
        # section never does, so leave no snapshot and let the next live
        # draw self-start.
        self._playing = None if self._frame_paused else list(self.pending)
        self._run_start = None  # a visit's run starts at frame 0
        self._demo_rest_from = None  # visits re-arm by count instead
        self._x_shift, self._last_cursor = 0, None
        super().reset_frame()
        if self._legacy is not None:
            self._legacy.reset_frame()
