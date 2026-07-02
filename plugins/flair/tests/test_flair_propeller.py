"""flair.propeller — registration, seam guard, and Propeller math."""

import sys

import pytest

from led_ticker_flair import flair as flair_pkg


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
