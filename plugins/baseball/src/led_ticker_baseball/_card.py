"""MLBGameCard — the scale-dispatching story for baseball.scores.

One card per game. At draw time it resolves (cfg_layout, scale, phys width)
via layouts.resolve_layout: scale 1 delegates to the LEGACY text-glyph
renderers (unchanged smallsign behavior); scale > 1 dispatches to the new
physical renderers. Held layouts return cursor = physical width so the
engine holds; the crawl returns its advance width so the engine scrolls.
"""

from typing import Any

import attrs
from led_ticker.plugin import (
    Color,
    ColorProvider,
    DrawResult,
    Font,
    FrameAwareBase,
    safe_scale,
    unwrap_to_real,
)

from led_ticker_baseball.layouts import resolve_layout
from led_ticker_baseball.layouts.crawl import render_crawl
from led_ticker_baseball.layouts.scoreboard import render_scoreboard
from led_ticker_baseball.layouts.two_row import render_two_row


@attrs.define
class MLBGameCard(FrameAwareBase):
    game: Any
    team_abbr: str
    tz: Any
    cfg_layout: str = "auto"
    story_index: int = 0
    story_total: int = 1
    padding: int = 6
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font | None = attrs.field(default=None, kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _legacy: Any = attrs.field(init=False, default=None)

    def _legacy_story(self, layout: str) -> Any:
        if self._legacy is None:
            # Lazy import: the legacy builders live beside the legacy message
            # classes; importing here keeps module import light and avoids
            # cycles with scores.py (which imports MLBGameCard).
            from led_ticker_baseball._scoreboard import (
                _build_game_message,
                _build_scoreboard_message,
            )
            from led_ticker_baseball._two_row import _build_two_row_message

            if layout == "scoreboard":
                self._legacy = _build_scoreboard_message(
                    self.game,
                    self.team_abbr,
                    self.tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    font_color=self.font_color,
                )
            elif layout == "two_row":
                is_away = self.team_abbr == self.game.away_abbr
                series_wins = (
                    self.game.series_away_wins
                    if is_away
                    else self.game.series_home_wins
                )
                series_losses = (
                    self.game.series_home_wins
                    if is_away
                    else self.game.series_away_wins
                )
                self._legacy = _build_two_row_message(
                    self.game,
                    self.team_abbr,
                    self.tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    top_font=self.top_font,
                    top_row_height=self.top_row_height,
                    font_color=self.font_color,
                    series_wins=series_wins,
                    series_losses=series_losses,
                    series_total_games=self.story_total,
                )
            else:
                self._legacy = _build_game_message(
                    self.game,
                    self.team_abbr,
                    self.tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    font_color=self.font_color,
                )
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
        if layout == "ticker":
            w = render_crawl(canvas, self.game, self.tz, cursor_pos, y_offset=y_offset)
            return canvas, w + self.padding
        if layout == "scoreboard":
            render_scoreboard(
                canvas,
                self.game,
                self.tz,
                y_offset=y_offset,
                story_index=self.story_index,
                story_total=self.story_total,
            )
        else:
            render_two_row(
                canvas,
                self.game,
                self.tz,
                y_offset=y_offset,
                story_index=self.story_index,
                story_total=self.story_total,
            )
        return canvas, real.width

    # Forward frame hooks to the cached legacy story so its frame-aware
    # effects behave; keep our own base counters advancing too. Signatures
    # mirror FrameAwareBase's real hooks exactly (led_ticker_flight.widget
    # precedent for advance_frame's visit_id kwarg; reset_frame takes no
    # args on the base — do not invent a *args/**kwargs shape for it).
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
