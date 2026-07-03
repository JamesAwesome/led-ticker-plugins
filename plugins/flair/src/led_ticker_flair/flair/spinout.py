"""flair.spinout — the outgoing widget propeller-spins out, then cuts."""

from typing import Any

from led_ticker.plugin import Canvas, make_rotation_surface

_DIRECTIONS = ("cw", "ccw")


class Spinout:
    # LOAD-BEARING (spec finding 1): outgoing bg holds for the whole spin
    # and the cross-scale re-wrap defers to the cut frame. Precedent:
    # SplitHorizontal / Scroll / Push*.
    scale_switch_at = 1.0

    def __init__(self, revolutions: int = 2, direction: str = "cw") -> None:
        bad_rev = not isinstance(revolutions, int) or isinstance(revolutions, bool)
        if bad_rev or revolutions < 1:
            raise ValueError(f"revolutions must be an int >= 1; got {revolutions!r}")
        if direction not in _DIRECTIONS:
            raise ValueError(
                f"direction must be one of {_DIRECTIONS}; got {direction!r}"
            )
        self.revolutions = revolutions
        self.direction = direction
        self._surface: Any = None
        self._last_t = 1.0  # re-fire detection (PushRandom precedent)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas
        if self._surface is None or not self._surface.matches(canvas):
            self._surface = make_rotation_surface(canvas)
        if t < self._last_t:
            self._surface.invalidate()  # new firing -> fresh snapshot
        self._last_t = t
        if not self._surface.has_snapshot:
            self._surface.clear()
            outgoing.draw(
                self._surface.target,
                cursor_pos=kwargs.get("outgoing_scroll_pos", 0),
            )
            self._surface.snapshot()
        angle = 360.0 * self.revolutions * (t**3)  # ease-in cubic (accelerate out)
        if self.direction == "ccw":
            angle = -angle % 360.0
        self._surface.blit(canvas, angle, canvas.width / 2)
        return canvas
