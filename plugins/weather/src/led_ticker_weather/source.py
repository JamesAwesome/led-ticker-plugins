"""weather.current polled SOURCE — a value token like `:weather.nyc:`.

Subclasses the core PolledDataSource mechanism (led-ticker-core >= 4.1): core
drives a supervised poll loop that calls `update()` every `interval` seconds;
`update()` fetches and renders a `format` string over the exposed fields, then
`self._set_value(...)` (write-order). Current-conditions fields only.
"""

import string
from typing import Any

import attrs
from led_ticker.plugin import PolledDataSource

from led_ticker_weather.weather import _match_condition, fetch_current

_DEFAULT_FORMAT = "{temp_f}°F {condition}"

# Fields exposed to `format`. Current-endpoint only (/current.json). `emoji` is
# the colon-wrapped condition slug — it composes: token substitution runs before
# layout, so draw_with_emoji renders it as a sprite. (high_f/low_f need the
# forecast endpoint — out of scope.)
_FIELDS = (
    "temp_f",
    "temp_c",
    "condition",
    "feelslike_f",
    "feelslike_c",
    "humidity",
    "wind_mph",
    "emoji",
)


@attrs.define(eq=False)
class WeatherSource(PolledDataSource):
    location: Any = attrs.field(default="", kw_only=True)
    format: str = attrs.field(default=_DEFAULT_FORMAT, kw_only=True)
    placeholder: str = attrs.field(default="…", kw_only=True)

    @classmethod
    def validate_config(cls, cfg: dict) -> list[str]:
        errors: list[str] = []
        if not cfg.get("location"):
            errors.append("weather.current: 'location' is required.")
        fmt = cfg.get("format", _DEFAULT_FORMAT)
        for _literal, field_name, _spec, _conv in string.Formatter().parse(fmt):
            if field_name and field_name not in _FIELDS:
                errors.append(
                    f"weather.current: unknown field '{{{field_name}}}' in format "
                    f"(known: {', '.join(_FIELDS)})."
                )
        return errors

    def __attrs_post_init__(self) -> None:
        # TOML may give location as {lat, lon} (same as the widget).
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"
        # Show the placeholder until the first successful fetch (version stays 0).
        self.current = self.placeholder

    async def update(self) -> None:
        current = await fetch_current(self.session, self.location)
        condition = current["condition"]["text"]
        fields = {
            "temp_f": int(current["temp_f"]),
            "temp_c": int(current["temp_c"]),
            "condition": condition,
            "feelslike_f": int(current["feelslike_f"]),
            "feelslike_c": int(current["feelslike_c"]),
            "humidity": int(current["humidity"]),
            "wind_mph": int(current["wind_mph"]),
            "emoji": f":{_match_condition(condition)}:",
        }
        # write-order: _set_value writes current before version, no await between.
        self._set_value(self.format.format(**fields))
