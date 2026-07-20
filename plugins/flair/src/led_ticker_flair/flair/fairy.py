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
        y = (
            y0
            + drift * (x / span - 0.5)
            + wob_amp * math.sin(wob_freq * x + wob_phase)
        )
        path.append(max(1, min(h - 2, int(round(y)))))
    return path
