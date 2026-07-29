"""weather.forecast — held multi-day forecast card with per-sign layouts.

`resolve_forecast_layout` is stateless and runs fresh on every draw tick
(flight pattern) so hot-reloads and canvas swaps always re-resolve. The
400px physical-width threshold splits bigsign (256 -> "big") from longboi
(512 -> "long"), the same convention as baseball/flight/stocks.
"""

import logging

import aiohttp
import attrs
from led_ticker.plugin import (
    Color,
    FrameAwareBase,
    run_monitor_loop,
    safe_scale,
    spawn_tracked,
    unwrap_to_real,
)

from led_ticker_weather.forecast_data import (
    DEMO_DATA,
    ForecastData,
    fetch_forecast,
    parse_forecast_payload,
)
from led_ticker_weather.forecast_layouts import (
    render_hero_big,
    render_hero_long,
    render_strip_small,
)

VALID_LAYOUTS: tuple[str, ...] = ("auto", "strip", "big", "long")

_WIDE_MIN_W = 400


def resolve_forecast_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if scale <= 1:
        return "strip"  # hi-res layouts are impossible on a scale-1 sign
    if cfg_layout == "long" and phys_w < _WIDE_MIN_W:
        # Width-fit degrade: render_hero_long hardcodes anchors out to
        # x~506; on a 256px panel it would draw mostly off-panel — land on
        # what "auto" would already pick there instead.
        return "big"
    if cfg_layout != "auto":
        return cfg_layout
    return "big" if phys_w < _WIDE_MIN_W else "long"


@attrs.define
class ForecastWidget(FrameAwareBase):
    """weather.forecast — held multi-day forecast card."""

    location: str = ""
    layout: str = "auto"
    units: str = "imperial"
    update_interval: int = attrs.field(default=10800, converter=int)
    demo: bool = False
    # Demo-only: truncate the fixed demo week to this many strip days (0 =
    # full 6-day week) so a config can preview a SHORT feed — the justify
    # fill spreading fewer days across the panel — without a live API key.
    demo_days: int = attrs.field(default=0, converter=int)
    # The engine's SHARED aiohttp session (core's _build_widget passes it
    # to start()); never close it. None (tests/direct) => fetch_forecast
    # opens a short-lived session per poll.
    session: aiohttp.ClientSession | None = None
    # Declared only — the ENGINE paints bg (Clear/Fill + transition bg
    # kwargs); draw() must never Fill (push-transition compositing draws
    # outgoing + incoming on the SAME canvas).
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    _data: ForecastData | None = attrs.field(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        # dict location from TOML ({lat = 40.71, lon = -74.01}), same
        # convention as weather.current.
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"
        if self.demo:
            data = DEMO_DATA
            if self.demo_days > 0:
                data = attrs.evolve(data, days=data.days[: self.demo_days])
            self._data = data
        elif not self.location:
            raise ValueError("weather.forecast requires location (or demo = true)")

    @classmethod
    async def start(cls, *args, **kwargs):
        widget = cls(*args, **kwargs)
        if not widget.demo:
            try:
                await widget.update()
            except Exception:
                logging.exception(
                    "weather.forecast initial fetch failed for %s; "
                    "will retry in background",
                    widget.location,
                )
            # An eager fetch that FAILED (widget._data is still None) means
            # the loop's first pass must poll immediately instead of
            # sleeping a full update_interval (~3h default) — otherwise a
            # boot-time network blip hides the widget (should_display()
            # False) for hours. This also engages the loop's backoff if the
            # immediate retry fails too. A successful eager fetch keeps
            # immediate=False (no double-fetch on the happy path).
            spawn_tracked(
                run_monitor_loop(
                    widget, widget.update_interval, immediate=widget._data is None
                )
            )
        return widget

    async def update(self) -> None:
        payload = await fetch_forecast(self.session, self.location)
        self._data = parse_forecast_payload(payload)
        logging.info(
            "weather.forecast %s updated: current + %d days",
            self.location,
            len(self._data.days),
        )

    def should_display(self) -> bool:
        """Hide from the rotation until data exists (core visibility seam)."""
        return self._data is not None

    def draw(self, canvas, cursor_pos=0, *, y_offset: int = 0, font_color=None):
        data = self._data
        if data is None:
            # Belt only — _expand_sources already drops us via
            # should_display(); a transition compositor may still call.
            return canvas, canvas.width
        layout = resolve_forecast_layout(
            self.layout, safe_scale(canvas), unwrap_to_real(canvas).width
        )
        if layout == "strip":
            render_strip_small(canvas, data, self.units, y_offset=y_offset)
        elif layout == "big":
            render_hero_big(canvas, data, self.units, y_offset=y_offset)
        else:
            render_hero_long(canvas, data, self.units, y_offset=y_offset)
        # Held card: LOGICAL width (never real.width — the engine compares
        # against the wrapper's width; real.width takes the scroll branch).
        return canvas, canvas.width

    @classmethod
    def validate_config(cls, cfg) -> list[str]:
        errs: list[str] = []
        layout = cfg.get("layout", "auto")
        if layout not in VALID_LAYOUTS:
            errs.append(f"layout must be one of {VALID_LAYOUTS}, got {layout!r}")
        units = cfg.get("units", "imperial")
        if units not in ("imperial", "metric"):
            errs.append(f'units must be "imperial" or "metric", got {units!r}')
        if not cfg.get("demo", False) and not cfg.get("location"):
            errs.append("location is required unless demo = true")
        interval = cfg.get("update_interval", 10800)
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
        ):
            errs.append(f"update_interval must be a positive number, got {interval!r}")
        demo_days = cfg.get("demo_days", 0)
        if (
            isinstance(demo_days, bool)
            or not isinstance(demo_days, int)
            or demo_days < 0
        ):
            errs.append(f"demo_days must be a non-negative integer, got {demo_days!r}")
        return errs

    @classmethod
    def validate_config_warnings(cls, cfg, ctx) -> list[str]:
        warns: list[str] = []
        layout = cfg.get("layout", "auto")
        if layout in ("big", "long") and ctx.scale == 1:
            warns.append(
                f'layout = "{layout}" needs a hi-res (scale > 1) sign; '
                'this panel will render the "strip" layout'
            )
        elif layout == "long" and ctx.scale > 1 and ctx.panel_width < 400:
            warns.append(
                'layout = "long" is designed for panels >= 400 px wide; '
                'this panel will render the "big" layout'
            )
        return warns
