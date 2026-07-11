import pytest
from led_ticker.plugin import unwrap_to_real

from led_ticker_flight.data import SAMPLE_AIRCRAFT
from led_ticker_flight.widget import OverheadWidget, resolve_layout


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def test_resolve_layout_auto():
    assert resolve_layout("auto", scale=1, phys_w=160) == "ticker"
    assert resolve_layout("auto", scale=4, phys_w=256) == "hero"
    assert resolve_layout("auto", scale=4, phys_w=512) == "dashboard"


def test_resolve_layout_explicit_and_fallback():
    assert resolve_layout("dashboard", scale=4, phys_w=256) == "dashboard"
    assert (
        resolve_layout("hero", scale=1, phys_w=160) == "ticker"
    )  # hi-res impossible at scale 1
    assert resolve_layout("ticker", scale=4, phys_w=256) == "ticker"


def test_demo_mode_populates_flights_without_network():
    w = OverheadWidget(demo=True)
    assert [a.flt for a in w._flights] == [a.flt for a in SAMPLE_AIRCRAFT]


def test_demo_respects_max_aircraft():
    w = OverheadWidget(demo=True, max_aircraft=2)
    assert len(w._flights) == 2


def test_missing_coords_raises_without_demo():
    with pytest.raises(ValueError, match="latitude"):
        OverheadWidget()


def test_draw_returns_canvas_and_zero(smallsign):
    w = OverheadWidget(demo=True)
    out, cursor = w.draw(smallsign)
    assert out is smallsign and cursor == 0
    assert lit(smallsign)


def test_draw_dispatches_hero_on_bigsign(bigsign):
    w = OverheadWidget(demo=True)
    w.advance_frame()
    out, cursor = w.draw(bigsign)
    assert cursor == 0 and lit(bigsign)


def test_frame_clock_moves_the_render(smallsign):
    from led_ticker.plugin import HeadlessCanvas

    w = OverheadWidget(demo=True)
    a = HeadlessCanvas(160, 16)
    b = HeadlessCanvas(160, 16)
    w.draw(a)
    for _ in range(40):  # 40 ticks = 2s at 50ms
        w.advance_frame()
    w.draw(b)
    assert lit(a) != lit(b)


@pytest.mark.asyncio
async def test_update_parses_via_monkeypatched_fetch(monkeypatch):
    payload = {
        "ac": [
            {
                "flight": "UA1 ",
                "t": "B738",
                "alt_baro": 30000,
                "baro_rate": 0,
                "gs": 400,
                "track": 90,
                "lat": 40.8,
                "lon": -73.9,
                "r": "N1",
            }
        ]
    }

    async def fake_fetch(session, lat, lon, radius, timeout=None):
        return payload

    monkeypatch.setattr("led_ticker_flight.widget.fetch_overhead", fake_fetch)
    w = OverheadWidget(latitude=40.7, longitude=-74.0)
    await w.update()
    assert [a.flt for a in w._flights] == ["UA1"]


@pytest.mark.asyncio
async def test_start_demo_accepts_and_never_uses_engine_session():
    # Core's factory always calls cls.start(session=<shared session>, ...).
    # A bare object() has no session API at all, so any accidental use of it
    # on the demo path would raise — constructing cleanly proves non-use.
    sentinel = object()
    w = await OverheadWidget.start(demo=True, session=sentinel)
    assert w.session is sentinel
    assert [a.flt for a in w._flights] == [a.flt for a in SAMPLE_AIRCRAFT]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload


class _FakeGet:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return _FakeResponse(self._payload)

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeGet(self._payload)


@pytest.mark.asyncio
async def test_update_uses_injected_shared_session(monkeypatch):
    payload = {
        "ac": [
            {
                "flight": "UA1 ",
                "t": "B738",
                "alt_baro": 30000,
                "baro_rate": 0,
                "gs": 400,
                "track": 90,
                "lat": 40.8,
                "lon": -73.9,
                "r": "N1",
            }
        ]
    }
    fake = _FakeSession(payload)

    def _no_new_sessions(*args, **kwargs):
        raise AssertionError(
            "update() must not construct its own ClientSession "
            "when the engine injected one"
        )

    monkeypatch.setattr(
        "led_ticker_flight.widget.aiohttp.ClientSession", _no_new_sessions
    )
    w = OverheadWidget(latitude=40.7, longitude=-74.0, session=fake)
    await w.update()
    assert [a.flt for a in w._flights] == ["UA1"]
    assert len(fake.calls) == 1
    _url, kwargs = fake.calls[0]
    assert "timeout" in kwargs  # the 8s budget rides per-request, not per-session
