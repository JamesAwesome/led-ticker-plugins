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


def test_reset_frame_does_not_rewind_rotation_clock():
    # Regression: OverheadWidget.draw() used to derive clock_ms from
    # FrameAwareBase._frame_count, which core's reset_frame() (called at
    # every section visit) zeroes unconditionally — snapping the hero/
    # dashboard rotation back to flight 0 mid-dwell whenever the section
    # cycled back into view. _clock_ticks must survive reset_frame().
    w = OverheadWidget(demo=True)
    for _ in range(100):
        w.advance_frame()
    assert w._clock_ticks == 100
    assert w._frame_count == 100

    w.reset_frame()

    assert w._frame_count == 0, "reset_frame should still zero the base counter"
    assert w._clock_ticks == 100, "reset_frame must not rewind the rotation clock"


def test_reset_frame_then_advance_continues_clock():
    w = OverheadWidget(demo=True)
    for _ in range(40):
        w.advance_frame()
    w.reset_frame()
    for _ in range(10):
        w.advance_frame()
    assert w._clock_ticks == 50
    assert w._frame_count == 10


def test_advance_frame_paused_does_not_advance_clock():
    w = OverheadWidget(demo=True)
    w.advance_frame()
    w.pause_frame()
    for _ in range(5):
        w.advance_frame()
    assert w._clock_ticks == 1, "paused advance_frame must not move the clock either"
    w.resume_frame()
    w.advance_frame()
    assert w._clock_ticks == 2


class TestFramesToTransitionReady:
    """Settle hook (core #305/#343): section transitions land on the fade's
    black frame at a dwell boundary instead of chopping the last flight
    mid-display. The ENGINE enforces the <= MAX_SETTLE_TICKS (1s) budget;
    the widget returns raw remaining ticks, unclamped."""

    HERO_DWELL_TICKS = 4200 // 50  # hero DWELL_MS // ENGINE_TICK_MS = 84

    def test_hero_ten_ticks_before_boundary(self, bigsign):
        w = OverheadWidget(demo=True)  # 4 demo flights
        w.draw(bigsign)  # stashes _last_layout = "hero"
        assert w._last_layout == "hero"
        w._clock_ticks = self.HERO_DWELL_TICKS - 10
        assert w.frames_to_transition_ready() == 10

    def test_hero_exactly_at_boundary(self, bigsign):
        w = OverheadWidget(demo=True)
        w.draw(bigsign)
        w._clock_ticks = 2 * self.HERO_DWELL_TICKS  # pos == 0 -> already black
        assert w.frames_to_transition_ready() == 0

    def test_single_flight_never_settles(self, bigsign):
        # One held flight never fades, so there is no black frame to settle
        # onto — the guard mirrors the fade's len(flights) >= 2 gate.
        w = OverheadWidget(demo=True, max_aircraft=1)
        w.draw(bigsign)
        assert w._last_layout == "hero"
        w._clock_ticks = self.HERO_DWELL_TICKS - 10
        assert w.frames_to_transition_ready() == 0

    def test_ticker_layout_never_settles(self, smallsign):
        w = OverheadWidget(demo=True)
        w.draw(smallsign)  # stashes _last_layout = "ticker"
        assert w._last_layout == "ticker"
        w._clock_ticks = 37
        assert w.frames_to_transition_ready() == 0

    def test_never_raises_fresh_widget_no_flights(self):
        # Fresh widget: never drawn (stash defaults to "ticker") and the
        # empty-flights state forced on top — must return 0, never raise
        # (base-method contract: a readiness check may never crash the
        # render loop).
        w = OverheadWidget(demo=True)
        w._flights = []
        assert w.frames_to_transition_ready() == 0


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


def test_bg_color_accepted_and_engine_contract_paints_it(smallsign):
    # Core injects a SECTION-level bg_color into every widget's config
    # (pre-coerced to graphics.Color). The widget declares the field only —
    # the ENGINE paints it via reset_canvas(canvas, widget.bg_color) before
    # each draw (weather/crypto precedent); draw() itself must not Fill (a
    # full-canvas Fill inside draw erases the other widget during push-
    # transition compositing). Simulate the engine tick here.
    from led_ticker.plugin import make_color

    w = OverheadWidget(demo=True, bg_color=make_color(0, 0, 40))
    assert w.bg_color is not None  # what the engine reads via getattr
    smallsign.Fill(0, 0, 40)  # reset_canvas's bg branch, pre-draw
    out, cursor = w.draw(smallsign)
    assert out is smallsign and cursor == 0
    # Corner pixel away from content (the row band is y 2..13) keeps the bg.
    assert lit(smallsign)[(0, 15)] == (0, 0, 40)


def test_core_field_validation_accepts_bg_color():
    # Regression tripwire for the original landmine: core's field validator
    # rejected 'bg_color' as unknown before the field existed, so a section
    # bg_color made the widget fail to build.
    from led_ticker.app.factories import _validate_cfg_fields

    _validate_cfg_fields(
        {"demo": True, "bg_color": [0, 0, 40]}, OverheadWidget, "flight.overhead"
    )


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
