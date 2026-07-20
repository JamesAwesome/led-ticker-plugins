"""flair.lightning — a zigzag bolt strikes across the outgoing widget, then
the crack pulls apart revealing the incoming widget underneath.

Spec: docs/superpowers/specs/2026-07-19-flair-lightning-transition-design.md
Perf contract (poker-arc lesson): everything per-frame is a pure function of
``t`` — no caches, no memos, no warm threads. The only per-firing state is
the bolt polyline, flattened to one crack-y per real column at plan time.
"""

import math
import random
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, is_scaled, snap_reset, unwrap_to_real

_CUTOVER = 0.45  # strike ends / peel begins
_OPEN_END = 0.9  # fraction of the peel phase over which the gap fully opens
_SEG_MIN_LOGICAL = 6  # zigzag vertex pitch bounds, LOGICAL px
_SEG_MAX_LOGICAL = 10
_HEAD_COLOR = (255, 255, 255)
_TRAIL_COLOR = (150, 190, 255)  # electric blue-white default
_FLICKER_LO = 0.72  # per-frame trail brightness floor
_HEAD_W_LOGICAL = 2  # head cluster half-width, LOGICAL px


def plan_bolt(w: int, h: int, scale: int, rng: random.Random) -> list[int]:
    """Per-REAL-column crack y for a fresh bolt.

    Random-walk zigzag: a vertex every _SEG_MIN.._SEG_MAX logical px with
    strictly alternating vertical direction, y confined to the center HALF
    of the panel (h/2 ± h/4 — James's visual-gate pick: even peaks at the
    A-variant pitch, B-variant prominence). Piecewise-linear between
    vertices."""
    band_half = h / 4.0
    cy = h / 2.0
    xs = [0]
    while xs[-1] < w - 1:
        step = rng.randint(_SEG_MIN_LOGICAL, _SEG_MAX_LOGICAL) * scale
        xs.append(min(w - 1, xs[-1] + step))
    if len(xs) < 2:  # degenerate 1px-wide panel
        xs.append(w - 1)
    sign = rng.choice((-1, 1))
    ys = []
    for _ in xs:
        ys.append(cy + sign * rng.uniform(0.35, 1.0) * band_half)
        sign = -sign
    crack = [0] * w
    seg = 0
    for x in range(w):
        while x > xs[seg + 1]:
            seg += 1
        x0, x1 = xs[seg], xs[seg + 1]
        y0, y1 = ys[seg], ys[seg + 1]
        f = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        crack[x] = int(round(y0 + (y1 - y0) * f))
    return crack


class Lightning:
    """Zigzag bolt strike + crack-open reveal.

    Strike (t < _CUTOVER): outgoing draws normally; the bolt draws itself
    left->right with a white-hot head and a flickering blue-white trail.
    Peel (t >= _CUTOVER): the outgoing cuts out; each frame draws the
    incoming in full, blacks out everything outside the opened gap
    (crack +/- d(t)), and paints glowing crack edges at the boundary.
    Knobs: ``seed`` pins the bolt (default None = fresh bolt every firing,
    detected via t regressing); ``color`` tints the trail."""

    min_frames = 24

    def __init__(self, color: Any = None, seed: Any = None) -> None:
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError(f"seed must be an int; got {seed!r}")
        if color is not None and (
            not isinstance(color, (list, tuple))
            or len(color) != 3
            or not all(
                isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255
                for c in color
            )
        ):
            raise ValueError(f"color must be [r, g, b] 0-255 ints; got {color!r}")
        self.seed = seed
        self.trail_color: tuple[int, int, int] = (
            (color[0], color[1], color[2]) if color is not None else _TRAIL_COLOR
        )
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._crack: list[int] = []  # empty == needs (re)plan
        self._plan_key: tuple[int, int, int] | None = None
        self._dims: tuple[int, int] = (0, 0)
        self._scale = 1
        self._thickness = 1
        self._d_need = 0.0
        self._flicker_seed = 0
        self._last_t = 1.0

    def _ensure_plan(self, canvas):
        # `real` is re-derived on EVERY call and never cached on self:
        # frame.swap() hands back a different back-buffer each tick
        # (constraint #1). Only geometry-derived data is retained.
        scale = canvas.scale if is_scaled(canvas) else 1
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if not self._crack or self._plan_key != key:
            self._crack = plan_bolt(real.width, real.height, scale, self._rng)
            self._plan_key = key
            self._dims = (real.width, real.height)
            self._scale = scale
            self._thickness = max(1, scale // 2)
            h = real.height
            # Smallest half-gap that reveals every pixel in every column,
            # plus edge thickness so the glowing edges are off-panel too.
            self._d_need = (
                max(max(cy, h - cy) for cy in self._crack) + self._thickness + 1
            )
            self._flicker_seed = self._rng.randrange(1 << 30)
        return real

    def _flicker(self, t: float) -> tuple[int, int, int]:
        """Deterministic per-frame trail brightness (no wall clock, no
        global random): keyed on the firing's flicker seed + quantized t."""
        r = random.Random(self._flicker_seed * 1000003 + round(t * 997))
        b = _FLICKER_LO + (1.0 - _FLICKER_LO) * r.random()
        tr, tg, tb = self.trail_color
        return (int(tr * b), int(tg * b), int(tb * b))

    def _paint_bolt(self, real, t):
        w, h = self._dims
        crack = self._crack
        thk = self._thickness
        set_pixel = real.SetPixel
        s = min(1.0, t / _CUTOVER)
        head_x = int(round(s * (w - 1)))
        col = self._flicker(t)
        for x in range(0, head_x + 1):
            y0 = crack[x] - (thk - 1) // 2
            for y in range(y0, y0 + thk):
                if 0 <= y < h:
                    set_pixel(x, y, *col)
        hw = max(1, _HEAD_W_LOGICAL * self._scale)
        for x in range(max(0, head_x - hw), min(w, head_x + hw + 1)):
            y0 = crack[x] - (thk - 1) // 2
            for y in range(y0 - 1, y0 + thk + 1):
                if 0 <= y < h:
                    set_pixel(x, y, *_HEAD_COLOR)

    def _gap_d(self, t: float) -> float:
        """Half-height of the open gap at t: smoothstep from 0 at cutover to
        _d_need at _OPEN_END of the peel phase (fully open well before SNAP,
        guaranteeing deterministic full reveal)."""
        p = (t - _CUTOVER) / (SNAP_THRESHOLD - _CUTOVER)
        p = min(1.0, max(0.0, p / _OPEN_END))
        ease = p * p * (3.0 - 2.0 * p)
        return ease * self._d_need

    def _paint_peel(self, real, t):
        w, h = self._dims
        crack = self._crack
        thk = self._thickness
        d = self._gap_d(t)
        set_pixel = real.SetPixel
        col = self._flicker(t)
        for x in range(w):
            lo = crack[x] - d  # gap: lo < y < hi
            hi = crack[x] + d
            top_black_end = min(h, max(0, math.ceil(lo)))  # [0, end) black
            bot_black_start = max(0, math.floor(hi) + 1)  # [start, h) black
            for y in range(0, top_black_end):
                set_pixel(x, y, 0, 0, 0)
            for y in range(bot_black_start, h):
                set_pixel(x, y, 0, 0, 0)
            # glowing crack edges over the innermost black rows
            for y in range(max(0, top_black_end - thk), top_black_end):
                set_pixel(x, y, *col)
            for y in range(bot_black_start, min(h, bot_black_start + thk)):
                set_pixel(x, y, *col)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t <= 0.0:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            return canvas
        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas

        refired = t < self._last_t
        if refired and self.seed is None:
            self._crack = []  # re-fire from fresh entropy (empty == replan)
            self._plan_key = None
            self._rng = random.Random()
        self._last_t = t

        real = self._ensure_plan(canvas)

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            self._paint_bolt(real, t)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._paint_peel(real, t)
        return canvas
