"""Shared ``.alternating`` / ``.random`` delegate bases for flair.interlock
and flair.blinds. Laser and accordion keep their own wrappers.

A wrapper holds a list of independent single-variant instances and picks
one per FIRING. A new firing is ``t == 0.0 or t < _last_t`` (the accordion
refire rule): t == 0 always starts a firing, so one cancelled right after
its t=0 frame can't make the next firing replay the stale variant; equal
non-zero ``t`` is a repeated frame, not a refire.
"""

import random
from typing import Any


class Cycling:
    """Cycles through ``transitions`` in order, one per firing."""

    def __init__(self, transitions: list[Any]) -> None:
        self._transitions: list[Any] = transitions
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        return self._transitions[0].min_frames

    def _next_index(self) -> int:
        return (self._index + 1) % len(self._transitions)

    def frame_at(
        self, t: float, canvas: Any, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Any:
        if t == 0.0 or t < self._last_t:
            self._index = self._next_index()
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )


class RandomNoRepeat(Cycling):
    """Picks a variant per firing, never the same one back-to-back
    (WipeRandom policy). ``_rng`` is an instance attribute so tests can
    seed it."""

    def __init__(self, transitions: list[Any]) -> None:
        super().__init__(transitions)
        self._rng = random.Random()

    def _next_index(self) -> int:
        choices = [i for i in range(len(self._transitions)) if i != self._index]
        return self._rng.choice(choices)
