"""Forecast data layer: WeatherAPI /v1/forecast.json fetch, condition-code
-> kind mapping (handoff condKind, ported verbatim), kind -> emoji-slug
tables, and the parsed models the renderers consume.

Icon language (spec divergence 1): kinds resolve to PACKAGED emoji — the
curated 8x8/32x32 weather pairs everywhere, upgraded to standard-pack
sprites for two hero-only distinctions (overcast, patchy rain) that the
curated set can't draw. Strips always use the lowres column.
"""

import datetime
import os

import aiohttp
import attrs

from led_ticker_weather.paint import js_round

# WeatherAPI condition codes, from the handoff table (design/README.md):
#   1000 sunny/clear · 1003 partly · 1006 cloudy · 1009 overcast ·
#   1030/1135/1147 fog · 1063/1150-1201/1240-1246 rain ·
#   1066/1114/1210-1225/1255-1258 snow · 1087/1273-1282 thunder.
# The patchy/solid rain split (spec Icons table) refines the rain band:
# patchy = 1063, 1150-1183, 1240; solid = 1186-1201, 1243-1246.
_FOG_CODES = frozenset({1030, 1135, 1147})
_SNOW_SINGLES = frozenset({1066, 1114})
_PATCHY_RAIN_SINGLES = frozenset({1063, 1240})


def cond_kind(code: int, is_day: int) -> str:
    """Map a WeatherAPI condition code (+ is_day) to a glyph kind."""
    if code == 1000:
        return "sunny" if is_day else "clear"
    if code == 1003:
        return "partly" if is_day else "partly_night"
    if code == 1006:
        return "cloudy"
    if code == 1009:
        return "overcast"
    if code in _FOG_CODES:
        return "fog"
    if code == 1087 or 1273 <= code <= 1282:
        return "thunder"
    if code in _SNOW_SINGLES or 1210 <= code <= 1225 or 1255 <= code <= 1258:
        return "snow"
    if code in _PATCHY_RAIN_SINGLES or 1150 <= code <= 1183:
        return "rain_patchy"
    if 1186 <= code <= 1201 or 1243 <= code <= 1246:
        return "rain"
    return "cloudy"  # unknown -> handoff drawIcon default (plain cloud)


# kind -> (lowres_slug, hero_hires_slug). Lowres column: curated 8x8
# sprites only (strips + smallsign — must render on every sign). Hires
# column: what the HERO slot draws at scale > 1; two entries upgrade to
# standard-pack sprites (hires-only, fine in the hero, never in strips).
KIND_SLUGS: dict[str, tuple[str, str]] = {
    "sunny": ("sun", "sun"),
    "clear": ("moon", "moon"),
    "partly": ("partly_cloudy", "partly_cloudy"),
    "partly_night": ("partly_cloudy", "moon"),
    "cloudy": ("cloud", "cloud"),
    "overcast": ("cloud", "sun_behind_large_cloud"),
    "rain": ("rain", "rain"),
    "rain_patchy": ("rain", "sun_behind_rain_cloud"),
    "thunder": ("thunder", "thunder"),
    "snow": ("snow", "snow"),
    "fog": ("fog", "fog"),
}


FORECAST_URL: str = "https://api.weatherapi.com/v1/forecast.json"

# Always request the deepest strip any layout wants (longboi: today + 6).
# Free-tier keys return fewer days; parsing and the renderers degrade
# (spec: Data — degrade on short feed).
_REQUEST_DAYS = 7


@attrs.frozen
class DayForecast:
    label: str  # weekday abbrev ("TUE")
    kind: str  # cond_kind() output
    hi_f: float
    lo_f: float
    pop: int  # daily_chance_of_rain, 0-100


@attrs.frozen
class CurrentConditions:
    temp_f: float
    feels_f: float
    kind: str
    hi_f: float  # today's forecast hi (forecastday[0])
    lo_f: float


@attrs.frozen
class ForecastData:
    location: str
    current: CurrentConditions
    days: tuple[DayForecast, ...]  # tomorrow onward (forecastday[1:])


def display_temp(f: float, units: str) -> int:
    """Handoff `TF()`: whole degrees, js_round; metric converts from F."""
    if units == "metric":
        return js_round((f - 32) * 5 / 9)
    return js_round(f)


def _day_label(date_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    return d.strftime("%a").upper()[:3]


def parse_forecast_payload(payload: dict) -> ForecastData:
    """Field mapping per design/README.md Data Sources (inlined in the
    .dc.html above its data block)."""
    cur = payload["current"]
    fdays = payload["forecast"]["forecastday"]
    today = fdays[0]["day"]
    current = CurrentConditions(
        temp_f=cur["temp_f"],
        feels_f=cur["feelslike_f"],
        kind=cond_kind(cur["condition"]["code"], cur["is_day"]),
        hi_f=today["maxtemp_f"],
        lo_f=today["mintemp_f"],
    )
    days = tuple(
        DayForecast(
            label=_day_label(fd["date"]),
            kind=cond_kind(fd["day"]["condition"]["code"], 1),
            hi_f=fd["day"]["maxtemp_f"],
            lo_f=fd["day"]["mintemp_f"],
            pop=int(fd["day"]["daily_chance_of_rain"]),
        )
        for fd in fdays[1:]
    )
    return ForecastData(
        location=payload["location"]["name"], current=current, days=days
    )


async def fetch_forecast(session: aiohttp.ClientSession | None, location: str) -> dict:
    """GET /v1/forecast.json and return the raw payload dict. Reads
    WEATHERAPI_KEY from env; raises ValueError on a missing key or an API
    error (same convention as weather.py's fetch_current). `session` is
    the ENGINE'S SHARED session when run by core (never close it; timeout
    is per-request); None (tests, direct use) opens a short-lived one.
    """
    api_key = os.getenv("WEATHERAPI_KEY", "")
    if not api_key:
        raise ValueError("WEATHERAPI_KEY not set. Add it to your .env file.")
    params = {
        "key": api_key,
        "q": location,
        "days": _REQUEST_DAYS,
        "aqi": "no",
        "alerts": "no",
    }
    timeout = aiohttp.ClientTimeout(total=10)
    if session is None:
        async with aiohttp.ClientSession() as own, own.get(
            FORECAST_URL, params=params, timeout=timeout
        ) as resp:
            data = await resp.json()
    else:
        async with session.get(FORECAST_URL, params=params, timeout=timeout) as resp:
            data = await resp.json()
    if "error" in data:
        code = data["error"].get("code", "?")
        msg = data["error"].get("message", "Unknown error")
        raise ValueError(f"WeatherAPI error {code}: {msg}")
    return data


# The handoff's fixed sample week (design .dc.html CUR/FC data block),
# used by demo = true and the layout tests. Fictional placeholder data.
DEMO_DATA: ForecastData = ForecastData(
    location="BOSTON",
    current=CurrentConditions(temp_f=78, feels_f=80, kind="partly", hi_f=82, lo_f=64),
    days=(
        DayForecast(label="TUE", kind="sunny", hi_f=86, lo_f=66, pop=0),
        DayForecast(label="WED", kind="thunder", hi_f=79, lo_f=68, pop=60),
        DayForecast(label="THU", kind="rain", hi_f=74, lo_f=65, pop=80),
        DayForecast(label="FRI", kind="cloudy", hi_f=77, lo_f=63, pop=30),
        DayForecast(label="SAT", kind="sunny", hi_f=83, lo_f=62, pop=5),
        DayForecast(label="SUN", kind="partly", hi_f=85, lo_f=64, pop=15),
    ),
)
