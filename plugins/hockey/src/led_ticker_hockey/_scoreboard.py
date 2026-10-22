"""Scale-1 (smallsign) renderers: the two-band `HockeyBandBoard` and the
`build_ticker_message` ticker line. Both are BDF text-glyph paths; scale>1
signs never reach them.

Band geometry (the mockup's, 160x16): away band rows 0-7, home band rows
8-15. Chip x0-2; abbrev x5; score x28; `SOG` label x40 + value x60; `PP m:ss`
(or `EN`) x84; the period (top band) and clock (bottom band) right-aligned.
"""

import time
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    FONT_SMALL,
    Color,
    ColorProvider,
    DrawResult,
    Font,
    FrameAwareBase,
    SegmentMessage,
    compute_baseline_for_band,
    draw_text,
    measure_width,
    safe_scale,
    unwrap_to_real,
)

from led_ticker_hockey import _palette as pal
from led_ticker_hockey._models import (
    GameInfo,
    fmt_clock,
    live_pp_seconds,
    status_lines,
    winner,
)
from led_ticker_hockey._paint import rect
from led_ticker_hockey.layouts.crawl import segments

_X_ABBREV = 5
_X_SCORE = 28
_X_SOG_LABEL = 40
_X_SOG_VALUE = 60
_X_SOG_VALUE_STALE = 68  # "STALE" is 25px wide: push the value clear of it
_X_SITUATION = 84


@attrs.define
class HockeyBandBoard(FrameAwareBase):
    """Two bands: away on top, home below."""

    game: GameInfo
    now_fn: Callable[[], float] = attrs.field(default=time.time, kw_only=True)
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    # (team, 0-1 fade toward white); 0.0 = full AMBER. Goal-flash highlight.
    highlight: tuple[str, float] | None = attrs.field(default=None, kw_only=True)
    stale: bool = attrs.field(default=False, kw_only=True)
    font: Font = attrs.field(default=FONT_SMALL, kw_only=True)

    def _score_color(self, abbrev: str) -> Color:
        g = self.game
        if self.highlight is not None and self.highlight[0] == abbrev:
            return pal.lerp(pal.AMBER, pal.WHITE, self.highlight[1])
        if g.state == "final":
            win = winner(g)
            if win is not None:
                return pal.GREEN if win == abbrev else pal.LOSER
        return pal.WHITE

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        g = self.game
        font = self.font
        if self.bg_color is not None:
            canvas.Fill(self.bg_color.red, self.bg_color.green, self.bg_color.blue)
        scale = safe_scale(canvas)
        half_h = canvas.height // 2
        baseline = compute_baseline_for_band(font, half_h, scale, valign="center")
        width = canvas.width
        now = self.now_fn()
        tz = self.tz or ZoneInfo("UTC")
        real = unwrap_to_real(canvas)
        top, bottom = status_lines(g, now, tz)
        ys = [baseline + y_offset, half_h + baseline + y_offset]

        def right(text: str, y: int, color: Color) -> None:
            if text:
                draw_text(
                    canvas,
                    font,
                    text,
                    width - measure_width(font, text, canvas),
                    y,
                    color,
                )

        if g.state == "future":
            y0, y1 = ys
            x = _X_ABBREV
            for text, color in (
                (g.away, pal.chip(g.away)[0]),
                (" @ ", pal.GRAY),
                (g.home, pal.chip(g.home)[0]),
            ):
                x = draw_text(canvas, font, text, x, y0, color)
            right(top, y0, pal.AMBER)
            draw_text(canvas, font, g.venue.upper(), _X_ABBREV, y1, pal.DIM)
            right(bottom, y1, pal.WHITE)
            return canvas, cursor_pos + canvas.width

        sit = g.situation
        for band, abbrev, score, sog in (
            (0, g.away, g.away_score, g.away_sog),
            (1, g.home, g.home_score, g.home_sog),
        ):
            y = ys[band]
            r0 = band * half_h
            primary, _ = pal.chip(abbrev)
            rect(real, 0, r0, 2, r0 + half_h - 2 + band, primary)
            draw_text(canvas, font, abbrev, _X_ABBREV, y, primary)
            draw_text(canvas, font, str(score), _X_SCORE, y, self._score_color(abbrev))
            if sog is not None:
                label = "STALE" if self.stale else "SOG"
                draw_text(canvas, font, label, _X_SOG_LABEL, y, pal.DIM)
                vx = _X_SOG_VALUE_STALE if self.stale else _X_SOG_VALUE
                draw_text(canvas, font, str(sog), vx, y, pal.CYAN)
            if g.state == "live" and sit is not None:
                if sit.pp_team == abbrev:
                    pp = fmt_clock(live_pp_seconds(g, now))
                    text = f"PP {pp}".rstrip()
                    draw_text(canvas, font, text, _X_SITUATION, y, pal.AMBER)
                elif sit.en_team == abbrev:
                    draw_text(canvas, font, "EN", _X_SITUATION, y, pal.AMBER)

        if g.state == "final":
            right(top, ys[0], pal.WHITE)
            right(bottom, ys[1], pal.AMBER)
        else:
            right(top, ys[0], pal.AMBER)
            right(bottom, ys[1], pal.WHITE)
        return canvas, cursor_pos + canvas.width


def build_ticker_message(
    game: GameInfo,
    now: float,
    tz: ZoneInfo,
    *,
    font: Font | None = None,
    bg_color: Color | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
    """One scrolling line — the SAME segments the hi-res crawl paints."""
    return SegmentMessage(
        segments(game, now, tz),
        center=True,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        font_color=font_color,
    )
