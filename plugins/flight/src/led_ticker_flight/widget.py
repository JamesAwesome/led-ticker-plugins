"""OverheadWidget — planes-overhead ADS-B tracker (flight.overhead)."""

import logging

import aiohttp
import attrs
from led_ticker.plugin import (
    ENGINE_TICK_MS,
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
    radius_km: int = 30
    layout: str = "auto"
    max_aircraft: int = 4
    interval: float = 10.0
    demo: bool = False
    # The engine's SHARED aiohttp session — core's _build_widget calls
    # `cls.start(session=session, **widget_cfg)`, and start() forwards it
    # here. None (direct construction, tests) => update() opens a temporary
    # session per poll instead.
    session: aiohttp.ClientSession | None = None
    _flights: list[Aircraft] = attrs.field(factory=list, init=False)

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

    def draw(self, canvas, cursor_pos=0, *, y_offset: int = 0, font_color=None):
        clock_ms = self._frame_count * ENGINE_TICK_MS
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

        _num("latitude", -90, 90, required=True)
        _num("longitude", -180, 180, required=True)
        _num("radius_km", 2, 460)
        _num("max_aircraft", 1, 8)
        _num("interval", 5, 3600)
        layout = cfg.get("layout", "auto")
        if layout not in _LAYOUTS:
            errs.append(f"layout must be one of {_LAYOUTS}, got {layout!r}")
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
