"""Forecast data layer: WeatherAPI /v1/forecast.json fetch, condition-code
-> kind mapping (handoff condKind, ported verbatim), kind -> emoji-slug
tables, and the parsed models the renderers consume.

Icon language (spec divergence 1): kinds resolve to PACKAGED emoji — the
curated 8x8/32x32 weather pairs everywhere, upgraded to standard-pack
sprites for two hero-only distinctions (overcast, patchy rain) that the
curated set can't draw. Strips always use the lowres column.
"""

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
