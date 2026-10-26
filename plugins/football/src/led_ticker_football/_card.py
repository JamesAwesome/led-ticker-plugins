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
`hold_time` covers it plus the board's own hold. A play is CONSUMED at the
next visit-entry `reset_frame()` only once it was actually shown on a live
(unpaused, ticking) frame, so a stale frame count from an earlier visit or
transition compositing never eats an unseen celebration.

Demo cards carry `demo_plays`: re-queued after every third completed visit
so a looping demo keeps showing the celebration.
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
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
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
    _demo_visits: int = attrs.field(init=False, default=0)
    _hl_shown: bool = attrs.field(init=False, default=False)
    _hl_frame: int = attrs.field(init=False, default=-1)
    _legacy: Any = attrs.field(init=False, default=None)
    # (layout, game, stale, bye) the cached legacy story was built for.
    _legacy_for: tuple[str, GameInfo, bool, bool] | None = attrs.field(
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

    def _celebrate(self, canvas: Any, y_offset: int) -> bool:
        """Paint the celebration frame if one is due; True when painted."""
        playing = self._playing
        if not playing or self._frame_paused:
            return False  # paused = transition compositing: the board
        phase = phase_at(self._frame_count, len(playing))
        if phase is None:
            return False
        idx, name, f = phase
        play = playing[idx]
        if self._frame_count > 0:  # a live frame (paused returned above)
            self._shown.add(play.key)
        if name == "detail":
            if self.bg_color is not None:
                bg = self.bg_color
                canvas.Fill(bg.red, bg.green, bg.blue)
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

    def _legacy_story(self, layout: str) -> Any:
        if layout == "scoreboard":
            board = self._legacy
            if not isinstance(board, FootballBandBoard):
                board = FootballBandBoard(
                    self.game,
                    now_fn=self.now_fn,
                    tz=self.tz,
                    bg_color=self.bg_color,
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
                bg_color=self.bg_color,
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
        if self._celebrate(canvas, y_offset):
            return canvas, canvas.width
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
            self.pending = [p for p in self.pending if p.key not in self._shown]
            self._shown.clear()
        if self._hl_shown:
            self.highlight = None  # it was on screen: consumed
        self._hl_shown = False
        self._hl_frame = -1
        # A completed visit ticked frames; a transition's extra reset
        # right before `_show_one`'s does not, so it isn't counted twice.
        if self.demo_plays and self._frame_count > 0:
            self._demo_visits += 1
            if self._demo_visits % DEMO_EVERY == 0 and not self.pending:
                self.queue_plays(list(self.demo_plays))
        self._playing = list(self.pending)
        super().reset_frame()
        if self._legacy is not None:
            self._legacy.reset_frame()
