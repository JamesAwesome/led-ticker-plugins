"""Scale-1 (smallsign) renderers: the two-band `HockeyBandBoard` and the
`build_ticker_message` ticker line. Both are BDF text-glyph paths; scale>1
signs never reach them.

Band geometry (the mockup's, 160x16): away band rows 0-7, home band rows
8-15. Chip x0-2; abbrev x5; score x28; `SOG` (or `STALE`) label x40 + value
x60; `PP m:ss` (or `EN`, live play only — hidden in intermission) x84; the
period (top band) and clock (bottom band) right-aligned. The x anchors are
MINIMUMS: each column starts at least `_GAP` px past the widest text of
the column before it (both bands share columns), so 2-digit scores, the
`STALE` label and 2-digit SOG push later columns right instead of touching.
The 8x8 sport icon (`:hockey.puck:`) sits `_ICON_GAP` px left of the period
when it keeps `_GAP` from the top band's columns, and is left out
otherwise; a next-game card puts it at x0 of the top band with the matchup
`_ICON_GAP` px after it (left out when that would crowd the date). The icon
is recorded in `shape_extents` for the clearance tripwire.
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
from led_ticker_hockey._paint import rect, sprite
from led_ticker_hockey.emoji import PUCK
from led_ticker_hockey.layouts.crawl import segments

_X_ABBREV = 5
_X_SCORE = 28
_X_SOG_LABEL = 40
_X_SOG_VALUE = 60
_X_SITUATION = 84
_GAP = 6
_ICON = 8  # the sport icon (`:hockey.puck:`), one band tall
_ICON_GAP = 2  # icon -> the text it labels


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
    # (name, x0, x1, band) of every shape the last draw painted (the icon).
    shape_extents: list[tuple[str, int, int, int]] = attrs.field(
        init=False, factory=list
    )

    def _icon(self, real: Any, x: int, y: int) -> None:
        sprite(real, PUCK, x, y)
        self.shape_extents.append(("ICON", x, x + _ICON, 0))

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
        self.shape_extents = []
        # Core fills `bg_color` before every draw; never clear here (a scroll
        # section's earlier widgets are already on the canvas this tick).
        ox = cursor_pos  # a scroll section's cursor; 0 when held
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
                    ox + width - measure_width(font, text, canvas),
                    y,
                    color,
                )

        if g.state == "future":
            y0, y1 = ys
            names = (
                (g.away, pal.chip(g.away)[0]),
                (" @ ", pal.GRAY),
                (g.home, pal.chip(g.home)[0]),
            )
            run = sum(measure_width(font, t, canvas) for t, _ in names)
            date_x = width - (measure_width(font, top, canvas) if top else 0)
            x = ox + _X_ABBREV
            if _ICON + _ICON_GAP + run + _GAP <= date_x:
                self._icon(real, ox, y_offset)
                x = ox + _ICON + _ICON_GAP
            for text, color in names:
                x = draw_text(canvas, font, text, x, y0, color)
            right(top, y0, pal.AMBER)
            draw_text(canvas, font, g.venue.upper(), ox + _X_ABBREV, y1, pal.DIM)
            right(bottom, y1, pal.WHITE)
            return canvas, cursor_pos + canvas.width

        def w(text: str) -> int:
            return measure_width(font, text, canvas)

        def col(minimum: int, texts: list[str], prev: int) -> int:
            """Column x: the anchor, or clear of the previous column."""
            return max(minimum, prev + _GAP) if texts else prev

        sit = g.situation if g.state == "live" and not g.in_intermission else None
        rows = (
            (g.away, g.away_score, g.away_sog),
            (g.home, g.home_score, g.home_sog),
        )
        scores = [str(score) for _, score, _ in rows]
        labels = [
            "STALE" if self.stale else ("SOG" if sog is not None else "")
            for _, _, sog in rows
        ]
        values = [str(sog) if sog is not None else "" for _, _, sog in rows]
        score_end = _X_SCORE + max(w(t) for t in scores)
        label_x = max(_X_SOG_LABEL, score_end + _GAP)
        label_end = label_x + max(w(t) for t in labels)
        value_x = col(_X_SOG_VALUE, [t for t in labels if t], label_end)
        value_end = value_x + max(w(t) for t in values)
        sit_x = col(_X_SITUATION, [t for t in values if t], value_end)
        top_end = 0  # right edge of the top band's columns
        for band, (abbrev, _, _) in enumerate(rows):
            y = ys[band]
            # the chip rides PushUp/PushDown with the text
            r0 = band * half_h + y_offset
            primary, _ = pal.chip(abbrev)
            rect(real, ox, r0, ox + 2, r0 + half_h - 2 + band, primary)
            ends = [
                draw_text(canvas, font, abbrev, ox + _X_ABBREV, y, primary),
                draw_text(
                    canvas,
                    font,
                    scores[band],
                    ox + _X_SCORE,
                    y,
                    self._score_color(abbrev),
                ),
            ]
            if labels[band]:
                ends.append(
                    draw_text(canvas, font, labels[band], ox + label_x, y, pal.DIM)
                )
            if values[band]:
                ends.append(
                    draw_text(canvas, font, values[band], ox + value_x, y, pal.CYAN)
                )
            if sit is not None:
                if sit.pp_team == abbrev:
                    pp = fmt_clock(live_pp_seconds(g, now))
                    text = f"PP {pp}".rstrip()
                    ends.append(draw_text(canvas, font, text, ox + sit_x, y, pal.AMBER))
                elif sit.en_team == abbrev:
                    ends.append(draw_text(canvas, font, "EN", ox + sit_x, y, pal.AMBER))
            if band == 0:
                top_end = max(ends) - ox

        top_w = measure_width(font, top, canvas) if top else 0
        icon_x = width - top_w - _ICON_GAP - _ICON if top else width - _ICON
        if icon_x >= top_end + _GAP:
            self._icon(real, ox + icon_x, y_offset)

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
    stale: bool = False,
) -> SegmentMessage:
    """One scrolling line — the SAME segments the hi-res crawl paints."""
    return SegmentMessage(
        segments(game, now, tz, stale=stale),
        center=True,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        font_color=font_color,
    )
