"""Shared helpers for flair.interlock / flair.blinds: the alternating /
random delegate bases (``_variants.py``) and the geometry-keyed snapshot
cache (``_snapshot.py``)."""

from typing import Any

from led_ticker.plugin import ScaledCanvas

from led_ticker_flair.flair._snapshot import Geometry, SnapshotCache, geometry_of
from led_ticker_flair.flair._variants import Cycling, RandomNoRepeat


class _StubCanvas:
    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        pass

    def Clear(self) -> None:  # noqa: N802
        pass


class _Recorder:
    min_frames = 24

    def __init__(self, idx: int, log: list[int]) -> None:
        self.idx = idx
        self.log = log

    def frame_at(
        self, t: float, canvas: Any, outgoing: Any, incoming: Any, **kw: Any
    ) -> Any:
        self.log.append(self.idx)
        return canvas


def _fakes(n: int) -> tuple[list[_Recorder], list[int]]:
    log: list[int] = []
    return [_Recorder(i, log) for i in range(n)], log


class _Widget:
    def draw(self, canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        canvas.SetPixel(0, 0, 255, 0, 0)
        return canvas, cursor_pos


def test_cycling_advances_on_t0_and_on_t_decrease():
    fakes, log = _fakes(3)
    c = Cycling(fakes)
    for t in (0.0, 0.5, 0.0, 0.3, 0.1):
        c.frame_at(t, None, None, None)
    assert log == [0, 0, 1, 1, 2]


def test_cycling_equal_nonzero_t_is_not_refire():
    fakes, log = _fakes(3)
    c = Cycling(fakes)
    c.frame_at(0.4, None, None, None)
    c.frame_at(0.4, None, None, None)
    assert log == [0, 0]


def test_random_no_repeat_seeded():
    fakes, _log = _fakes(4)
    r = RandomNoRepeat(fakes)
    r._rng.seed(1)
    seen = []
    for _ in range(30):
        r.frame_at(0.0, None, None, None)
        seen.append(r._index)
        r.frame_at(0.96, None, None, None)
    assert all(a != b for a, b in zip(seen, seen[1:], strict=False))
    assert len(set(seen)) >= 3


def test_min_frames_forwarded():
    fakes, _log = _fakes(1)
    assert Cycling(fakes).min_frames == 24


def test_geometry_unscaled_and_scaled():
    assert geometry_of(_StubCanvas(160, 16)) == Geometry(160, 16, 1, 0, 16)
    sc = ScaledCanvas(_StubCanvas(128, 64), scale=2, content_height=16)
    assert geometry_of(sc) == Geometry(128, 64, 2, 16, 32)


def test_snapshot_cache_reuses_raster_until_geometry_changes():
    cache = SnapshotCache()
    c = _StubCanvas(10, 4)
    a = cache.take(c, _Widget(), 0, 0)
    b = cache.take(c, _Widget(), 0, 0)
    assert a is b
    assert a.get(0, 0) == (255, 0, 0)
    other = cache.take(_StubCanvas(12, 4), _Widget(), 0, 0)
    assert other is not a
    assert other.width == 12


def test_cycling_forwards_scale_switch_at():
    from led_ticker_flair.flair.blinds import BlindsAlternating, BlindsRandom
    from led_ticker_flair.flair.interlock import InterlockAlternating, InterlockRandom

    # The runner reads scale_switch_at on the WRAPPER (getattr default 0.5).
    assert BlindsAlternating().scale_switch_at == 1.0
    assert BlindsRandom().scale_switch_at == 1.0
    assert not hasattr(InterlockAlternating(), "scale_switch_at")
    assert not hasattr(InterlockRandom(), "scale_switch_at")
