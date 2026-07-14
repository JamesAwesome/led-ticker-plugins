import datetime
import zoneinfo

from led_ticker_stocks.state import (
    STATE_META,
    MarketState,
    state_from_clock,
    state_from_status,
)

ET = zoneinfo.ZoneInfo("America/New_York")


def test_status_closed_when_not_open():
    assert state_from_status({"isOpen": False, "session": None}) is MarketState.CLOSED
    assert (
        state_from_status({"isOpen": False, "session": "pre-market"})
        is MarketState.CLOSED
    )


def test_status_sessions_when_open():
    assert (
        state_from_status({"isOpen": True, "session": "pre-market"}) is MarketState.PRE
    )
    assert state_from_status({"isOpen": True, "session": "regular"}) is MarketState.OPEN
    assert (
        state_from_status({"isOpen": True, "session": "post-market"})
        is MarketState.AFTER
    )
    # open with an unknown/null session still counts as OPEN
    assert state_from_status({"isOpen": True, "session": None}) is MarketState.OPEN


def test_clock_boundaries():
    def at(h, m):
        return datetime.datetime(2026, 7, 13, h, m, tzinfo=ET)  # a Monday

    assert state_from_clock(at(5, 0)) is MarketState.PRE
    assert state_from_clock(at(10, 0)) is MarketState.OPEN
    assert state_from_clock(at(17, 0)) is MarketState.AFTER
    assert state_from_clock(at(21, 0)) is MarketState.CLOSED
    assert state_from_clock(at(3, 0)) is MarketState.CLOSED


def test_clock_weekend_is_closed():
    sat = datetime.datetime(2026, 7, 11, 11, 0, tzinfo=ET)
    assert state_from_clock(sat) is MarketState.CLOSED


def test_state_meta_dims_and_labels():
    assert STATE_META[MarketState.OPEN].dim == 1.0
    assert STATE_META[MarketState.CLOSED].dim == 0.45
    assert STATE_META[MarketState.PRE].dim == 0.85
    assert STATE_META[MarketState.OPEN].chip_label == "LIVE"
    assert STATE_META[MarketState.CLOSED].chip_label == "CLSD"
    assert STATE_META[MarketState.OPEN].pulses is True
