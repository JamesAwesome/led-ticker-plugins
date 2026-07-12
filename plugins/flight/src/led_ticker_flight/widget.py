"""OverheadWidget — planes-overhead ADS-B tracker (flight.overhead)."""

import logging

import aiohttp
import attrs
from led_ticker.plugin import (
    ENGINE_TICK_MS,
    Color,
    FrameAwareBase,
    run_monitor_loop,
    safe_scale,
    spawn_tracked,
    unwrap_to_real,
)

from led_ticker_flight.adsb import fetch_overhead, parse_point_response, radius_nm
from led_ticker_flight.dashboard_layout import render_dashboard
from led_ticker_flight.data import SAMPLE_AIRCRAFT, Aircraft
from led_ticker_flight.hero_layout import render_hero
from led_ticker_flight.ticker_layout import render_ticker

_LAYOUTS = ("auto", "ticker", "hero", "dashboard")


def resolve_layout(name: str, scale: int, phys_w: int) -> str:
    if name != "auto":
        if name in ("hero", "dashboard") and scale == 1:
            return "ticker"  # hi-res layouts are impossible on a scale-1 sign
        return name
    if scale == 1:
        return "ticker"
    return "hero" if phys_w < 400 else "dashboard"


@attrs.define
class OverheadWidget(FrameAwareBase):
    latitude: float | None = None
    longitude: float | None = None
    # converter=int: validate_config accepts integral floats (a plausible
    # TOML spelling — radius_km = 30.0, max_aircraft = 4.0), so construction
    # must coerce them or SAMPLE_AIRCRAFT[:4.0] / downstream int math crash.
    # Non-integral floats never reach here (validate rejects them); bools
    # are likewise validate-rejected before construction.
    radius_km: int = attrs.field(default=30, converter=int)
    layout: str = "auto"
    max_aircraft: int = attrs.field(default=4, converter=int)
    interval: float = 10.0
    demo: bool = False
    # The engine's SHARED aiohttp session — core's _build_widget calls
    # `cls.start(session=session, **widget_cfg)`, and start() forwards it
    # here. None (direct construction, tests) => update() opens a temporary
    # session per poll instead.
    session: aiohttp.ClientSession | None = None
    # A section-level `bg_color` is injected into every widget's config by
    # core (pre-coerced to a `graphics.Color`); without this field the build
    # fails with "unknown field: 'bg_color'". Declared-only, like weather /
    # crypto / core's TickerMessage: the ENGINE paints it (reset_canvas
    # before each draw + the transition bg kwargs) — draw() must NOT Fill it
    # itself, or push-transition compositing (outgoing + incoming drawn on
    # the SAME canvas) would have this widget's Fill erase the other widget.
    # None => engine Clear() = pure black, the design default.
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    _flights: list[Aircraft] = attrs.field(factory=list, init=False)
    # Rotation clock, separate from FrameAwareBase's `_frame_count` — core's
    # `reset_frame()` (ticker._show_one, at every section visit) zeroes
    # `_frame_count` unconditionally, which would otherwise snap the hero/
    # dashboard rotation back to flight 0 mid-dwell every time this section
    # cycles back into view. `_clock_ticks` only ever increments (via the
    # advance_frame override below) and is never reset, so `clock_ms` keeps
    # counting across visits and the rotation index continues from wherever
    # it left off.
    _clock_ticks: int = attrs.field(init=False, default=0)

    def __attrs_post_init__(self) -> None:
        if self.demo:
            self._flights = list(SAMPLE_AIRCRAFT)[: self.max_aircraft]
        elif self.latitude is None or self.longitude is None:
            raise ValueError(
                "flight.overhead requires latitude and longitude (or demo = true)"
            )

    @classmethod
    async def start(cls, *args, **kwargs):
        widget = cls(*args, **kwargs)
        if not widget.demo:
            try:
                await widget.update()
            except Exception:
                logging.exception(
                    "flight.overhead initial fetch failed; will retry in background"
                )
            spawn_tracked(run_monitor_loop(widget, widget.interval))
        return widget

    async def update(self) -> None:
        # __attrs_post_init__ raises unless demo=True or both coords are set;
        # start()/run_monitor_loop only call update() on a non-demo widget, so
        # both are always floats here — narrow for the type checker.
        assert self.latitude is not None
        assert self.longitude is not None
        radius = radius_nm(self.radius_km)
        timeout = aiohttp.ClientTimeout(total=8)
        if self.session is not None:
            # Engine-shared session: never close it, apply timeout per-request.
            payload = await fetch_overhead(
                self.session, self.latitude, self.longitude, radius, timeout=timeout
            )
        else:
            async with aiohttp.ClientSession() as session:
                payload = await fetch_overhead(
                    session, self.latitude, self.longitude, radius, timeout=timeout
                )
        self._flights = parse_point_response(
            payload, self.latitude, self.longitude, self.max_aircraft
        )
        logging.info(
            "flight.overhead: %d aircraft within %dkm",
            len(self._flights),
            self.radius_km,
        )

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        # Mirror the base's own pause gate: advance_frame() no-ops while
        # paused (transition compositing), so _clock_ticks must too, or the
        # rotation clock would drift ahead of the visible frame during a
        # dissolve/push.
        if not self._frame_paused:
            self._clock_ticks += 1

    def draw(self, canvas, cursor_pos=0, *, y_offset: int = 0, font_color=None):
        clock_ms = self._clock_ticks * ENGINE_TICK_MS
        scale = safe_scale(canvas)
        real = unwrap_to_real(canvas)
        layout = resolve_layout(self.layout, scale, real.width)
        if layout == "ticker":
            render_ticker(canvas, self._flights, clock_ms, y_offset=y_offset)
        elif layout == "hero":
            render_hero(canvas, self._flights, clock_ms, y_offset=y_offset)
        else:
            render_dashboard(canvas, self._flights, clock_ms, y_offset=y_offset)
        return canvas, 0

    @classmethod
    def validate_config(cls, cfg: dict) -> list[str]:
        errs: list[str] = []

        def _num(name, lo, hi, required=False):
            v = cfg.get(name)
            if v is None:
                if required and not cfg.get("demo"):
                    errs.append(f"{name} is required (or set demo = true)")
                return
            if isinstance(v, bool) or not isinstance(v, int | float):
                errs.append(f"{name} must be a number, got {v!r}")
            elif not lo <= v <= hi:
                errs.append(f"{name} must be between {lo} and {hi}, got {v}")

        def _int(name, lo, hi, required=False):
            v = cfg.get(name)
            if v is None:
                if required and not cfg.get("demo"):
                    errs.append(f"{name} is required (or set demo = true)")
                return
            if isinstance(v, bool) or not isinstance(v, int | float):
                errs.append(f"{name} must be a number, got {v!r}")
                return
            # int/max_aircraft feed straight into list slicing and API params;
            # a plausible-looking float (e.g. max_aircraft = 2.5, radius_km =
            # 30.5) passes a plain numeric-range check but crashes downstream
            # (SAMPLE_AIRCRAFT[:2.5] raises TypeError at boot). Reject any
            # non-integral float here instead of coercing silently.
            if isinstance(v, float) and not v.is_integer():
                errs.append(f"{name} must be a whole number, got {v!r}")
            elif not lo <= v <= hi:
                errs.append(f"{name} must be between {lo} and {hi}, got {v}")

        _num("latitude", -90, 90, required=True)
        _num("longitude", -180, 180, required=True)
        _int("radius_km", 2, 460)
        _int("max_aircraft", 1, 8)
        _num("interval", 5, 3600)
        layout = cfg.get("layout", "auto")
        if layout not in _LAYOUTS:
            errs.append(f"layout must be one of {_LAYOUTS}, got {layout!r}")
        demo = cfg.get("demo")
        if demo is not None and not isinstance(demo, bool):
            errs.append(f"demo must be a bool (true/false), got {demo!r}")
        return errs

    @classmethod
    def validate_config_warnings(cls, cfg: dict, ctx) -> list[str]:
        warns: list[str] = []
        layout = cfg.get("layout", "auto")
        if layout in ("hero", "dashboard") and ctx.scale == 1:
            warns.append(
                f'layout = "{layout}" needs a hi-res (scale > 1) sign; '
                "falling back to ticker"
            )
        if layout == "dashboard" and ctx.scale > 1 and ctx.panel_width < 400:
            warns.append(
                "dashboard layout is designed for panels >= 400 px wide; "
                "columns will crowd"
            )
        return warns
