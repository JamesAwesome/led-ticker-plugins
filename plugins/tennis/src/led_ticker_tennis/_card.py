"""TennisMatchCard — the scale-dispatching story for tennis.scores (the
baseball `MLBGameCard` pattern).

One card per match. `draw()` resolves `(cfg_layout, scale, phys width)` via
`layouts.resolve_layout` on every call: scale <= 1 delegates to the legacy
text-glyph renderers (`_scoreboard.py`, cached on `self._legacy`); scale >
1 dispatches to the physical renderers in `layouts/`. A held layout
returns `cursor = canvas.width` — the WRAPPER's LOGICAL width, the units
the engine's hold-vs-scroll check compares against (returning `real.width`
would phantom-scroll). The crawl works in logical units end to end and
adds `self.padding` for the engine's scroll loop.
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

from led_ticker_tennis._models import MatchInfo
from led_ticker_tennis.layouts import resolve_layout
from led_ticker_tennis.layouts.crawl import render_crawl
from led_ticker_tennis.layouts.scoreboard import render_scoreboard


@attrs.define
class TennisMatchCard(FrameAwareBase):
    match: MatchInfo
    tz: Any
    cfg_layout: str = "auto"
    story_index: int = 0
    story_total: int = 1
    padding: int = 6
    show_ranking: bool = False
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _legacy: Any = attrs.field(init=False, default=None)

    def _legacy_story(self, layout: str) -> Any:
        if self._legacy is None:
            from led_ticker_tennis._scoreboard import (
                _build_match_message,
                _build_scoreboard_message,
            )

            if layout == "scoreboard":
                self._legacy = _build_scoreboard_message(
                    self.match,
                    self.tz,
                    bg_color=self.bg_color,
                    font=self.small_font,
                    font_color=self.font_color,
                )
            else:
                self._legacy = _build_match_message(
                    self.match,
                    self.tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    font_color=self.font_color,
                    show_ranking=self.show_ranking,
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
            w = render_crawl(
                canvas,
                self.match,
                self.tz,
                cursor_pos,
                y_offset=y_offset,
                hold_padding=self.padding,
                show_ranking=self.show_ranking,
            )
            return canvas, w + self.padding
        render_scoreboard(
            canvas,
            self.match,
            self.tz,
            y_offset=y_offset,
            story_index=self.story_index,
            story_total=self.story_total,
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
