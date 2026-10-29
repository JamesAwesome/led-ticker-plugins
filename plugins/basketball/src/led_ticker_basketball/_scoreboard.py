"""Scale-1 (smallsign) renderers: the single-band `BasketballBandBoard` and
the `build_ticker_message` ticker line. Both are BDF text-glyph paths;
scale>1 signs never reach them.

Band geometry (160x16, ONE 16-row band): away chip x0-2 and home chip at
the right edge (3 px, full height); the away run (abbrev, score) reads left
to right from `X_ABBREV`, the home run (score, abbrev) is mirrored against
the home chip, and the centre text (`Q4 1:48`, `HALF`, `FINAL/OT`) is
centred on the canvas in the free window between the two runs. Every
column is a MINIMUM: each item starts at least `_GAP` px past the measured
right edge of the one before it, so 3-digit scores and 4-letter abbrevs
push the window narrower instead of touching. When the centre cannot keep
`_GAP` from both runs it shrinks: the period drops (clock alone), then
`FINAL/OT` -> `F/OT`, then it ellipsizes. `STALE` joins the centre when it
fits and otherwise REPLACES it (a stale clock is the one thing the board
must not assert). A next-game card reads `NY (ball) PHI`: the 8x8
`:basketball.ball:` IS the `@` (and the `VS` on a neutral site), vertically
centred, `_ICON_GAP` px from each name. At 14 px it is narrower than the
18 px ` @ ` it replaces, so it is always drawn. `ball_at = False` puts the
text `@` / `VS` back and draws no ball. The chips and the ball are recorded
in `shape_extents` for the clearance tripwire.
"""

import time
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
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

from led_ticker_basketball import _palette as pal
from led_ticker_basketball._models import GameInfo, is_clutch, status_lines, winner
from led_ticker_basketball._paint import rect, sprite
from led_ticker_basketball.emoji import BALL
from led_ticker_basketball.layouts.crawl import segments

X_ABBREV = 5
_CHIP = 3
_GAP = 6
_ICON = 8  # the `:basketball.ball:` sprite on a next-game card
_ICON_GAP = 3  # each name -> the ball between them
_ELLIPSIS = "…"
_STALE = "STALE"

# One drawable run: (text, color, gap before it). Parts with a 0 gap are
# drawn flush (their own spaces carry the spacing).
Part = tuple[str, Color, int]


@attrs.define
class BasketballBandBoard(FrameAwareBase):
    """One band: away run left, centre status, home run right."""

    game: GameInfo
    now_fn: Callable[[], float] = attrs.field(default=time.time, kw_only=True)
    tz: ZoneInfo | None = None
    # team -> 0-1 fade; 0.0 = the team's primary, 1.0 = the score's rest colour.
    highlight: dict[str, float] | None = attrs.field(default=None, kw_only=True)
    stale: bool = attrs.field(default=False, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    # The next-game card's `@` / `VS` is the ball sprite; False keeps the text.
    ball_at: bool = attrs.field(default=True, kw_only=True)
    # (name, x0, x1) of every shape the last draw painted, INCLUSIVE bounds.
    shape_extents: list[tuple[str, int, int]] = attrs.field(init=False, factory=list)

    def _score_color(self, abbrev: str) -> Color:
        g = self.game
        rest = pal.WHITE
        if g.state == "final":
            win = winner(g)
            if win is not None:
                rest = pal.GREEN if win == abbrev else pal.LOSER
        if self.highlight and abbrev in self.highlight:
            # Fade to the colour the score will REST at (green/gray on a
            # final), so the pulse never ends with a snap.
            return pal.lerp(pal.chip(abbrev)[0], rest, self.highlight[abbrev])
        return rest

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
        width = canvas.width
        baseline = compute_baseline_for_band(
            font, canvas.height, scale, valign="center"
        )
        y = baseline + y_offset
        real = unwrap_to_real(canvas)
        now = self.now_fn()
        tz = self.tz or ZoneInfo("UTC")

        def w(text: str) -> int:
            return measure_width(font, text, canvas) if text else 0

        def run_w(parts: list[Part]) -> int:
            return sum(w(t) + gap for t, _c, gap in parts)

        def paint(parts: list[Part], x: int) -> None:
            for text, color, gap in parts:
                x += gap
                if text:
                    draw_text(canvas, font, text, ox + x, y, color)
                x += w(text)

        for abbrev, x0 in ((g.away, 0), (g.home, width - _CHIP)):
            x1 = x0 + _CHIP - 1
            top = y_offset  # the chips ride PushUp/PushDown with the text
            rect(
                real,
                ox + x0,
                top,
                ox + x1,
                top + canvas.height - 1,
                pal.chip(abbrev)[0],
            )
            self.shape_extents.append(("CHIP", ox + x0, ox + x1))
        left = max(X_ABBREV, _CHIP + _GAP)
        right = width - _CHIP - _GAP  # end-exclusive edge of the home run

        if g.state == "future":
            self._draw_future(
                g, now, tz, left, right, w, run_w, paint, real, ox, y_offset
            )
            return canvas, cursor_pos + canvas.width

        away_s, home_s = str(g.away_score), str(g.home_score)
        away_score_x = left + w(g.away) + _GAP
        home_abbrev_x = right - w(g.home)
        home_score_x = home_abbrev_x - _GAP - w(home_s)
        paint([(g.away, pal.chip(g.away)[0], 0)], left)
        paint([(away_s, self._score_color(g.away), 0)], away_score_x)
        paint([(home_s, self._score_color(g.home), 0)], home_score_x)
        paint([(g.home, pal.chip(g.home)[0], 0)], home_abbrev_x)

        lo = away_score_x + w(away_s) + _GAP
        hi = home_score_x - _GAP
        centre = self._centre_parts(g, now, tz)
        candidates = centre
        if self.stale:
            flag: Part = (_STALE, pal.DIM, _GAP)
            candidates = [[*c, flag] for c in centre] + [[(_STALE, pal.DIM, 0)]]
        for parts in candidates:
            x = _place(run_w(parts), lo, hi, width // 2)
            if x is not None:
                paint(parts, x)
                break
        else:
            if centre and not self.stale:
                parts = _ellipsize(centre[-1], hi - lo, w)
                x = _place(run_w(parts), lo, hi, width // 2) if parts else None
                if x is not None:
                    paint(parts, x)
        return canvas, cursor_pos + canvas.width

    @staticmethod
    def _centre_parts(g: GameInfo, now: float, tz: ZoneInfo) -> list[list[Part]]:
        """The centre's shrink order, widest first."""
        label, clock = status_lines(g, now, tz)
        if g.state == "final":
            if not clock:
                return [[(label, pal.WHITE, 0)]]
            ot = (f"/{clock}", pal.AMBER, 0)
            return [[(label, pal.WHITE, 0), ot], [(label[:1], pal.WHITE, 0), ot]]
        if not clock:
            return [[(label, pal.AMBER, 0)]]
        hue = pal.RED if is_clutch(g) else pal.WHITE
        return [[(label, pal.AMBER, 0), (f" {clock}", hue, 0)], [(clock, hue, 0)]]

    def _draw_future(
        self, g, now, tz, left, right, w, run_w, paint, real, ox, y_offset
    ) -> None:
        """`NY (ball) PHI` in team colours left; the day label (AMBER) and
        the tip-off (WHITE, `TBD` DIM) right-aligned against the home chip.
        The day label sheds its weekday, then the tip-off its AM/PM, then the
        day label goes, until the pair clears the names by `_GAP`. `STALE`
        sits left of the day label only when it fits with a day label kept.
        With `ball_at` off the ball is the text ` @ ` (` VS `, neutral) in
        GRAY."""
        at = " VS " if g.neutral_site else " @ "
        ball_x = left + w(g.away) + _ICON_GAP
        home_x = ball_x + _ICON + _ICON_GAP
        if not self.ball_at:
            home_x = left + w(g.away) + w(at)
        lo = home_x + w(g.home) + _GAP
        day, tip = status_lines(g, now, tz)
        tip_color = pal.DIM if g.time_tbd and tip == "TBD" else pal.WHITE
        days = [day]
        if day.count(" ") >= 2:
            days.append(day.split(" ", 1)[1])  # "WED NOV 15" -> "NOV 15"
        tips = [tip]
        if tip.endswith((" AM", " PM")):
            tips.append(tip[:-3])  # "7:30 PM" -> "7:30"
        # Shrink order: weekday first, then AM/PM, then the day label.
        pairs = [(days[0], tips[0]), (days[-1], tips[0])]
        pairs += [(days[0], tips[-1]), (days[-1], tips[-1])]
        pairs += [("", tips[0]), ("", tips[-1])]

        def parts_for(d: str, t: str, *, stale: bool) -> list[Part]:
            out: list[Part] = [(_STALE, pal.DIM, 0)] if stale else []
            if d:
                out.append((d, pal.AMBER, _GAP if stale else 0))
            if t:
                out.append((t, tip_color, _GAP if out else 0))
            return out

        candidates: list[list[Part]] = []
        if self.stale:
            candidates += [parts_for(d, t, stale=True) for d, t in pairs if d]
        candidates += [parts_for(d, t, stale=False) for d, t in pairs]
        paint([(g.away, pal.chip(g.away)[0], 0)], left)
        if self.ball_at:
            sprite(real, BALL, ox + ball_x, y_offset + (16 - _ICON) // 2)
            self.shape_extents.append(("ICON", ox + ball_x, ox + ball_x + _ICON - 1))
        else:
            paint([(at, pal.GRAY, 0)], left + w(g.away))
        paint([(g.home, pal.chip(g.home)[0], 0)], home_x)
        for parts in candidates:
            x = right - run_w(parts)
            if parts and x >= lo:
                paint(parts, x)
                return


def _place(need: int, lo: int, hi: int, centre: int) -> int | None:
    """x for a `need`-wide run centred on `centre`, slid (never shrunk) to
    stay inside [lo, hi]; None when the window is narrower than the run."""
    if need <= 0 or need > hi - lo:
        return None
    return max(lo, min(centre - need // 2, hi - need))


def _ellipsize(parts: list[Part], max_w: int, w) -> list[Part]:
    """The last shrink step: the run as one string, ellipsized to `max_w`,
    in its last part's colour (the clock's when there is one)."""
    text = "".join(t for t, _c, _g in parts)
    color = parts[-1][1]
    while len(text) > 1 and w(text.rstrip() + _ELLIPSIS) > max_w:
        text = text[:-1]
    out = text.rstrip() + _ELLIPSIS
    return [(out, color, 0)] if w(out) <= max_w else []


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
