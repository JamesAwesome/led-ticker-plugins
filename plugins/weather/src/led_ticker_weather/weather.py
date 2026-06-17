"""Weather widget using WeatherAPI.com (feeds.weather)."""

import logging
import os
from typing import Any, Self

import aiohttp
import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    Canvas,
    Color,
    ColorProvider,
    DrawResult,
    Font,
    FrameAwareBase,
    coerce_color_provider,
    compute_baseline,
    compute_cursor,
    draw_emoji_at,
    draw_text,
    draw_text_per_char,
    get_text_width,
    measure_emoji_at,
    run_monitor_loop,
    spawn_tracked,
)
from led_ticker.plugin import (
    colors as _colors,
)

WEATHERAPI_URL: str = "https://api.weatherapi.com/v1/current.json"


def _match_condition(condition: str) -> str:
    """Map a WeatherAPI condition string to an emoji slug."""
    c = condition.lower()
    if "thunder" in c:
        return "thunder"
    if "snow" in c or "blizzard" in c or "ice" in c or "sleet" in c:
        return "snow"
    if "rain" in c or "drizzle" in c or "shower" in c:
        return "rain"
    if "fog" in c or "mist" in c:
        return "fog"
    if "partly" in c:
        return "partly_cloudy"
    if "cloud" in c or "overcast" in c:
        return "cloud"
    # Sunny, Clear, or anything else
    return "sun"


@attrs.define
class WeatherWidget(FrameAwareBase):
    """Current weather display widget."""

    session: aiohttp.ClientSession
    location: str  # query string: "New York", "10001", "40.71,-74.01"
    text: str
    units: str = "imperial"
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color | ColorProvider = attrs.Factory(lambda: _colors.DEFAULT_COLOR)
    # WeatherWidget keeps two color knobs: `font_color` for the label
    # (e.g. "Brooklyn:") and `font_color_temp` for the temperature
    # value (e.g. "64°F"). They're separate so a config can color the
    # label with an effect (`font_color = "rainbow"`) while keeping
    # the temp value in a steady high-contrast color (default white).
    # If you want the temp to also use the effect, set them both:
    #   font_color = "rainbow"
    #   font_color_temp = "rainbow"
    font_color_temp: Color | ColorProvider = attrs.Factory(lambda: _colors.RGB_WHITE)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    hold_time: float = 0.0
    show_icon: bool = True
    unit_symbol: str = attrs.field(init=False, default="")
    current_temp: int = attrs.field(init=False, default=0)
    weather: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self) -> None:
        # Coerce raw TOML color specs into ColorProvider instances. font_color is
        # also pre-coerced by core (shared field name) — coerce_color_provider is
        # idempotent, so this is a safe pass-through there. font_color_temp is
        # plugin-unique and NOT coerced by core, so this is where its rich forms
        # ("rainbow", {style=...}, etc.) are parsed.
        self.font_color = coerce_color_provider(self.font_color, "font_color")
        self.font_color_temp = coerce_color_provider(
            self.font_color_temp, "font_color_temp"
        )

        # Support dict location from TOML: {lat = 40.71, lon = -74.01}
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"

        if self.units == "imperial":
            self.unit_symbol = "F"
        elif self.units == "metric":
            self.unit_symbol = "C"

    @classmethod
    async def start(
        cls, *args: Any, update_interval: int = 10800, **kwargs: Any
    ) -> Self:
        widget = cls(*args, **kwargs)
        try:
            await widget.update()
        except Exception:
            logging.exception(
                "Weather initial update failed for %s, will retry in background",
                widget.location,
            )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating weather for: %s", self.location)
        api_key = os.getenv("WEATHERAPI_KEY", "")
        if not api_key:
            raise ValueError("WEATHERAPI_KEY not set. Add it to your .env file.")
        params = {
            "key": api_key,
            "q": self.location,
        }
        async with self.session.get(
            WEATHERAPI_URL,
            params=params,
        ) as response:
            data = await response.json()

            # WeatherAPI returns {"error": {...}} on failure
            if "error" in data:
                code = data["error"].get("code", "?")
                msg = data["error"].get("message", "Unknown error")
                raise ValueError(f"WeatherAPI error {code}: {msg}")

            current = data["current"]
            if self.units == "imperial":
                self.current_temp = int(current["temp_f"])
            else:
                self.current_temp = int(current["temp_c"])
            self.weather = current["condition"]["text"]

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        temp_text = f"{self.current_temp}{self.unit_symbol}"
        label_text = f"{self.text}: "

        # Resolve the icon slug once and read its actual rendered footprint
        # via `measure_emoji_at` — keeps layout in sync with whichever
        # variant `draw_emoji_at` will pick (lowres on plain canvas,
        # hires-when-available on a ScaledCanvas, falling back to lowres
        # for slugs without a HIRES_REGISTRY entry like `partly_cloudy`).
        # Reading the footprint dynamically scales correctly across
        # per-section `scale` overrides — at scale=2 a hires sprite is 16
        # logical wide, and a hardcoded `8` here would let the temperature
        # text overlap the icon.
        if self.show_icon:
            content_width = (
                get_text_width(self.font, label_text, padding=0, canvas=canvas)
                + measure_emoji_at(canvas, _match_condition(self.weather))
                + get_text_width(self.font, temp_text, padding=0, canvas=canvas)
            )
        else:
            condition_text = f"{self.weather} "
            content_width = get_text_width(
                self.font,
                f"{label_text}{condition_text}{temp_text}",
                padding=0,
                canvas=canvas,
            )

        cursor_pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            self.padding,
            center=self.center,
        )

        baseline_y = compute_baseline(self.font, canvas, valign="center") + y_offset

        cursor_pos += self._draw_segment(
            canvas,
            cursor_pos,
            baseline_y,
            self.font_color,
            label_text,
            frame_count=self.frame_for("font_color"),
        )

        if self.show_icon:
            # Bottom-anchor the condition icon at the text baseline (exact at
            # any scale via draw_emoji_at's real-pixel bottom-anchor).
            cursor_pos += draw_emoji_at(
                canvas,
                _match_condition(self.weather),
                int(cursor_pos),
                bottom_baseline=baseline_y,
            )
        else:
            cursor_pos += self._draw_segment(
                canvas,
                cursor_pos,
                baseline_y,
                self.font_color,
                f"{self.weather} ",
                frame_count=self.frame_for("font_color"),
            )

        cursor_pos += self._draw_segment(
            canvas,
            cursor_pos,
            baseline_y,
            self.font_color_temp,
            temp_text,
            frame_count=self.frame_for("font_color_temp"),
        )
        cursor_pos += end_padding

        return canvas, cursor_pos

    def _draw_segment(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        provider: ColorProvider,
        text: str,
        frame_count: int,
    ) -> int:
        """Render one weather text segment (label / condition / temp).

        Per-char providers (rainbow / gradient) iterate chars via
        `draw_text_per_char` so each char renders with its own hue.
        Whole-string providers (constant / color_cycle / random)
        materialize once and use `draw_text`. Mirrors the per-char
        dispatch in `TickerCountdown.draw` and image widgets'
        `_draw_text` — without it, `font_color = "rainbow"` on
        weather collapsed the label / condition / temp to a single
        sweeping hue.
        """
        if provider.per_char:
            return draw_text_per_char(
                canvas,
                self.font,
                x,
                baseline_y,
                text,
                lambda idx, total: provider.color_for(frame_count, idx, total),
            )
        color = provider.color_for(frame_count, 0, len(text) if text else 1)
        # plugin draw_text signature: (canvas, font, text, x, y, color) → absolute x.
        # Subtract starting x to return relative advance width.
        return draw_text(canvas, self.font, text, x, baseline_y, color) - x
