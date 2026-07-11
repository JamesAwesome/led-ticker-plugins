"""Semantic color palette + airline tail-fin table.

Values are copied verbatim from design/README.md — never adjust them here.
"""

import re

import attrs

RGB = tuple[int, int, int]

IDENT: RGB = (255, 255, 255)
TYPE: RGB = (170, 90, 255)
ALT: RGB = (255, 180, 0)
SPEED: RGB = (60, 220, 60)
TRACK: RGB = (0, 220, 255)
DIST: RGB = (255, 80, 255)
CLIMB: RGB = (0, 255, 0)
DESCEND: RGB = (255, 60, 60)
LEVEL: RGB = (255, 180, 0)
LABEL: RGB = (70, 90, 130)
IDLE: RGB = (0, 150, 200)
LIVE: RGB = (0, 255, 0)


@attrs.frozen
class Airline:
    name: str
    c1: RGB
    c2: RGB


AIRLINES: dict[str, Airline] = {
    "UA": Airline("UNITED", (40, 95, 210), (235, 240, 255)),
    "DL": Airline("DELTA", (220, 40, 60), (30, 80, 150)),
    "WN": Airline("SOUTHWEST", (255, 190, 0), (220, 45, 55)),
    "BA": Airline("BRITISH", (40, 95, 175), (220, 45, 55)),
}
DEFAULT_AIRLINE = Airline("", (150, 160, 175), (90, 100, 115))


def airline_of(callsign: str) -> Airline:
    """Airline for a callsign's alphabetic prefix (first two letters)."""
    m = re.match(r"[A-Z]+", callsign)
    code = m.group(0)[:2] if m else ""
    return AIRLINES.get(code, DEFAULT_AIRLINE)
