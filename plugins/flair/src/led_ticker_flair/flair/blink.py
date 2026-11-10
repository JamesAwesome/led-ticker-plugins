"""flair.blink — hard on/off text blink.

The text is shown for the "on" fraction of each period and blanked
(an empty visible slice) for the rest. Rates faster than 3 Hz are
refused unless ``allow_fast`` is set (WCAG 2.3.1 photosensitivity), judged
at the FASTEST engine cadence (20 ms per frame), not the nominal 50 ms.
``frames_to_rest`` lets the core settle seam extend a hold that would
end mid-off so the transition lands on visible text.
"""

from led_ticker.plugin import ENGINE_TICK_MS, AnimationFrame

# The animation counter advances once per scroll step on scrolling text
# (``scroll_step_ms`` in ticker mode, ``scroll_speed_ms`` on image overlays,
# floor 20 ms), NOT once per ENGINE_TICK_MS. To stay under 3 flashes/s
# whatever the cadence, the cycle must span >= 17 frames: 17 x 20 ms =
# 340 ms -> 2.94 Hz. (Without opt-in this makes 850 ms the minimum period.)
_FASTEST_TICK_MS = 20
_MIN_SAFE_FRAMES = 17
# Core's settle seam extends a hold by at most MAX_SETTLE_TICKS (1 s of
# engine ticks = 20 frames); an OFF phase longer than that can't be waited
# out, so the transition would start on blank text.
_MAX_OFF_FRAMES = 20


class Blink:
    restart_on_visit = True
    emits_rotation = False
    # Blanking never depends on the text content: keep live tokens live.
    locks_resolution = False

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
        if not isinstance(allow_fast, bool):
            raise ValueError(f"allow_fast must be a bool; got {allow_fast!r}")
        period = max(2, round(period_ms / ENGINE_TICK_MS))
        on = min(period - 1, max(1, round(period * duty)))
        if period < _MIN_SAFE_FRAMES and not allow_fast:
            raise ValueError(
                f"flair.blink: period_ms={period_ms} blinks faster than 3 Hz "
                "(WCAG 2.3.1 photosensitivity limit), which must hold even at "
                f"a {_FASTEST_TICK_MS} ms scroll cadence (minimum period_ms "
                f"{_MIN_SAFE_FRAMES * ENGINE_TICK_MS}); "
                "set allow_fast = true to opt in"
            )
        if period - on > _MAX_OFF_FRAMES:
            raise ValueError(
                f"flair.blink: the OFF phase is {period - on} frames, longer "
                f"than the {_MAX_OFF_FRAMES}-frame (1 s) settle limit, so a "
                "transition could start on blank text; use a shorter "
                "period_ms or a higher duty"
            )
        self.period_ms = period_ms
        self.duty = duty
        self.count = count
        self.allow_fast = allow_fast
        self.period = period
        self.on = on

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
