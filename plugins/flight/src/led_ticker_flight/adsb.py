"""adsb.lol /v2/point client + geo math (haversine, bearing, 8-wind compass)."""

import math
from typing import TypeIs

import aiohttp

from led_ticker_flight.data import Aircraft

ADSB_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
KM_PER_NM = 1.852
_EARTH_RADIUS_KM = 6371.0
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _finite(v: object) -> TypeIs[int | float]:
    """True for a real, finite (non-NaN/non-inf) int/float, excluding bool.

    `round()` and the haversine/bearing trig raise on NaN/inf, which would
    otherwise crash `parse_point_response` for the WHOLE batch over one bad
    aircraft (task-10-adversarial finding #2). `TypeIs` (not `bool`) so
    pyright narrows `v` to `int | float` after `if not _finite(v): continue`,
    matching the isinstance-based narrowing this replaced."""
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def radius_nm(radius_km: int) -> int:
    return max(1, min(250, round(radius_km / KM_PER_NM)))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def compass8(deg: float) -> str:
    return _COMPASS[int(((deg + 22.5) % 360) // 45)]


def parse_point_response(
    payload: dict, lat: float, lon: float, max_aircraft: int
) -> list[Aircraft]:
    out: list[Aircraft] = []
    # Normalize ac_list: if not a list, treat as empty.
    ac_list = payload.get("ac")
    if not isinstance(ac_list, list):
        ac_list = []

    for ac in ac_list:
        # Skip non-dict entries.
        if not isinstance(ac, dict):
            continue

        # Guard string fields: only call .strip() on actual strings.
        flight_val = ac.get("flight")
        flt = flight_val.strip() if isinstance(flight_val, str) else ""
        if not flt:
            continue

        ac_lat, ac_lon = ac.get("lat"), ac.get("lon")
        # Ensure lat/lon are numeric AND finite (drop if non-numeric/NaN/inf).
        if not _finite(ac_lat):
            continue
        if not _finite(ac_lon):
            continue

        alt = ac.get("alt_baro")
        if not _finite(alt):
            continue  # "ground", missing, or NaN/inf

        # Guard baro_rate: treat non-numeric/NaN/inf as absent, fall back to geom_rate.
        baro_rate = ac.get("baro_rate")
        if _finite(baro_rate):
            vr = baro_rate
        else:
            geom_rate = ac.get("geom_rate")
            vr = geom_rate if _finite(geom_rate) else 0

        km = haversine_km(lat, lon, ac_lat, ac_lon)
        wind = compass8(bearing_deg(lat, lon, ac_lat, ac_lon))

        # Guard ground speed: treat non-numeric/NaN/inf as 0.
        gs_val = ac.get("gs")
        gs: int | float = gs_val if _finite(gs_val) else 0

        # Guard track: treat non-numeric/NaN/inf as 0.
        track_val = ac.get("track")
        track: int | float = track_val if _finite(track_val) else 0

        # Guard type and registration: only call .strip() on actual strings.
        type_val = ac.get("t")
        actype = type_val.strip() if isinstance(type_val, str) else ""

        reg_val = ac.get("r")
        reg = reg_val.strip() if isinstance(reg_val, str) else ""

        out.append(
            Aircraft(
                flt=flt,
                actype=actype,
                alt=round(alt),
                vr=round(vr),
                gs=round(gs),
                trk=round(track) % 360,
                dist=f"{round(km)}KM {wind}",
                dist_km=km,
                reg=reg,
            )
        )
    out.sort(key=lambda a: a.dist_km)
    return out[:max_aircraft]


async def fetch_overhead(
    session: aiohttp.ClientSession, lat: float, lon: float, radius_nm_val: int
) -> dict:
    url = ADSB_URL.format(lat=lat, lon=lon, radius=radius_nm_val)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()
