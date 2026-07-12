"""Aircraft model, per-field formatting, vertical-rate cue, sample feed."""

import attrs

from led_ticker_flight.palette import CLIMB, DESCEND, LEVEL, RGB


@attrs.frozen
class Aircraft:
    flt: str
    actype: str
    alt: int
    vr: int
    gs: int
    trk: int
    dist: str
    dist_km: float = 0.0
    reg: str = ""


def vr_state(vr: int) -> str:
    if vr > 50:
        return "climb"
    if vr < -50:
        return "descend"
    return "level"


VR_COLOR: dict[str, RGB] = {"climb": CLIMB, "descend": DESCEND, "level": LEVEL}
VR_GLYPH: dict[str, str] = {"climb": "up", "descend": "down", "level": "level"}


def fmt_alt(alt: int) -> str:
    return f"{alt:,}FT"


# The handoff's sample flights (design/app.js) — the demo-mode feed.
SAMPLE_AIRCRAFT: list[Aircraft] = [
    Aircraft("UA2341", "B738", 34000, 1200, 460, 247, "12KM NE", 12.0, "N12345"),
    Aircraft("DL815", "A21N", 28000, -900, 420, 198, "6KM S", 6.0, "N815DN"),
    Aircraft("WN88", "B737", 39000, 0, 480, 90, "22KM E", 22.0, "N7088A"),
    Aircraft("BA49H", "B77W", 41000, 0, 510, 305, "31KM NW", 31.0, "G-STBA"),
]
