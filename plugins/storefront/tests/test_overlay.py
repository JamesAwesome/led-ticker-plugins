import asyncio
import types
from datetime import datetime

import pytest

from led_ticker_storefront.overlay import StorefrontOverlay


def _ctx(block):
    # Minimal StartupContext stand-in: only .config._raw is read by the plugin.
    cfg = types.SimpleNamespace(_raw={"storefront": block} if block else {})
    return types.SimpleNamespace(frame=None, session=None, config=cfg)


def test_disabled_when_block_absent(real_canvas):
    ov = StorefrontOverlay()
    ov.startup(_ctx(None))          # must not spawn or raise
    ov.paint(real_canvas)            # no state → paints nothing
    assert ov.state is None


def test_paint_draws_open_badge(real_canvas, monkeypatch):
    ov = StorefrontOverlay()
    # freeze the clock to Monday 10:00 (open per schedule) and stop the poller
    monkeypatch.setattr(ov, "_spawn_poller", lambda: None)
    ov._clock = lambda: datetime(2024, 1, 1, 10, 0)
    ov.startup(_ctx({"schedule": {"mon": "09:00-17:00"}, "open": {"text": "OPEN"}}))
    assert ov.state.is_open is True
    ov.paint(real_canvas)
    lit = any(
        real_canvas.get_pixel(x, y) != (0, 0, 0)
        for y in range(real_canvas.height) for x in range(real_canvas.width)
    )
    assert lit


def test_paint_advances_frame(real_canvas, monkeypatch):
    ov = StorefrontOverlay()
    monkeypatch.setattr(ov, "_spawn_poller", lambda: None)
    ov._clock = lambda: datetime(2024, 1, 1, 10, 0)
    ov.startup(_ctx({"schedule": {"mon": "09:00-17:00"}}))
    ov.paint(real_canvas)
    ov.paint(real_canvas)
    assert ov.state.frame == 2


async def test_poll_survives_refresh_exception(caplog, monkeypatch):
    ov = StorefrontOverlay()
    ov._clock = lambda: datetime(2024, 1, 1, 10, 0)
    ov.startup(_ctx({"schedule": {"mon": "09:00-17:00"}}))
    monkeypatch.setattr(ov, "_spawn_poller", lambda: None)

    refresh_calls = 0

    def _boom(self, now):
        nonlocal refresh_calls
        refresh_calls += 1
        raise RuntimeError("simulated refresh failure")

    monkeypatch.setattr(type(ov.state), "refresh", _boom)

    sleep_calls = 0

    async def _fake_sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 3:
            raise asyncio.CancelledError
        return None

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    with (
        caplog.at_level("ERROR", logger="led_ticker_storefront"),
        pytest.raises(asyncio.CancelledError),
    ):
        await ov._poll()

    # loop must have survived the first refresh exception and looped again
    assert refresh_calls >= 2
    assert any("poll" in rec.message.lower() for rec in caplog.records)
