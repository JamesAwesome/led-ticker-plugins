"""adsb.lol /v2/point client + geo math (haversine, bearing, 8-wind compass)."""

import math

import aiohttp

from led_ticker_flight.data import Aircraft

ADSB_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
KM_PER_NM = 1.852
_EARTH_RADIUS_KM = 6371.0
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


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
    for ac in payload.get("ac", []):
        flt = (ac.get("flight") or "").strip()
        ac_lat, ac_lon = ac.get("lat"), ac.get("lon")
        alt = ac.get("alt_baro")
        if not flt or ac_lat is None or ac_lon is None:
            continue
        if not isinstance(alt, int | float) or isinstance(alt, bool):
            continue  # "ground" or missing
        vr = ac.get("baro_rate")
        if vr is None:
            vr = ac.get("geom_rate") or 0
        km = haversine_km(lat, lon, ac_lat, ac_lon)
        wind = compass8(bearing_deg(lat, lon, ac_lat, ac_lon))
        out.append(
            Aircraft(
                flt=flt,
                actype=(ac.get("t") or "").strip(),
                alt=round(alt),
                vr=round(vr),
                gs=round(ac.get("gs") or 0),
                trk=round(ac.get("track") or 0) % 360,
                dist=f"{round(km)}KM {wind}",
                dist_km=km,
                reg=(ac.get("r") or "").strip(),
            )
        )
    out.sort(key=lambda a: a.dist_km)
    return out[:max_aircraft]


async def fetch_overhead(
    session: aiohttp.ClientSession, lat: float, lon: float, radius: int
) -> dict:
    url = ADSB_URL.format(lat=lat, lon=lon, radius=radius)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()
