"""flair.twinkle — TwinkleFOX-style per-pixel twinkle on animated text.

Each text pixel is (with probability ``density``) a "twinkler" whose
brightness cycles between ``min_brightness`` and full; the rest stay at full
brightness. The effect is delivered through ``AnimationFrame.pixel_gain``,
which core applies to the text only (borders/backgrounds are untouched).

Pure function of ``(frame, x, y, seed)``. Per-pixel hashing is done once per
row and cached (``_rows``); the gain closure itself is just list indexing and
the triangle function, so a bigsign draw stays cheap.
"""

import math
import random

from led_ticker.plugin import AnimationFrame

from led_ticker_flair.flair._twinkle import row_params

_ROW_CHUNK = 64


def validate_common(density: object, speed: object, seed: object) -> None:
    if (
        isinstance(density, bool)
        or not isinstance(density, int | float)
        or math.isnan(density)
        or not 0 < density <= 1
    ):
        raise ValueError(f"density must be a number in (0, 1]; got {density!r}")
    if (
        isinstance(speed, bool)
        or not isinstance(speed, int | float)
        or math.isnan(speed)
        or not 0 < speed <= 2.0
    ):
        raise ValueError(f"speed must be a number in (0, 2.0]; got {speed!r}")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ValueError(f"seed must be an int or None; got {seed!r}")


class Twinkle:
    restart_on_visit = False
    emits_rotation = False
    # Gain is a function of position, not the text: keep live tokens live.
    locks_resolution = False

    def __init__(
        self,
        density: float = 0.6,
        speed: float = 1.0,
        min_brightness: float = 0.15,
        seed: int | None = None,
    ) -> None:
        validate_common(density, speed, seed)
        if (
            isinstance(min_brightness, bool)
            or not isinstance(min_brightness, int | float)
            or math.isnan(min_brightness)
            or not 0 <= min_brightness < 1
        ):
            raise ValueError(
                f"min_brightness must be a number in [0, 1); got {min_brightness!r}"
            )
        self.density = float(density)
        self.speed = float(speed)
        self.min_brightness = float(min_brightness)
        self.seed = seed
        self._seed = seed if seed is not None else random.SystemRandom().getrandbits(62)
        self._cycle = 24 / self.speed
        self._rows: dict[int, tuple[list[float], list[float]]] = {}

    def _row(self, y: int, x: int) -> tuple[list[float], list[float]]:
        row = self._rows.get(y)
        have = len(row[0]) if row else 0
        if row is None:
            row = ([], [])
            self._rows[y] = row
        if x >= have:
            to = (x // _ROW_CHUNK + 1) * _ROW_CHUNK
            f, o = row_params(y, have, to, self._seed, self.density)
            row[0].extend(f)
            row[1].extend(o)
        return row

    def frame_for(self, frame, full_text, canvas_width, text_width):
        cycle = self._cycle
        lo = self.min_brightness
        span = 1.0 - lo
        rows = self._rows

        def gain(x: int, y: int) -> float:
            if x < 0 or y < 0:
                return 1.0
            row = rows.get(y)
            if row is None or x >= len(row[0]):
                row = self._row(y, x)
            factor = row[0][x]
            if factor == 0.0:
                return 1.0
            p = (frame * factor / cycle + row[1][x]) % 1
            lvl = 3 * p if p < 1 / 3 else 1.5 * (1 - p)
            return lo + span * lvl

        return AnimationFrame(visible_text=full_text, pixel_gain=gain)

    def frames_to_rest(self, frame, total_chars):
        return 0
