"""FootballGameCard — the scale-dispatching story for football.scores (the
hockey `HockeyGameCard` pattern).

One card per game. `draw()` resolves `(cfg_layout, scale, phys width)` via
`layouts.resolve_layout` on every call: scale <= 1 delegates to the bitmap
renderers in `_scoreboard.py` (cached on `self._legacy`); scale > 1
dispatches to the physical renderers in `layouts/`. A held layout returns
`cursor = canvas.width`, the WRAPPER's LOGICAL width (what the engine's
hold-vs-scroll check compares against). The crawl adds `self.padding`.

The widget reuses a card across polls and assigns `game` / `stale` / `bye`
in place. The cached legacy story must never show an old game: the band
board is re-synced on every draw, the ticker message is rebuilt when
`game`, `stale`, `bye` or the layout changes.

Scoring plays: `queue_plays` routes a tracked team's play to `pending`
(newest `MAX_QUEUED` kept) and any other team's play to a brief score
`highlight`. A play with the same PRE-TRY snapshot (`pre_extra_score`) as
one already pending is that touchdown's extra point (or a correction) and
REPLACES it; `replace_plays` does the same for plays the widget knows were
already celebrated, and never queues. While `pending`, `draw()` plays the
celebration timeline off `_frame_count` (held, on every layout; the board
while the frame counter is paused, i.e. transition compositing) and
`hold_time` covers it plus the board's own hold. A play is CONSUMED only
once it was actually shown on a live (unpaused, ticking) frame, so a stale
frame count from an earlier visit or transition compositing never eats an
unseen celebration. Two kinds of run:

- a VISIT run (slideshow): `reset_frame()` snapshots `pending` into
  `_playing` at frame 0; consumption happens at the next visit entry.
- a SELF-STARTED run (`ticker` / `one_at_a_time` sections, which never
  call `reset_frame()`): with no snapshot, the first live draw snapshots
  `pending` and records `_run_start`; the timeline plays off
  `_run_pos`, which advances only on frames the card is actually drawn
  (a card hidden behind another takeover is still advanced by core), and
  the draw after it ends consumes, clears the snapshot and draws the
  board.

Every celebration frame clears the panel first and returns `canvas.width`:
a full-panel takeover, even mid side-by-side scroll.

Either way, plays queued mid-run wait for the next run; an extra point
still folds into its running touchdown (`_swap` covers `_playing`).

Demo cards carry `demo_plays`: re-queued after every third completed
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

from led_ticker_football._celebration import (
    CELEBRATION_FRAMES,
    CELEBRATION_SECONDS,
    HIGHLIGHT_FRAMES,
    MAX_QUEUED,
    flash_word,
    phase_at,
    render_detail,
    render_flash,
)
from led_ticker_football._models import GameInfo, ScoringPlay, pre_extra_score
from led_ticker_football._palette import chip as _chip
from led_ticker_football._scoreboard import FootballBandBoard, build_ticker_message
from led_ticker_football.layouts import resolve_layout
from led_ticker_football.layouts.crawl import render_crawl
from led_ticker_football.layouts.scoreboard import render_scoreboard

# While a celebration is due the card holds for it AND then shows the board
# for at least this long, so the celebration never eats the board's hold.
BOARD_FLOOR = 4.0
DEMO_EVERY = 3  # demo cards re-celebrate after every 3rd completed visit
# Scroll-mode sections have no visits: a demo card re-celebrates this many
# live frames (12 s) after its last self-started run ended.
DEMO_REST_FRAMES = DEMO_EVERY * CELEBRATION_FRAMES


@attrs.define
class ScaleMemo:
    """Shared by one widget's cards: set once any draw (paused or not)
    sees scale > 1, so a new game's card never hands core a hi-res
    `bg_color` fill. Core caches `bg_color` per visit, so the first hi-res
    visit was read before this was set: the hi-res draw paths clear the
    panel for it when leftmost and live. Once per widget instance the
    color can still show during the transition into that first visit, a
    title-less scroll section's scroll-in, or a one_at_a_time section's
    first tick (see CLAUDE.md *Palette*)."""

    hires: bool = False


@attrs.define
class FootballGameCard(FrameAwareBase):
    game: GameInfo
    tz: Any
    cfg_layout: str = "auto"
    padding: int = 6
    now_fn: Callable[[], float] = time.time
    tracked: frozenset[str] = frozenset()
    stale: bool = False
    bye: bool = False
    base_hold: float = 0.0
    # The configured fill; core reads the `bg_color` property below.
    _bg_color: Color | None = attrs.field(default=None, kw_only=True, alias="bg_color")
    scale_memo: ScaleMemo = attrs.field(factory=ScaleMemo, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    demo_plays: tuple[ScoringPlay, ...] = attrs.field(default=(), kw_only=True)
    pending: list[ScoringPlay] = attrs.field(init=False, factory=list)
    highlight: tuple[str, int] | None = attrs.field(init=False, default=None)
    _shown: set[str] = attrs.field(init=False, factory=set)
    # The visit's celebration snapshot, taken at visit entry. None = no
    # visit yet. Plays queued mid-visit wait for the next turn.
    _playing: list[ScoringPlay] | None = attrs.field(init=False, default=None)
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
    # Scroll sections: the engine keeps decrementing `pos` under a takeover.
    # `_run_cursor` is the EFFECTIVE cursor where a self-started run began;
    # `_x_shift` (effective = raw + shift) freezes the card there until the
    # raw cursor next increases (a fresh pass), tracked in `_last_cursor`.
    _run_cursor: int = attrs.field(init=False, default=0)
    _x_shift: int = attrs.field(init=False, default=0)
    _last_cursor: int | None = attrs.field(init=False, default=None)
    _run_frame: int = attrs.field(init=False, default=-1)
    _demo_visits: int = attrs.field(init=False, default=0)
    _hl_shown: bool = attrs.field(init=False, default=False)
    _hl_frame: int = attrs.field(init=False, default=-1)
    _legacy: Any = attrs.field(init=False, default=None)
    # (layout, game, stale, bye) the cached legacy story was built for.
    _legacy_for: tuple[str, GameInfo, bool, bool] | None = attrs.field(
        init=False, default=None
    )

    @property
    def bg_color(self) -> Color | None:
        """What core fills before every draw (at every scale): the
        configured color on scale-1 signs, None once a hi-res draw was
        seen. `bg_color` is a scale-1 option."""
        return None if self.scale_memo.hires else self._bg_color

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

    def _snap(self, play: ScoringPlay) -> tuple[int, int]:
        return pre_extra_score(play, self.game.home)

    def queue_plays(self, plays: list[ScoringPlay]) -> None:
        """Tracked-team plays celebrate; any other play highlights the
        score. No tracked teams means nothing celebrates. A play whose
        pre-try snapshot is already pending replaces it (the extra point)."""
        for p in plays:
            if self._swap(p):
                continue
            if p.team in self.tracked:
                self.pending.append(p)
            else:
                self.highlight = (p.team, HIGHLIGHT_FRAMES)
        del self.pending[:-MAX_QUEUED]

    def replace_plays(self, plays: list[ScoringPlay]) -> None:
        """Follow-ups to plays already queued or celebrated: swap a matching
        entry (so the detail shows the full score), never celebrate again."""
        for p in plays:
            self._swap(p)

    def _swap(self, play: ScoringPlay) -> bool:
        """Replace the pending play with `play`'s pre-try snapshot."""
        snap = self._snap(play)
        swapped = False
        for seq in (self.pending, self._playing or []):
            for i, old in enumerate(seq):
                if self._snap(old) == snap:
                    if old.key in self._shown:
                        self._shown.add(play.key)
                    seq[i] = play
                    swapped = True
        return swapped

    def drop_overturned(self) -> None:
        """Drop pending plays the current score no longer supports."""
        g = self.game
        self.pending = [
            p
            for p in self.pending
            if p.away_score <= g.away_score and p.home_score <= g.home_score
        ]

    def _board_highlight(self) -> tuple[str, float] | None:
        """The fade to pass the board this draw. The countdown ticks only
        on live frames that actually draw it (not paused, not frame 0,
        once per frame), so transition compositing never burns it unseen."""
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
            self.queue_plays(list(self.demo_plays))
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
        play = playing[idx]
        if self._frame_count > 0:  # a live frame (paused returned above)
            self._shown.add(play.key)
        # A full-panel takeover: clear what earlier widgets painted this
        # tick (side-by-side scroll). bg_color is scale-1 only.
        bg = self._bg_color
        if bg is not None and safe_scale(canvas) <= 1:
            canvas.Fill(bg.red, bg.green, bg.blue)
        else:
            unwrap_to_real(canvas).Clear()
        if name == "detail":
            render_detail(
                canvas, self.game, play, f, y_offset=y_offset, font=self.small_font
            )
        else:
            render_flash(
                canvas,
                _chip(play.team)[0],
                name == "flash_on",
                flash_word(play.kind),
                y_offset=y_offset,
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
        if self.demo_plays:
            self._demo_rest_from = self._frame_count

    def _consume_shown(self) -> None:
        if self._shown:
            self.pending = [p for p in self.pending if p.key not in self._shown]
            self._shown.clear()

    def _count_demo_visit(self) -> None:
        if self.demo_plays:
            self._demo_visits += 1
            if self._demo_visits % DEMO_EVERY == 0 and not self.pending:
                self.queue_plays(list(self.demo_plays))

    def _legacy_story(self, layout: str) -> Any:
        if layout == "scoreboard":
            board = self._legacy
            if not isinstance(board, FootballBandBoard):
                board = FootballBandBoard(
                    self.game,
                    now_fn=self.now_fn,
                    tz=self.tz,
                    bg_color=self._bg_color,
                    font=self.small_font if self.small_font is not None else FONT_SMALL,
                )
                self._legacy = board
            board.game = self.game
            board.stale = self.stale
            board.bye = self.bye
            self._legacy_for = (layout, self.game, self.stale, self.bye)
            return board
        built = self._legacy_for
        if (
            self._legacy is None
            or built is None
            or built[0] != layout
            or built[1] is not self.game
            or built[2] != self.stale
            or built[3] != self.bye
        ):
            self._legacy = build_ticker_message(
                self.game,
                self.now_fn(),
                self.tz,
                font=self.font,
                bg_color=self._bg_color,
                font_color=self.font_color,
                stale=self.stale,
                bye=self.bye,
            )
            self._legacy_for = (layout, self.game, self.stale, self.bye)
        return self._legacy

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if safe_scale(canvas) > 1:
            self.scale_memo.hires = True
        if self._last_cursor is None or cursor_pos > self._last_cursor:
            self._x_shift = 0  # a fresh pass: draw honestly again
        self._last_cursor = cursor_pos
        if self._celebrate(canvas, y_offset, cursor_pos):
            return canvas, canvas.width
        cursor_pos += self._x_shift
        scale = safe_scale(canvas)
        real = unwrap_to_real(canvas)
        layout = resolve_layout(self.cfg_layout, scale, real.width)
        if scale <= 1:
            story = self._legacy_story(layout)
            if isinstance(story, FootballBandBoard):
                story.highlight = self._board_highlight()
            return story.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        if self._bg_color is not None and cursor_pos <= 0 and not self._frame_paused:
            # Core caches `bg_color` once per slideshow visit, so a widget's
            # first hi-res visit is filled with it before the memo is set.
            # Leftmost (nothing of another widget's to the left) and live
            # (never clobber transition compositing): own the panel.
            real.Clear()
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
                bye=self.bye,
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
            bye=self.bye,
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
        self._playing = list(self.pending)
        self._run_start = None  # a visit's run starts at frame 0
        self._demo_rest_from = None  # visits re-arm by count instead
        self._x_shift, self._last_cursor = 0, None
        super().reset_frame()
        if self._legacy is not None:
            self._legacy.reset_frame()
