"""flair.propeller — registration, seam guard, and Propeller math."""

import sys

import pytest
from led_ticker.plugin import ENGINE_TICK_MS

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.propeller import Propeller


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording animation registrations
    (mirror the pattern in test_packaging.py / other family tests —
    check those files and reuse their helper if one exists)."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}

    def animation(self, style: str):
        def deco(cls):
            self.animations[style] = cls
            return cls

        return deco


def test_register_registers_propeller() -> None:
    api = _RecordingAPI()
    flair_pkg.register(api)
    assert "propeller" in api.animations


def test_register_guard_message_when_seam_missing(monkeypatch) -> None:
    """Version-skew error quality (spec §9): a core without the seam must
    produce an actionable 'update core' message, not a bare ImportError.

    Goes through register() — not _import_seam() directly — so a refactor
    that drops the guard call from register() fails this test."""
    # Replace the led_ticker.plugin module in sys.modules with a stub that
    # lacks ENGINE_TICK_MS so the guarded import fails with the message.
    import types

    stub = types.ModuleType("led_ticker.plugin")
    # Do NOT set ENGINE_TICK_MS — simulates a pre-4.3 core.
    monkeypatch.setitem(sys.modules, "led_ticker.plugin", stub)

    with pytest.raises(ImportError, match=r"led-ticker-core >= 4\.3"):
        flair_pkg.register(_RecordingAPI())


class TestPropellerEnvelope:
    def test_frame_zero_is_flat(self) -> None:
        p = Propeller()
        assert p.frame_for(0, "HELLO", 160, 40).rotation == 0.0

    def test_pre_mod_angle_strictly_increasing(self) -> None:
        """Engineer round-1 finding 4: monotonicity holds PRE-modulo (the
        post-mod angle legitimately wraps down once per revolution)."""
        p = Propeller(revolutions=2, spin_seconds=1.0)
        prev = -1.0
        for frame in range(0, p.total_frames + 1):
            t = min(1.0, frame / p.total_frames)
            eased = 1.0 - (1.0 - t) ** 3
            pre_mod = 360.0 * p.revolutions * eased
            assert pre_mod > prev or frame == 0
            prev = pre_mod

    def test_lands_exactly_flat_and_stays(self) -> None:
        p = Propeller(revolutions=2, spin_seconds=1.0)
        for frame in (p.total_frames, p.total_frames + 1, p.total_frames + 500):
            assert p.frame_for(frame, "HELLO", 160, 40).rotation == 0.0

    def test_visible_text_always_full(self) -> None:
        p = Propeller()
        for frame in (0, 3, p.total_frames // 2, p.total_frames + 9):
            assert p.frame_for(frame, "FULL TEXT", 160, 60).visible_text == "FULL TEXT"

    def test_ccw_mirrors_angles(self) -> None:
        cw = Propeller(direction="cw")
        ccw = Propeller(direction="ccw")
        mid = cw.total_frames // 3
        a_cw = cw.frame_for(mid, "HI", 160, 12).rotation
        a_ccw = ccw.frame_for(mid, "HI", 160, 12).rotation
        assert a_cw != 0.0  # mid-spin really is rotated
        assert a_ccw == pytest.approx((-a_cw) % 360.0)

    def test_ccw_lands_exactly_flat(self) -> None:
        p = Propeller(direction="ccw")
        assert p.frame_for(p.total_frames, "HI", 160, 12).rotation == 0.0

    def test_total_frames_from_spin_seconds(self) -> None:
        p = Propeller(spin_seconds=1.5)
        assert p.total_frames == max(1, int(1.5 * 1000) // ENGINE_TICK_MS)  # 30


class TestPropellerRest:
    def test_frames_to_rest_counts_down(self) -> None:
        p = Propeller(spin_seconds=1.0)
        assert p.frames_to_rest(0, 10) == p.total_frames
        assert p.frames_to_rest(p.total_frames - 3, 10) == 3
        assert p.frames_to_rest(p.total_frames, 10) == 0
        assert p.frames_to_rest(p.total_frames + 100, 10) == 0


class TestPropellerContract:
    def test_class_markers(self) -> None:
        assert Propeller.restart_on_visit is True
        assert Propeller.emits_rotation is True

    def test_constructor_validation(self) -> None:
        with pytest.raises(ValueError):
            Propeller(revolutions=0)
        with pytest.raises(ValueError):
            Propeller(spin_seconds=0.0)
        with pytest.raises(ValueError):
            Propeller(direction="sideways")


class TestPropellerEaseDirection:
    def test_mid_spin_angle_is_ease_out_not_ease_in(self) -> None:
        """Pin one mid-spin angle THROUGH the live frame_for() against the
        ease-out formula. An ease-in mutation (t**3) matches ease-out at
        both endpoints, so endpoint tests can't catch it — this midpoint
        can: at t=0.5, ease-out gives 0.875 (fast start), ease-in 0.125."""
        p = Propeller(revolutions=2, spin_seconds=1.0)
        mid = p.total_frames // 2  # t = 0.5 exactly (total_frames = 20)
        t = mid / p.total_frames
        eased_out = 1.0 - (1.0 - t) ** 3
        expected = (360.0 * p.revolutions * eased_out) % 360.0
        assert p.frame_for(mid, "HI", 160, 12).rotation == pytest.approx(expected)
        # And distinguishable from ease-in at the same frame:
        eased_in = t**3
        wrong = (360.0 * p.revolutions * eased_in) % 360.0
        assert p.frame_for(mid, "HI", 160, 12).rotation != pytest.approx(wrong)
