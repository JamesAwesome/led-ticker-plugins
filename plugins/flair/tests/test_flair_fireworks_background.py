"""flair.fireworks BACKGROUND effect — continuous fireworks painted behind a
widget's content (``background = "flair.fireworks"``). Distinct from the
``flair.fireworks`` TRANSITION in ``fireworks.py``; shares its burst
geometry and spoke painter.

Stub canvas duplicated per-file (repo convention, see test_flair_spinout).
"""

import random
from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import BackgroundEffectBase, ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.fireworks_background import (
    CYCLE_FRAMES,
    FireworksBackground,
)


class _StubCanvas:
    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.calls: list[tuple[int, int, int, int, int]] = []

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)
        self.calls.append((x, y, r, g, b))

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.SetPixel(xx, yy, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)


def _lit(canvas: _StubCanvas) -> set[tuple[int, int]]:
    return {xy for xy, rgb in canvas._pixels.items() if rgb != (0, 0, 0)}


def _paint_frames(
    fx: FireworksBackground, frames: range, w: int = 160, h: int = 16
) -> list[_StubCanvas]:
    out = []
    for f in frames:
        c = _StubCanvas(w, h)
        fx.paint(c, f)
        out.append(c)
    return out


class _RecordingAPI:
    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}
        self.widgets: dict[str, type] = {}
        self.borders: dict[str, type] = {}
        self.backgrounds: dict[str, type] = {}

    def _deco(self, bucket: dict[str, type], name: str):
        def deco(cls):
            bucket[name] = cls
            return cls

        return deco

    def animation(self, style: str):
        return self._deco(self.animations, style)

    def transition(self, name: str):
        return self._deco(self.transitions, name)

    def widget(self, name: str):
        return self._deco(self.widgets, name)

    def border(self, name: str):
        return self._deco(self.borders, name)

    def background(self, name: str):
        return self._deco(self.backgrounds, name)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


class TestContract:
    def test_is_background_effect_base(self) -> None:
        assert issubclass(FireworksBackground, BackgroundEffectBase)

    def test_frame_variant(self) -> None:
        """An animated background MUST be frame_invariant=False or the image
        widgets' static fast path freezes it on the first frame."""
        assert FireworksBackground.frame_invariant is False

    def test_continuous_phase_across_visits(self) -> None:
        assert FireworksBackground.restart_on_visit is False

    def test_registered_as_flair_fireworks_background(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert api.backgrounds["fireworks"] is FireworksBackground
        assert "fireworks" not in api.borders  # no longer a border
        # The transition of the same name is untouched.
        assert "fireworks" in api.transitions


# ---------------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------------


class TestPaint:
    def test_paints_something_within_one_cycle(self) -> None:
        fx = FireworksBackground(seed=1)
        lit_any = any(_lit(c) for c in _paint_frames(fx, range(CYCLE_FRAMES)))
        assert lit_any

    def test_every_half_cycle_window_has_a_lit_frame(self) -> None:
        """Bursts are staggered so the panel never goes dark for long —
        a 'fireworks behind text' effect with multi-second gaps reads as
        broken, not as fireworks."""
        fx = FireworksBackground(seed=3)
        window = CYCLE_FRAMES // 2
        canvases = _paint_frames(fx, range(CYCLE_FRAMES * 4))
        for start in range(0, len(canvases) - window, window):
            assert any(_lit(c) for c in canvases[start : start + window]), (
                f"dark window starting at frame {start}"
            )

    def test_pure_function_of_frame(self) -> None:
        """Transitions pause the frame counter and re-render the widget
        repeatedly at the same frame; the composite must be stable."""
        fx = FireworksBackground(seed=7)
        a, b = _StubCanvas(), _StubCanvas()
        fx.paint(a, 37)
        fx.paint(b, 37)
        assert a.calls == b.calls and a.calls

    def test_same_seed_fresh_instances_identical(self) -> None:
        a = FireworksBackground(seed=11)
        b = FireworksBackground(seed=11)
        ca = _paint_frames(a, range(0, CYCLE_FRAMES, 5))
        cb = _paint_frames(b, range(0, CYCLE_FRAMES, 5))
        assert [c.calls for c in ca] == [c.calls for c in cb]

    def test_next_cycle_plans_different_bursts(self) -> None:
        """Frame f and frame f + CYCLE_FRAMES are the same phase of the
        cycle but a NEW epoch — the bursts must re-plan (new centers /
        colors), not replay the same show forever."""
        fx = FireworksBackground(seed=5)
        lit_a = set()
        lit_b = set()
        for f in range(CYCLE_FRAMES):
            a, b = _StubCanvas(), _StubCanvas()
            fx.paint(a, f)
            fx.paint(b, f + CYCLE_FRAMES)
            lit_a |= _lit(a)
            lit_b |= _lit(b)
        assert lit_a != lit_b

    def test_unseeded_instance_is_still_frame_pure(self) -> None:
        fx = FireworksBackground()
        a, b = _StubCanvas(), _StubCanvas()
        fx.paint(a, 20)
        fx.paint(b, 20)
        assert a.calls == b.calls

    def test_never_paints_outside_panel(self) -> None:
        fx = FireworksBackground(seed=2)
        for c in _paint_frames(fx, range(CYCLE_FRAMES * 2), 160, 16):
            for x, y, *_ in c.calls:
                assert 0 <= x < 160 and 0 <= y < 16

    def test_never_paints_outside_small_tall_panel(self) -> None:
        fx = FireworksBackground(seed=2)
        for c in _paint_frames(fx, range(CYCLE_FRAMES), 64, 64):
            for x, y, *_ in c.calls:
                assert 0 <= x < 64 and 0 <= y < 64

    def test_does_not_black_out_pixels(self) -> None:
        """A background effect paints light, never black — black fill
        would erase a host widget's bg_color / image underneath."""
        fx = FireworksBackground(seed=4)
        for c in _paint_frames(fx, range(CYCLE_FRAMES * 2)):
            assert (0, 0, 0) not in c._pixels.values()

    def test_launch_streak_white_hot_head_appears(self) -> None:
        """Early in a burst's window a rocket streak rises from the bottom
        edge — at least one frame per cycle shows a white-hot pixel."""
        fx = FireworksBackground(seed=9)
        seen_white = any(
            (255, 255, 255) in c._pixels.values()
            for c in _paint_frames(fx, range(CYCLE_FRAMES), 256, 64)
        )
        assert seen_white

    def test_speed_scales_cycle_length(self) -> None:
        """speed=2 → a full show in half the frames: the lit-set over
        CYCLE_FRAMES//2 frames at speed 2 matches the lit-set over
        CYCLE_FRAMES frames at speed 1 (same seed, same epochs)."""
        slow = FireworksBackground(seed=6, speed=1.0)
        fast = FireworksBackground(seed=6, speed=2.0)
        lit_slow = set()
        for c in _paint_frames(slow, range(0, CYCLE_FRAMES, 2)):
            lit_slow |= _lit(c)
        lit_fast = set()
        for c in _paint_frames(fast, range(CYCLE_FRAMES // 2)):
            lit_fast |= _lit(c)
        assert lit_slow == lit_fast

    def test_colors_restrict_palette(self) -> None:
        fx = FireworksBackground(seed=8, colors=[[0, 0, 255]])
        seen = set()
        for c in _paint_frames(fx, range(CYCLE_FRAMES * 2)):
            seen |= set(c._pixels.values())
        # Every lit pixel is either a (possibly faded) white-hot head —
        # a neutral grey — or a dimmed pure blue.
        for r, g, b in seen:
            assert (r == g == b) or (r == 0 and g == 0 and b > 0), (r, g, b)


class TestScaledCanvas:
    def test_paints_physical_pixels_on_real_canvas(self) -> None:
        real = _StubCanvas(256, 64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        fx = FireworksBackground(seed=1)
        # ScaledCanvas is attrs-slotted; patch at the class so any write
        # through the wrapper (block-expanded) fails loudly.
        with mock.patch.object(
            ScaledCanvas,
            "SetPixel",
            side_effect=AssertionError("painted through the wrapper"),
        ):
            for f in range(CYCLE_FRAMES):
                fx.paint(wrapped, f)
        assert real.calls, "nothing painted on the real canvas"
        for x, y, *_ in real.calls:
            assert 0 <= x < 256 and 0 <= y < 64

    def test_burst_count_follows_real_dims(self) -> None:
        """Burst count is derived from the REAL panel (256x64 → 4), not the
        logical wrapper (64x16 → 2)."""
        real = _StubCanvas(256, 64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        fx = FireworksBackground(seed=1)
        fx.paint(wrapped, 0)
        assert fx._slot_count(wrapped) == 4


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize("bad", [1, 9, 0, -1, True, 3.0, "4"])
    def test_bursts_out_of_range_or_wrong_type(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="bursts"):
            FireworksBackground(bursts=bad)

    @pytest.mark.parametrize("ok", [2, 8, None])
    def test_bursts_accepted(self, ok: Any) -> None:
        FireworksBackground(bursts=ok)

    @pytest.mark.parametrize(
        "bad", [[], "red", [[1, 2]], [[0, 0, 256]], [[0, 0, True]]]
    )
    def test_colors_invalid(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="colors"):
            FireworksBackground(colors=bad)

    @pytest.mark.parametrize("bad", [0, -1.0, True, "fast", float("nan")])
    def test_speed_invalid(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="speed"):
            FireworksBackground(speed=bad)

    def test_speed_accepts_int_and_float(self) -> None:
        FireworksBackground(speed=2)
        FireworksBackground(speed=0.5)

    @pytest.mark.parametrize("bad", [True, 1.5, "7"])
    def test_seed_wrong_type(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="seed"):
            FireworksBackground(seed=bad)

    def test_explicit_bursts_overrides_auto(self) -> None:
        fx = FireworksBackground(bursts=7)
        assert fx._slot_count(_StubCanvas(160, 16)) == 7


# ---------------------------------------------------------------------------
# Core config-load integration (registry → _coerce_background)
# ---------------------------------------------------------------------------


class TestCoreIntegration:
    """Core resolves the registered name through its `background` field."""

    @pytest.fixture
    def loaded(self):
        from led_ticker import _plugin_loader as L

        L.reset_plugins()
        try:
            L.load_plugins(None, entry_points_enabled=True)
            yield
        finally:
            L.reset_plugins()

    def test_shorthand_string(self, loaded) -> None:
        from led_ticker.app.coercion import _coerce_background

        fx = _coerce_background("flair.fireworks")
        assert isinstance(fx, FireworksBackground)

    def test_inline_table_kwargs(self, loaded) -> None:
        from led_ticker.app.coercion import _coerce_background

        fx = _coerce_background(
            {"style": "flair.fireworks", "bursts": 3, "speed": 1.5, "seed": 1}
        )
        assert isinstance(fx, FireworksBackground)
        assert fx._slot_count(_StubCanvas(160, 16)) == 3

    def test_unknown_kwarg_is_config_error(self, loaded) -> None:
        from led_ticker.app.coercion import _coerce_background

        with pytest.raises(ValueError, match="unknown keys"):
            _coerce_background({"style": "flair.fireworks", "thickness": 2})

    def test_message_widget_paints_fireworks_behind_text(self, loaded) -> None:
        """End-to-end through core: a message widget with this background
        paints fireworks before its border and text."""
        from led_ticker.app.coercion import _coerce_background
        from led_ticker.widgets import get_widget_class

        bg = _coerce_background({"style": "flair.fireworks", "seed": 1})
        widget = get_widget_class("message")(text="HI", background=bg)
        lit: set[tuple[int, int]] = set()
        for _ in range(CYCLE_FRAMES):
            widget.advance_frame()
            c = _StubCanvas(160, 16)
            widget.draw(c, 0)
            lit |= _lit(c)
        # Text alone lights a few dozen pixels near x=0; fireworks spread
        # lit pixels across the panel's right half too.
        assert any(x > 80 for x, _ in lit)


# ---------------------------------------------------------------------------
# Determinism helper sanity
# ---------------------------------------------------------------------------


def test_rng_seed_mixing_differs_per_slot_and_epoch() -> None:
    """Slot/epoch keyed seeds must not collide (slot 1 epoch 0 ≠ slot 0
    epoch 1) or two bursts would share a plan."""
    fx = FireworksBackground(seed=1)
    seeds = {fx._slot_seed(s, e) for s in range(8) for e in range(50)}
    assert len(seeds) == 8 * 50
    # And the stream is usable.
    random.Random(fx._slot_seed(0, 0)).random()
