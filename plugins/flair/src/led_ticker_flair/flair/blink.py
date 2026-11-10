"""flair.blink — hard on/off text blink.

The text is shown for the "on" fraction of each period and blanked
(an empty visible slice) for the rest. Rates faster than 3 Hz are
refused unless ``allow_fast`` is set (WCAG 2.3.1 photosensitivity).
``frames_to_rest`` lets the core settle seam extend a hold that would
end mid-off so the transition lands on visible text.
"""

from led_ticker.plugin import ENGINE_TICK_MS, AnimationFrame

# 3 flashes per second -> shortest allowed period is 1000/3 ms.
_MAX_FAST_PERIOD_MS = 1000 / 3


class Blink:
    restart_on_visit = True
    emits_rotation = False

    def __init__(
        self,
        period_ms: int = 1000,
        duty: float = 0.75,
        count: int = 0,
        allow_fast: bool = False,
    ) -> None:
        bad_period = isinstance(period_ms, bool) or not isinstance(
            period_ms, (int, float)
        )
        if bad_period or period_ms <= 0:
            raise ValueError(f"period_ms must be a number > 0; got {period_ms!r}")
        if isinstance(duty, bool) or not isinstance(duty, (int, float)):
            raise ValueError(f"duty must be a number in (0, 1); got {duty!r}")
        if not 0 < duty < 1:
            raise ValueError(f"duty must be in (0, 1); got {duty!r}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"count must be an int >= 0; got {count!r}")
        if period_ms < _MAX_FAST_PERIOD_MS and not allow_fast:
            raise ValueError(
                f"flair.blink: period_ms={period_ms} blinks faster than 3 Hz "
                "(WCAG 2.3.1 photosensitivity limit); "
                "set allow_fast = true to opt in"
            )
        self.period_ms = period_ms
        self.duty = duty
        self.count = count
        self.allow_fast = allow_fast
        self.period = max(2, round(period_ms / ENGINE_TICK_MS))
        self.on = min(self.period - 1, max(1, round(self.period * duty)))

    def _is_on(self, frame: int) -> bool:
        if self.count and frame >= self.count * self.period:
            return True
        return frame % self.period < self.on

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text if self._is_on(frame) else "")

    def frames_to_rest(self, frame, total_chars):
        """Frames until the next ON phase (0 when already on)."""
        if self._is_on(frame):
            return 0
        return self.period - (frame % self.period)
