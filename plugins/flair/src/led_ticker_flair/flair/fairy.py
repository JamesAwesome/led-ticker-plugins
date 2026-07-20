"""flair.fairy — a fairy (white-hot dot) crosses the panel trailing gold
pixie dust, settling a line that then opens to reveal the incoming widget.
Tinkerbell-inspired. Variants: fairy.forward / fairy.reverse /
fairy.alternating (sprite-family convention).

Spec: docs/superpowers/specs/2026-07-20-flair-fairy-transition-design.md
Perf contract: everything per-frame is a pure function of ``t`` — no caches,
no warm threads, and NO PARTICLE STATE: every spark derives from
_mix(column, k, quantized t). Per-firing state is the path list + flags.
The open-phase gap/blackout core is duplicated from lightning.py on purpose
(rule of three — see the spec's Code shape section)."""

import math
import random
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, is_scaled, snap_reset, unwrap_to_real

_CUTOVER = 0.5  # flight ends / open begins (flight is the star)
_OPEN_END = 0.9  # fraction of the open phase over which the gap fully opens
_TRAIL_FRAC = 0.30  # spark trail length, fraction of panel width
_DRIFT_LOGICAL = 4  # max end-to-end path drift, logical px
_WOBBLE_LOGICAL = 1.5  # max sine wobble amplitude, logical px
_SPARK_SPREAD_LOGICAL = 4  # vertical spark scatter around the path
_SPARKS_PER_COL = 3
_GOLD = (255, 215, 120)
_CREAM = (255, 240, 200)
_AMBER = (230, 170, 60)
_HEAD_COLOR = (255, 255, 255)


def _mix(*parts: int) -> int:
    """Deterministic 32-bit mixer (order-sensitive) for stateless sparks."""
    acc = 0x9E3779B9
    for p in parts:
        acc ^= (p & 0xFFFFFFFF) + 0x9E3779B9 + ((acc << 6) & 0xFFFFFFFF) + (acc >> 2)
        acc &= 0xFFFFFFFF
    return acc


def plan_path(w: int, h: int, scale: int, rng: random.Random) -> list[int]:
    """Per-REAL-column path y: nearly straight — baseline in the center
    third, a few logical px of end-to-end drift, small sine wobble.
    Single-valued per column (the reveal machinery requires it)."""
    y0 = h / 2.0 + rng.uniform(-0.8, 0.8) * (h / 6.0)
    drift = rng.uniform(-_DRIFT_LOGICAL, _DRIFT_LOGICAL) * scale
    wob_amp = rng.uniform(0.5, _WOBBLE_LOGICAL) * scale
    wob_freq = rng.uniform(1.5, 3.0) * 2.0 * math.pi / max(1, w)
    wob_phase = rng.uniform(0.0, 2.0 * math.pi)
    span = max(1, w - 1)
    path = []
    for x in range(w):
        y = y0 + drift * (x / span - 0.5) + wob_amp * math.sin(wob_freq * x + wob_phase)
        path.append(max(1, min(h - 2, int(round(y)))))
    return path


def _tinted(
    base: tuple[int, int, int], dust: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Rescale a palette color's channels by the dust tint (gold -> tint)."""
    return (
        min(255, int(base[0] * dust[0] / _GOLD[0])),
        min(255, int(base[1] * dust[1] / _GOLD[1])),
        min(255, int(base[2] * dust[2] / _GOLD[2])),
    )


class Fairy:
    """Pixie-dust flight + line-open reveal (forward: flies left->right).

    Flight (t < _CUTOVER): outgoing draws normally; a white-hot head crosses
    the panel scattering stateless gold sparks behind it and settling a thin
    gold line at its path. Open (t >= _CUTOVER): outgoing cuts out; incoming
    draws in full, everything outside the widening gap (path +/- d) is
    blacked out, and the two edges are thin gold lines with twinkling
    sparks. Knobs: ``seed`` (pins path + spark field), ``color`` (dust
    tint). Direction is NOT a knob — use fairy.reverse / fairy.alternating."""

    min_frames = 24
    _direction = 1  # +1: left->right; -1: right->left (FairyReverse)

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
        self.dust_color: tuple[int, int, int] = (
            (color[0], color[1], color[2]) if color is not None else _GOLD
        )
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._path: list[int] = []  # empty == needs (re)plan
        self._plan_key: tuple[int, int, int] | None = None
        self._dims: tuple[int, int] = (0, 0)
        self._scale = 1
        self._thickness = 1
        self._d_need = 0.0
        self._spark_seed = 0
        self._last_t = 1.0

    # --- planning -----------------------------------------------------------

    def _ensure_plan(self, canvas):
        # `real` is re-derived on EVERY call and never cached on self
        # (constraint #1: frame.swap() hands back a different buffer).
        scale = canvas.scale if is_scaled(canvas) else 1
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if not self._path or self._plan_key != key:
            self._path = plan_path(real.width, real.height, scale, self._rng)
            self._plan_key = key
            self._dims = (real.width, real.height)
            self._scale = scale
            self._thickness = max(1, scale // 2)
            h = real.height
            self._d_need = (
                max(max(py, h - py) for py in self._path) + self._thickness + 1
            )
            self._spark_seed = self._rng.randrange(1 << 30)
        return real

    # --- flight phase -------------------------------------------------------

    def _head_x(self, s: float, w: int) -> float:
        return s * (w - 1) if self._direction > 0 else (1.0 - s) * (w - 1)

    def _paint_flight(self, real, t):
        w, h = self._dims
        path = self._path
        thk = self._thickness
        scale = self._scale
        set_pixel = real.SetPixel
        dust = self.dust_color
        # 0.7x keeps the settled line clearly GOLD on black (0.45x read as
        # muddy brown in the gate render).
        line_col = tuple(int(c * 0.7) for c in dust)
        s = min(1.0, t / _CUTOVER)
        head = self._head_x(s, w)
        trail_len = max(4, int(_TRAIL_FRAC * w))
        spread = _SPARK_SPREAD_LOGICAL * scale
        qt = round(t * 997)
        for x in range(w):
            behind = (head - x) * self._direction
            if behind < 0:
                continue  # ahead of the fairy
            # settled line under everything already flown over
            y0 = path[x] - (thk - 1) // 2
            for y in range(y0, y0 + thk):
                if 0 <= y < h:
                    set_pixel(x, y, *line_col)
            if behind > trail_len:
                continue  # dust has faded to just the line
            # stateless sparks: presence, offset, base brightness from _mix.
            # Sub-linear age falloff keeps the region near the head dense and
            # bright (linear falloff read as sparse/dim in the gate render).
            age = (1.0 - behind / trail_len) ** 0.6
            for k in range(_SPARKS_PER_COL):
                rr = _mix(self._spark_seed, x, k)
                if rr % 4 == 0:
                    continue  # this (column, k) slot never sparks
                dy = (rr >> 4) % (2 * spread + 1) - spread
                tw = ((_mix(rr, qt) >> 3) & 0xFF) / 255.0
                b = age * (0.5 + 0.5 * tw)
                base = (_CREAM, _GOLD, _AMBER)[(rr >> 2) % 3]
                col = _tinted(base, dust)
                col = tuple(int(c * b) for c in col)
                sy = path[x] + dy
                if not (0 <= sy < h):
                    continue
                set_pixel(x, sy, *col)
                if b > 0.75 and scale > 1:  # bright sparks -> 4-point star
                    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx2, ny2 = x + ox, sy + oy
                        if 0 <= nx2 < w and 0 <= ny2 < h:
                            set_pixel(nx2, ny2, *col)
        # white-hot head drawn as a 4-point SPARKLE STAR (core + plus-arms),
        # gold at the arm tips — a plain square read as a cursor in the gate
        # render.
        hx = int(round(head))
        r_h = max(1, scale // 2)
        halo = _tinted(_GOLD, dust)
        hy = path[hx] if 0 <= hx < w else h // 2
        for ox in range(-r_h, r_h + 1):
            for oy in range(-r_h, r_h + 1):
                x2, y2 = hx + ox, hy + oy
                if 0 <= x2 < w and 0 <= y2 < h:
                    set_pixel(x2, y2, *_HEAD_COLOR)
        arm = 2 * r_h + 1
        for direction_x, direction_y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for step in range(r_h + 1, arm + 1):
                x2 = hx + direction_x * step
                y2 = hy + direction_y * step
                if 0 <= x2 < w and 0 <= y2 < h:
                    col = _HEAD_COLOR if step <= arm - 1 else halo
                    set_pixel(x2, y2, *col)

    # --- open phase (gap/blackout core duplicated from lightning.py --------
    # on purpose: rule of three, see spec Code shape) ------------------------

    def _gap_d(self, t: float) -> float:
        p = (t - _CUTOVER) / (SNAP_THRESHOLD - _CUTOVER)
        p = min(1.0, max(0.0, p / _OPEN_END))
        ease = p * p * (3.0 - 2.0 * p)
        return ease * self._d_need

    def _paint_open(self, real, t):
        w, h = self._dims
        path = self._path
        thk = self._thickness
        d = self._gap_d(t)
        set_pixel = real.SetPixel
        dust = self.dust_color
        edge_col = _tinted(_GOLD, dust)
        qt = round(t * 997)
        for x in range(w):
            lo = path[x] - d  # gap: lo < y < hi
            hi = path[x] + d
            top_black_end = min(h, max(0, math.ceil(lo)))  # [0, end) black
            bot_black_start = max(0, math.floor(hi) + 1)  # [start, h) black
            for y in range(0, top_black_end):
                set_pixel(x, y, 0, 0, 0)
            for y in range(bot_black_start, h):
                set_pixel(x, y, 0, 0, 0)
            # gold edges over the innermost black rows, with twinkle sparkle
            sparkle = (_mix(self._spark_seed, x, 7, qt) & 0xFF) > 200
            col = _CREAM if sparkle else edge_col
            for y in range(max(0, top_black_end - thk), top_black_end):
                set_pixel(x, y, *col)
            for y in range(bot_black_start, min(h, bot_black_start + thk)):
                set_pixel(x, y, *col)

    # --- driver -------------------------------------------------------------

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
            self._path = []  # re-fire from fresh entropy (empty == replan)
            self._plan_key = None
            self._rng = random.Random()
        self._last_t = t

        real = self._ensure_plan(canvas)

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            self._paint_flight(real, t)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._paint_open(real, t)
        return canvas


class FairyReverse(Fairy):
    """Fairy flying right->left."""

    _direction = -1


class FairyAlternating:
    """Cycles fairy.forward -> fairy.reverse per firing (pacman convention)."""

    def __init__(self, color: Any = None, seed: Any = None) -> None:
        self._transitions: list[Any] = [
            Fairy(color=color, seed=seed),
            FairyReverse(color=color, seed=seed),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 24)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
