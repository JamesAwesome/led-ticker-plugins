"""flair.lightning — a zigzag bolt strikes across the outgoing widget, then
the crack pulls apart revealing the incoming widget underneath.

Spec: docs/superpowers/specs/2026-07-19-flair-lightning-transition-design.md
Perf contract (poker-arc lesson): everything per-frame is a pure function of
``t`` — no caches, no memos, no warm threads. The only per-firing state is
the bolt polyline, flattened to one crack-y per real column at plan time.
"""

import random

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
    strictly alternating vertical direction, y confined to the center third
    of the panel (h/2 ± h/6). Piecewise-linear between vertices."""
    band_half = h / 6.0
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
