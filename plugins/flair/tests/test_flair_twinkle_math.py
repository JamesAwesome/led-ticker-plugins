"""TwinkleFOX-style twinkle math (``flair/_twinkle.py``).

Pure integer/float helpers: no canvas, no led_ticker imports. Consumed by the
twinkle text animation, the twinkle starfield background, and snow effects.
"""

import statistics

from led_ticker_flair.flair._twinkle import hash32, is_twinkler, level


def test_hash32_range_and_determinism() -> None:
    seen = set()
    for x in range(32):
        for y in range(16):
            v = hash32(x, y, 7, 1)
            assert 0 <= v < 2**32
            assert v == hash32(x, y, 7, 1)
            seen.add(v)
    # A decent mix produces (almost) all distinct values over 512 inputs.
    assert len(seen) > 500


def test_hash32_accepts_negative_inputs() -> None:
    v = hash32(-5, -1, -42, 3)
    assert 0 <= v < 2**32
    assert v == hash32(-5, -1, -42, 3)


def test_level_bounds() -> None:
    for x in range(32):
        for y in range(16):
            for frame in range(200):
                v = level(x, y, frame, seed=3, speed=1.0)
                assert 0.0 <= v <= 1.0


def test_level_bounds_at_max_speed() -> None:
    for x in range(32):
        for y in range(16):
            for frame in range(200):
                v = level(x, y, frame, seed=3, speed=2.0)
                assert 0.0 <= v <= 1.0


def test_pure() -> None:
    a = level(10, 5, 123, seed=9, speed=1.5)
    b = level(10, 5, 123, seed=9, speed=1.5)
    assert a == b


def test_desynchronized() -> None:
    # At a fixed frame, neighbouring pixels must not all twinkle in lockstep.
    frame = 40
    levels = [
        level(x, y, frame, seed=1, speed=1.0) for x in range(10) for y in range(10)
    ]
    assert len(levels) == 100
    assert statistics.pstdev(levels) > 0.2


def test_density_fraction() -> None:
    density = 0.6
    total = 256 * 64
    count = sum(
        1
        for x in range(256)
        for y in range(64)
        if is_twinkler(x, y, seed=11, density=density)
    )
    fraction = count / total
    assert abs(fraction - density) <= 0.02


def test_min_cycle_at_max_speed() -> None:
    # period = (24 / speed) / factor frames; at speed 2.0 the cycle is 12
    # frames and factor < 2, so every period must be strictly above 6 frames.
    speed = 2.0
    cycle = 24 / speed
    for x in range(64):
        for y in range(16):
            h = hash32(x, y, 5, 2)
            factor = 1 + (h % 8) / 8
            period = cycle / factor
            assert period > 6.0


def test_seed_changes_pattern() -> None:
    frame = 17
    a = [level(x, y, frame, seed=1, speed=1.0) for x in range(16) for y in range(8)]
    b = [level(x, y, frame, seed=2, speed=1.0) for x in range(16) for y in range(8)]
    assert a != b


def test_row_params_agrees_with_is_twinkler_and_level() -> None:
    from led_ticker_flair.flair._twinkle import row_params

    seed, density, speed = 11, 0.4, 1.0
    cycle = 24 / speed
    for y in (0, 5, 63):
        factors, offsets = row_params(y, 3, 83, seed, density)
        assert len(factors) == len(offsets) == 80
        for i, x in enumerate(range(3, 83)):
            if not is_twinkler(x, y, seed, density):
                assert factors[i] == 0.0
                continue
            assert factors[i] >= 1.0
            for frame in (0, 7, 31):
                p = (frame * factors[i] / cycle + offsets[i]) % 1
                lvl = 3 * p if p < 1 / 3 else 1.5 * (1 - p)
                assert lvl == level(x, y, frame, seed, speed)
