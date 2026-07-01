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

# Typed sample for validate_config dry-run: one value per field, covers all
# conversion specs (:d, :.1f, :s, etc.) without hitting the real API.
_SAMPLE: dict[str, Any] = {
    "temp_f": 0,
    "temp_c": 0,
    "condition": "x",
    "feelslike_f": 0,
    "feelslike_c": 0,
    "humidity": 0,
    "wind_mph": 0,
    "emoji": ":sun:",
}


@attrs.define(eq=False)
class WeatherSource(PolledDataSource):
    location: Any = attrs.field(default="", kw_only=True)
    format: str = attrs.field(default=_DEFAULT_FORMAT, kw_only=True)
    placeholder: str = attrs.field(default="…", kw_only=True)
    # Cached at construction: only the field names referenced in `format`.
    # Declared as an attrs field (slotted class) — set in __attrs_post_init__.
    _used_fields: tuple[str, ...] = attrs.field(init=False, factory=tuple)

    @classmethod
    def validate_config(cls, cfg: dict) -> list[str]:
        errors: list[str] = []
        if not cfg.get("location"):
            errors.append("weather.current: 'location' is required.")
        fmt = cfg.get("format", _DEFAULT_FORMAT)
        if not isinstance(fmt, str):
            errors.append(
                f"weather.current: 'format' must be a string, got {type(fmt).__name__}."
            )
            return errors
        # Parse the format (guarded: an unclosed brace like "{temp_f" raises
        # ValueError — surface it as a clean plugin error, not a raised exception).
        try:
            parsed = list(string.Formatter().parse(fmt))
        except ValueError as exc:
            errors.append(f"weather.current: malformed format string: {exc}")
            return errors
        # Check for unknown field names first (gives a clearer message).
        for _literal, field_name, _spec, _conv in parsed:
            if field_name and field_name not in _FIELDS:
                errors.append(
                    f"weather.current: unknown field '{{{field_name}}}' in format "
                    f"(known: {', '.join(_FIELDS)})."
                )
        # Dry-run against typed samples to catch bad conversion specs
        # (e.g. "{temp_f:zzz}", "{condition:d}", nested braces).
        # Skip if we already flagged an unknown field — the sample won't have it.
        if not errors:
            try:
                fmt.format(**_SAMPLE)
            except (ValueError, KeyError, IndexError) as exc:
                errors.append(f"weather.current: invalid format string: {exc}")
        return errors

    def __attrs_post_init__(self) -> None:
        # TOML may give location as {lat, lon} (same as the widget).
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"
        # Cache the field names actually referenced by the format string so
        # update() only reads the fields it needs (Finding 1: lazy field build).
        self._used_fields = tuple(
            name for _, name, _, _ in string.Formatter().parse(self.format) if name
        )
        # Show the placeholder until the first successful fetch (version stays 0).
        self.current = self.placeholder

    def _field_value(self, current: dict, name: str) -> Any:
        """Compute one field value by name from the raw API response dict."""
        if name == "temp_f":
            return int(current["temp_f"])
        if name == "temp_c":
            return int(current["temp_c"])
        if name == "condition":
            return current["condition"]["text"]
        if name == "feelslike_f":
            return int(current["feelslike_f"])
        if name == "feelslike_c":
            return int(current["feelslike_c"])
        if name == "humidity":
            return int(current["humidity"])
        if name == "wind_mph":
            return int(current["wind_mph"])
        if name == "emoji":
            condition = current["condition"]["text"]
            return f":{_match_condition(condition)}:"
        raise KeyError(name)  # unreachable for validated formats

    async def update(self) -> None:
        current = await fetch_current(self.session, self.location)
        # Build only the fields the format string actually references (lazy).
        # An unused field absent from the API response can no longer cause a
        # KeyError here — only referenced fields are fetched from `current`.
        fields = {name: self._field_value(current, name) for name in self._used_fields}
        # write-order: _set_value writes current before version, no await between.
        self._set_value(self.format.format(**fields))
