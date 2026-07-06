"""flair.fisheye — registration, guard lockstep, and Fisheye contract tests."""

import inspect
import sys
import types

import pytest

from led_ticker_flair import flair as flair_pkg

# ---------------------------------------------------------------------------
# _RecordingAPI — captures animation + transition registrations
# ---------------------------------------------------------------------------


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording animation + transition registrations."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}

    def animation(self, style: str):
        def deco(cls):
            self.animations[style] = cls
            return cls

        return deco

    def transition(self, name: str):
        def deco(cls):
            self.transitions[name] = cls
            return cls

        return deco


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_fisheye_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "fisheye" in api.animations

    def test_propeller_still_registered(self) -> None:
        """fisheye registration must not displace the existing propeller."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "propeller" in api.animations

    def test_spinout_still_registered(self) -> None:
        """fisheye registration must not displace the existing spinout."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "spinout" in api.transitions

    def test_fisheye_class_is_Fisheye(self) -> None:
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        api = _RecordingAPI()
        flair_pkg.register(api)
        assert api.animations["fisheye"] is Fisheye


# ---------------------------------------------------------------------------
# Guard-probe lockstep: probe must be LensSpec (the 4.7 symbol),
# not make_rotation_surface (a 4.6 symbol)
# ---------------------------------------------------------------------------


class TestGuardProbe:
    def test_register_guard_message_when_lens_seam_missing(self, monkeypatch) -> None:
        """Version-skew error quality (spec §9): a core without LensSpec must
        produce an actionable 'update core' message, not a bare ImportError.

        Goes through register() — not _import_seam() directly — so a refactor
        that drops the guard call from register() fails this test.

        The stub PROVIDES ``make_rotation_surface`` (now a pre-4.7 symbol) and
        withholds ONLY ``LensSpec`` — so this test FAILS if the guard's probe
        ever regresses to a pre-4.7 symbol like ``make_rotation_surface``."""
        stub = types.ModuleType("led_ticker.plugin")
        # PROVIDE the pre-4.7 symbols (a real 4.6 core has these) and
        # withhold ONLY LensSpec.
        stub.ENGINE_TICK_MS = 50
        from led_ticker.plugin import (  # noqa: PLC0415
            Animation,
            AnimationFrame,
            make_rotation_surface,
        )

        stub.Animation = Animation
        stub.AnimationFrame = AnimationFrame
        stub.make_rotation_surface = make_rotation_surface
        monkeypatch.setitem(sys.modules, "led_ticker.plugin", stub)

        with pytest.raises(ImportError, match=r">= 4\.7"):
            flair_pkg.register(_RecordingAPI())


# ---------------------------------------------------------------------------
# Constructor validation — ValueError messages carry "flair.fisheye:" prefix
# ---------------------------------------------------------------------------


class TestFisheyeCtorValidation:
    def _cls(self):
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        return Fisheye

    def test_bad_magnify_message_has_prefix(self) -> None:
        """ValueError from LensSpec (bad magnify) is re-raised with prefix."""
        with pytest.raises(ValueError, match="flair.fisheye"):
            # magnify < edge_squeeze is invalid
            self._cls()(magnify=0.3, edge_squeeze=0.6)

    def test_bad_edge_squeeze_message_has_prefix(self) -> None:
        """ValueError from LensSpec (bad edge_squeeze) is re-raised with prefix."""
        with pytest.raises(ValueError, match="flair.fisheye"):
            # edge_squeeze > magnify is invalid
            self._cls()(magnify=1.0, edge_squeeze=2.0)

    def test_bad_profile_message_has_prefix(self) -> None:
        """ValueError from LensSpec (bad profile) is re-raised with prefix."""
        with pytest.raises(ValueError, match="flair.fisheye"):
            self._cls()(profile="linear")

    def test_valid_defaults_construct(self) -> None:
        f = self._cls()()
        assert f is not None

    def test_valid_custom_params_construct(self) -> None:
        f = self._cls()(magnify=2.0, edge_squeeze=0.4, profile="cosine")
        assert f is not None


# ---------------------------------------------------------------------------
# No-**kwargs tripwire (rule-53)
# ---------------------------------------------------------------------------


class TestRule53Contract:
    def test_unknown_kwarg_raises_type_error(self) -> None:
        """The explicit-param __init__ signature is rule-53 LOAD-BEARING:
        _build_plugin_style validates config kwargs against
        inspect.signature(cls), so a **kwargs catch-all would silently
        swallow config typos like ``magnifyy=2``. This tripwire fails if
        anyone adds **kwargs to __init__."""
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        with pytest.raises(TypeError):
            Fisheye(magnifyy=2)  # typo'd kwarg must NOT be swallowed

    def test_no_var_keyword_in_signature(self) -> None:
        """inspect.signature must have no VAR_KEYWORD parameter."""
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        params = inspect.signature(Fisheye).parameters.values()
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


# ---------------------------------------------------------------------------
# frame_for constancy — same LensSpec object every call (no per-tick alloc)
# ---------------------------------------------------------------------------


class TestFrameForConstancy:
    def _make(self):
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        return Fisheye()

    def test_frame_for_returns_full_text(self) -> None:
        f = self._make()
        frame = f.frame_for(0, "HELLO WORLD", 160, 60)
        assert frame.visible_text == "HELLO WORLD"

    def test_frame_for_visible_text_always_full(self) -> None:
        f = self._make()
        text = "FULL TEXT"
        for tick in (0, 1, 5, 100, 999):
            assert f.frame_for(tick, text, 160, 60).visible_text == text

    def test_lens_is_same_object_across_calls(self) -> None:
        """LensSpec must be the same object every tick — no per-tick alloc."""
        f = self._make()
        frames = [f.frame_for(tick, "HI", 160, 12) for tick in range(10)]
        spec_ids = {id(fr.lens) for fr in frames}
        assert len(spec_ids) == 1, "LensSpec identity must be stable"

    def test_lens_is_not_none(self) -> None:
        f = self._make()
        frame = f.frame_for(0, "HI", 160, 12)
        assert frame.lens is not None

    def test_lens_identity_is_init_spec(self) -> None:
        """The lens returned by frame_for is the _spec built in __init__."""
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        f = Fisheye(magnify=1.5, edge_squeeze=0.5)
        spec = f._spec
        for tick in range(5):
            assert f.frame_for(tick, "X", 160, 10).lens is spec


# ---------------------------------------------------------------------------
# frames_to_rest — always 0 regardless of frame / total_chars
# ---------------------------------------------------------------------------


class TestFramesToRest:
    def _make(self):
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        return Fisheye()

    def test_frames_to_rest_is_zero_at_frame_0(self) -> None:
        assert self._make().frames_to_rest(0, 10) == 0

    def test_frames_to_rest_is_zero_at_large_frame(self) -> None:
        assert self._make().frames_to_rest(9999, 50) == 0

    def test_frames_to_rest_is_zero_for_various_total_chars(self) -> None:
        f = self._make()
        for frame, chars in ((0, 1), (1, 10), (100, 100), (500, 5)):
            assert f.frames_to_rest(frame, chars) == 0


# ---------------------------------------------------------------------------
# Class-marker pins (rule-63 / rule-64)
# ---------------------------------------------------------------------------


class TestClassMarkers:
    def test_restart_on_visit_is_false(self) -> None:
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        assert Fisheye.restart_on_visit is False

    def test_emits_lens_is_true(self) -> None:
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        assert Fisheye.emits_lens is True

    def test_emits_rotation_is_false(self) -> None:
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        assert Fisheye.emits_rotation is False

    def test_restart_on_visit_is_class_attribute(self) -> None:
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        assert "restart_on_visit" in Fisheye.__dict__

    def test_emits_lens_is_class_attribute(self) -> None:
        from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415

        assert "emits_lens" in Fisheye.__dict__
