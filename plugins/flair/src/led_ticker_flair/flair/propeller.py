"""flair.propeller — spin-in-then-rest whole-text rotation.

The message text spins in-plane like a propeller on visit entry
(ease-out cubic: fast start, soft landing), settles exactly flat, and
stays readable for the rest of the hold. Emits AnimationFrame.rotation;
the core seam (led-ticker-core >= 4.3) renders it. Composes with the
defer-to-rest settle via frames_to_rest, and with validate rules 62
(duration vs hold) / 63 (hires fonts don't rotate) via emits_rotation.
"""

from led_ticker.plugin import ENGINE_TICK_MS, AnimationFrame

_DIRECTIONS = ("cw", "ccw")


class Propeller:
    restart_on_visit = True  # spin on every visit
    emits_rotation = True  # read by core validate rule 63

    def __init__(
        self,
        revolutions: int = 2,
        spin_seconds: float = 1.0,
        direction: str = "cw",
    ) -> None:
        bad_rev = not isinstance(revolutions, int) or isinstance(revolutions, bool)
        if bad_rev or revolutions < 1:
            raise ValueError(f"revolutions must be an int >= 1; got {revolutions!r}")
        if spin_seconds <= 0:
            raise ValueError(f"spin_seconds must be > 0; got {spin_seconds!r}")
        if direction not in _DIRECTIONS:
            raise ValueError(
                f"direction must be one of {_DIRECTIONS}; got {direction!r}"
            )
        self.revolutions = revolutions
        self.spin_seconds = spin_seconds
        self.direction = direction
        self.total_frames = max(1, int(spin_seconds * 1000) // ENGINE_TICK_MS)

    def frame_for(self, frame, full_text, canvas_width, text_width):
        t = min(1.0, frame / self.total_frames)
        eased = 1.0 - (1.0 - t) ** 3  # ease-out cubic
        angle = (360.0 * self.revolutions * eased) % 360.0
        if self.direction == "ccw":
            angle = -angle % 360.0
        return AnimationFrame(visible_text=full_text, rotation=angle)

    def frames_to_rest(self, frame, total_chars):
        """One-shot rest: frames until the spin completes (0 forever after).
        The core settle seam consults this at the hold->transition handoff."""
        return max(0, self.total_frames - frame)
