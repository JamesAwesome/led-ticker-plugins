"""Scale-1 (smallsign) renderers: the two-band `FootballBandBoard` and the
`build_ticker_message` ticker line. Both are BDF text-glyph paths; scale>1
signs never reach them.

Band geometry (160x16): away band rows 0-7, home band rows 8-15. Chip x0-2;
abbrev x5; score x28; possession dot (3x3) x44; timeout pips (3x 2 px, 1-px
gaps) x53; down & distance x67 on the possessing band only (`STALE` sits in
that column on a band with no situation text); the quarter (top band) and
clock (bottom band) right-aligned. The x anchors are MINIMUMS: each column
starts at least `_GAP` px past the widest item of the column before it
(both bands share columns), so 2-digit scores push later columns right
instead of touching. Shapes (dot, pips) are recorded in `shape_extents`
for the clearance tripwire.
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

from led_ticker_football import _palette as pal
from led_ticker_football._models import GameInfo, status_lines, winner
from led_ticker_football._paint import pips, rect
from led_ticker_football.layouts.crawl import segments

X_ABBREV = 5
X_SCORE = 28
X_DOT = 44
X_PIPS = 53
X_SITUATION = 67
_GAP = 6
_DOT = 3
_PIP = 2
_PIP_GAP = 1
_PIPS_W = 3 * _PIP + 2 * _PIP_GAP


@attrs.define
class FootballBandBoard(FrameAwareBase):
    """Two bands: away on top, home below."""

    game: GameInfo
    now_fn: Callable[[], float] = attrs.field(default=time.time, kw_only=True)
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    # (team, 0-1 fade toward white); 0.0 = full AMBER. Score highlight.
    highlight: tuple[str, float] | None = attrs.field(default=None, kw_only=True)
    stale: bool = attrs.field(default=False, kw_only=True)
    bye: bool = attrs.field(default=False, kw_only=True)
    font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    # (name, x0, x1, band) of every shape the last draw painted.
    shape_extents: list[tuple[str, int, int, int]] = attrs.field(
        init=False, factory=list
    )

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

        def w(text: str) -> int:
            return measure_width(font, text, canvas) if text else 0

        def right(text: str, y: int, color: Color) -> None:
            if text:
                draw_text(canvas, font, text, width - w(text), y, color)

        if g.state == "future":
            y0, y1 = ys
            x = X_ABBREV
            at = " VS " if g.neutral_site else " @ "
            for text, color in (
                (g.away, pal.chip(g.away)[0]),
                (at, pal.GRAY),
                (g.home, pal.chip(g.home)[0]),
            ):
                x = draw_text(canvas, font, text, x, y0, color)
            if self.bye:
                draw_text(canvas, font, " BYE", x, y0, pal.GRAY)
            right(top, y0, pal.AMBER)
            venue = "STALE" if self.stale else g.venue.upper()
            # The venue shares the bottom band with the kickoff: ellipsize
            # it to >= _GAP short of the time's measured left edge.
            max_w = width - w(bottom) - _GAP - X_ABBREV if bottom else width - X_ABBREV
            if venue and w(venue) > max_w:
                while len(venue) > 1 and w(venue.rstrip() + "…") > max_w:
                    venue = venue[:-1]
                venue = venue.rstrip() + "…"
            draw_text(canvas, font, venue, X_ABBREV, y1, pal.DIM)
            right(bottom, y1, pal.WHITE)
            return canvas, cursor_pos + canvas.width

        sit = g.situation if g.state == "live" else None
        rows = ((g.away, g.away_score), (g.home, g.home_score))
        scores = [str(score) for _, score in rows]
        score_end = X_SCORE + max(w(t) for t in scores)
        show_shapes = sit is not None
        dot_x = max(X_DOT, score_end + _GAP)
        pips_x = max(X_PIPS, dot_x + _DOT + _GAP) if show_shapes else dot_x
        sit_x = (
            max(X_SITUATION, pips_x + _PIPS_W + _GAP)
            if show_shapes
            else max(X_SITUATION, score_end + _GAP)
        )
        hue = pal.RED if sit is not None and sit.red_zone else pal.CYAN
        stale_band = None
        if self.stale:
            # The band without situation text (the top one when both are free).
            poss_band = (
                1
                if sit is not None and sit.possession == g.home
                else 0
                if sit is not None and sit.possession == g.away
                else None
            )
            stale_band = 1 if poss_band == 0 else 0
        for band, (abbrev, _) in enumerate(rows):
            y = ys[band]
            r0 = band * half_h
            primary, _ = pal.chip(abbrev)
            rect(real, 0, r0, 2, r0 + half_h - 2 + band, primary)
            draw_text(canvas, font, abbrev, X_ABBREV, y, primary)
            draw_text(canvas, font, scores[band], X_SCORE, y, self._score_color(abbrev))
            if sit is not None:
                if sit.possession == abbrev:
                    cy = r0 + half_h // 2
                    dot_c = pal.RED if sit.red_zone else pal.WHITE
                    rect(real, dot_x, cy - 1, dot_x + _DOT - 1, cy + 1, dot_c)
                    self.shape_extents.append(("DOT", dot_x, dot_x + _DOT, band))
                tol = sit.away_timeouts if band == 0 else sit.home_timeouts
                pw = pips(
                    real,
                    pips_x,
                    r0 + half_h // 2 - _PIP // 2,
                    tol,
                    size=_PIP,
                    gap=_PIP_GAP,
                    lit=pal.WHITE,
                    spent=pal.DIM,
                )
                if pw:
                    self.shape_extents.append(("PIPS", pips_x, pips_x + pw, band))
                if sit.possession == abbrev and sit.down_distance:
                    draw_text(canvas, font, sit.down_distance, sit_x, y, hue)
            if stale_band == band:
                draw_text(canvas, font, "STALE", sit_x, y, pal.DIM)

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
    bye: bool = False,
) -> SegmentMessage:
    """One scrolling line — the SAME segments the hi-res crawl paints."""
    return SegmentMessage(
        segments(game, now, tz, stale=stale, bye=bye),
        center=True,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        font_color=font_color,
    )
