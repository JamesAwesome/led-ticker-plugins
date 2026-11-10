"""TwinkleFOX-style twinkle math shared by the twinkle text animation, the
twinkle starfield background, and the snow effects.

Pure helpers: no canvas, no ``random`` module, no ``hash()`` (which is salted
per process). Every output is a deterministic function of its arguments.
"""

_M64 = (1 << 64) - 1
_M32 = (1 << 32) - 1


def _mix64(z: int) -> int:
    """splitmix64 finalizer over a 64-bit value."""
    z = (z + 0x9E3779B97F4A7C15) & _M64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    return z ^ (z >> 31)


def hash32(x: int, y: int, seed: int, salt: int) -> int:
    """Mix four integers into a 32-bit value in ``[0, 2**32)``."""
    h = 0
    for v in (x, y, seed, salt):
        h = _mix64(h ^ (v & _M64))
    return h & _M32


def is_twinkler(x: int, y: int, seed: int, density: float) -> bool:
    """Whether the pixel ``(x, y)`` is one of the twinkling stars at ``density``."""
    return hash32(x, y, seed, 1) / 2**32 < density


def level(x: int, y: int, frame: int, seed: int, speed: float) -> float:
    """Brightness in ``[0, 1]`` for pixel ``(x, y)`` at ``frame``.

    Each pixel has its own period (``cycle / factor`` frames, with ``factor``
    in ``[1, 2)``) and phase offset, so neighbours desynchronize. The ramp
    rises over the first third of the cycle and falls over the rest.
    """
    cycle = 24 / speed
    factor = 1 + (hash32(x, y, seed, 2) % 8) / 8
    offset = hash32(x, y, seed, 3) / 2**32
    p = (frame * factor / cycle + offset) % 1
    return 3 * p if p < 1 / 3 else 1.5 * (1 - p)
