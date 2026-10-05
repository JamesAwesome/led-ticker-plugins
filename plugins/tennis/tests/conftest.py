"""Shared fixtures for the led-ticker-tennis test suite.

Real headless canvases come from `led_ticker.plugin` (HeadlessBackend /
ScaledCanvas, led-ticker-core >= 2.1) — the same shapes the sibling packs'
suites use: smallsign 160x16 scale 1; bigsign 256x64 and longboi 512x64
wrapped at scale 4 (16 logical rows).
"""

from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_tennis._models import MatchInfo
from led_ticker_tennis._source import _SHARED_SOURCES

TZ = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def reset_sources():
    _SHARED_SOURCES.clear()
    yield
    _SHARED_SOURCES.clear()


@pytest.fixture
def tz():
    return TZ


@pytest.fixture
def smallsign():
    return HeadlessBackend(160, 16).create_canvas()


@pytest.fixture
def bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


def live_match(**over) -> MatchInfo:
    """Lehecka (serving, 15) v Fils (40) — a break point in set 2."""
    kw = dict(
        match_id=90211,
        p1="Lehecka",
        p2="Fils",
        p1_full="Jiri Lehecka",
        p2_full="Arthur Fils",
        p1_rank=21,
        p2_rank=15,
        state="live",
        sets=(0, 1),
        games=[(4, 6), (3, 4)],
        points=("15", "40"),
        server=1,
        tour="atp",
        tournament="Cincinnati Open",
        round_code="R16",
    )
    kw.update(over)
    return MatchInfo(**kw)


def lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}
