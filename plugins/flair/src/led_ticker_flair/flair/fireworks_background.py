"""flair.fireworks BACKGROUND effect — continuous fireworks painted BEHIND a
widget's content (``background = "flair.fireworks"``).

Same name as the ``flair.fireworks`` TRANSITION in ``fireworks.py`` but a
different registry (``api.background`` vs ``api.transition``), so the two
coexist: the transition fires once between widgets; this effect loops for
as long as the host widget is on screen. It reuses the transition's
``Burst`` plan shape, ``_spoke_angles`` geometry and the ``Fireworks``
class's two pure painters (``_draw_launch_streak`` / ``_draw_spokes``) so
the look is identical — a rocket streak rises from the bottom edge, pops
into a 10-14 spoke asterisk that eases open, coasts and fades.

Why ``background`` and not ``border`` (core >= 4.32): a widget has ONE
``border`` slot, and this effect shipped briefly as a border (plugins#128,
never released) — which meant fireworks OR a rainbow ring, not both. Core's
``background`` field is the dedicated "paint behind the content, every tick"
layer: hosts paint background → image → border → text, with its own
``frame_for("background")`` counter and ``frame_invariant`` fast-path gate.

Design rules (load-bearing):

- **Pure function of ``(frame_count, real dims)`` per instance.**
  Transitions pause the host's frame counter and re-render the widget
  many times at the SAME frame while compositing; a stateful particle sim
  would advance on every re-render and smear. Each burst slot's plan is
  derived from ``seed``, slot index and epoch (``frame // cycle``) only,
  and the per-frame phase is arithmetic on ``frame_count`` — so the same
  frame always paints the same pixels. ``seed=None`` draws ONE instance
  seed from OS entropy at construction (so two unseeded signs differ) but
  stays frame-pure afterwards.
- **Never paints black.** ``_draw_spokes``' tail/fade math can round a
  dim color to ``(0, 0, 0)``; the transition doesn't care (it paints onto a
  cleared canvas) but a background stamping black would erase a host's
  ``bg_color`` fill or image underneath. ``_LightOnly`` filters those
  calls out. Nothing here ever calls ``_fill_burst_black``.
- **Physical resolution.** Paints to ``unwrap_to_real(canvas)``, so a
  spoke is one real LED on the bigsign, not a 4×4 block; burst count /
  radius derive from the REAL panel dims (same as the transition).
"""

import math
import random
from typing import Any

from led_ticker.plugin import BackgroundEffectBase, unwrap_to_real

from led_ticker_flair.flair.fireworks import (
    _LAUNCH_OPEN_BOUNDARY,
    _RADIUS_MAX_FRAC,
    _RADIUS_MIN_FRAC,
    PALETTE,
    Burst,
    Fireworks,
    _spoke_angles,
    burst_count,
)

# One slot's full show (launch → open → fade → dark) at ``speed = 1.0``, in
# engine ticks (50 ms each) — 3 s. Slots are phase-staggered evenly across
# the cycle so with N slots a new rocket launches every ``cycle / N`` ticks.
CYCLE_FRAMES = 60

# Phase boundaries within a slot's local cycle position ``u`` in ``[0, 1)``,
# measured from the slot's own jittered start (``Burst.t_start``, in
# ``[0, _START_JITTER_MAX]``) so launches don't land on a metronome.
_LAUNCH_END = 0.30  # rocket streak rising; radius pinned at 0
_OPEN_END = 0.65  # asterisk eases open to radius_max at full brightness
_FADE_END = 0.90  # heads coast 35% farther while brightness fades to 0
_START_JITTER_MAX = 0.08  # keeps the whole show inside the cycle

# Coast growth past radius_max during the fade (mirrors the transition's
# ``_SPOKE_COAST_GROWTH`` look without coupling to its bloom timeline).
_COAST_GROWTH = 0.35

# ``bursts=`` override bounds — same band the transition allows.
_MIN_BURSTS = 2
_MAX_BURSTS = 8

# Floor on the resolved cycle length so an absurd ``speed`` can't collapse
# a show into a single frame.
_MIN_CYCLE_FRAMES = 8

# Bound on the per-(dims, slot, epoch) burst-plan cache; plans are cheap
# to rebuild and an unbounded dict would grow one entry per burst for the
# life of the process.
_PLAN_CACHE_MAX = 256

# Seed mixing: ``slot`` occupies bits 48+, ``epoch`` the low 48 bits, so
# (slot, epoch) pairs can't collide for any realistic uptime (2^48 ticks at
# 20 Hz is ~445,000 years).
_SLOT_SHIFT = 48
_SEED_MULT = 0x9E3779B97F4A7C15


class _LightOnly:
    """SetPixel proxy that drops pure-black writes (see module docstring)."""

    __slots__ = ("_real",)

    def __init__(self, real: Any) -> None:
        self._real = real

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        if r or g or b:
            self._real.SetPixel(x, y, r, g, b)


class FireworksBackground(BackgroundEffectBase):
    """Continuous fireworks behind the host widget's content (``background`` slot)."""

    frame_invariant = False
    # Continuous phase across ``loop_count > 1`` visits — a show that
    # restarted on every visit would replay the same opening rocket.
    restart_on_visit = False

    def __init__(
        self,
        bursts: int | None = None,
        colors: Any = None,
        speed: float = 1.0,
        seed: int | None = None,
    ) -> None:
        if bursts is not None and (
            not isinstance(bursts, int)
            or isinstance(bursts, bool)
            or not (_MIN_BURSTS <= bursts <= _MAX_BURSTS)
        ):
            raise ValueError(
                f"bursts must be an int in [{_MIN_BURSTS}, {_MAX_BURSTS}] or None; "
                f"got {bursts!r}"
            )

        palette: tuple[tuple[int, int, int], ...] = PALETTE
        if colors is not None:
            if not isinstance(colors, list) or not colors:
                raise ValueError(
                    "colors must be a non-empty list of [r, g, b] triples; "
                    f"got {colors!r}"
                )
            resolved = []
            for entry in colors:
                ok = (
                    isinstance(entry, list | tuple)
                    and len(entry) == 3
                    and all(
                        isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                        for v in entry
                    )
                )
                if not ok:
                    raise ValueError(
                        f"colors entry {entry!r} must be an [r, g, b] triple "
                        "of ints 0-255"
                    )
                resolved.append((entry[0], entry[1], entry[2]))
            palette = tuple(resolved)

        if (
            isinstance(speed, bool)
            or not isinstance(speed, int | float)
            or math.isnan(speed)
            or speed <= 0
        ):
            raise ValueError(f"speed must be a number > 0; got {speed!r}")

        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ValueError(f"seed must be an int or None; got {seed!r}")

        self.bursts = bursts
        self.palette = palette
        self.speed = float(speed)
        self.seed = seed
        self._seed = seed if seed is not None else random.SystemRandom().getrandbits(62)
        self._cycle = max(_MIN_CYCLE_FRAMES, round(CYCLE_FRAMES / self.speed))
        self._plans: dict[tuple[int, int, int, int], Burst] = {}

    # -- plan -------------------------------------------------------------

    def _slot_count(self, canvas: Any) -> int:
        real = unwrap_to_real(canvas)
        if self.bursts is not None:
            return self.bursts
        return burst_count(real.width, real.height)

    def _slot_seed(self, slot: int, epoch: int) -> int:
        return (self._seed * _SEED_MULT + (slot << _SLOT_SHIFT) + epoch) & (
            (1 << 63) - 1
        )

    def _burst_for(self, w: int, h: int, n: int, slot: int, epoch: int) -> Burst:
        key = (w, h, slot, epoch)
        b = self._plans.get(key)
        if b is not None:
            return b
        rng = random.Random(self._slot_seed(slot, epoch))
        band_w = w / n
        cx = slot * band_w + rng.uniform(0.2, 0.8) * band_w
        cy = rng.uniform(0.05, 2.0 / 3.0) * h
        radius_max = rng.uniform(_RADIUS_MIN_FRAC, _RADIUS_MAX_FRAC) * h
        t_start = rng.uniform(0.0, _START_JITTER_MAX)
        color = rng.choice(self.palette)
        b = Burst(
            cx=cx,
            cy=cy,
            radius_max=radius_max,
            t_start=t_start,
            t_burst_dur=1.0,  # unused by this effect; phases are absolute in ``u``
            color=color,
            spoke_angles=_spoke_angles(rng),
        )
        if len(self._plans) >= _PLAN_CACHE_MAX:
            self._plans.clear()
        self._plans[key] = b
        return b

    # -- paint ------------------------------------------------------------

    def paint(self, canvas: Any, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        w, h = real.width, real.height
        if w <= 0 or h <= 0:
            return
        n = self.bursts if self.bursts is not None else burst_count(w, h)
        target = _LightOnly(real)
        cycle = self._cycle

        for slot in range(n):
            # Even phase stagger across slots; ``epoch`` advances when this
            # slot's own phase wraps, so each slot re-plans independently.
            phase = frame_count / cycle + slot / n
            epoch = math.floor(phase)
            u0 = phase - epoch
            b = self._burst_for(w, h, n, slot, epoch)
            u = u0 - b.t_start
            if u < 0.0:
                continue  # jittered start not reached yet
            if u < _LAUNCH_END:
                p = (u / _LAUNCH_END) * _LAUNCH_OPEN_BOUNDARY
                Fireworks._draw_launch_streak(target, b, p, w, h)
            elif u < _OPEN_END:
                q = (u - _LAUNCH_END) / (_OPEN_END - _LAUNCH_END)
                radius = b.radius_max * (1.0 - (1.0 - q) ** 2)
                Fireworks._draw_spokes(target, b, radius, 1.0, w, h)
            elif u < _FADE_END:
                q = (u - _OPEN_END) / (_FADE_END - _OPEN_END)
                radius = b.radius_max * (1.0 + _COAST_GROWTH * (1.0 - (1.0 - q) ** 2))
                Fireworks._draw_spokes(target, b, radius, 1.0 - q, w, h)
            # else: dark until the slot's phase wraps into the next epoch
