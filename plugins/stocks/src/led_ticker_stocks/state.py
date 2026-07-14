"""Market-state machine: Finnhub status (primary) + US/Eastern clock (fallback)."""

import datetime
import enum

import attrs


class MarketState(enum.Enum):
    PRE = "pre"
    OPEN = "open"
    AFTER = "after"
    CLOSED = "closed"


@attrs.define(frozen=True)
class StateMeta:
    dim: float
    chip_label: str
    chip_rgb: tuple
    pulses: bool


STATE_META = {
    MarketState.PRE: StateMeta(0.85, "PRE", (255, 180, 0), False),
    MarketState.OPEN: StateMeta(1.0, "LIVE", (0, 255, 0), True),
    MarketState.AFTER: StateMeta(0.85, "AH", (170, 90, 255), False),
    MarketState.CLOSED: StateMeta(0.45, "CLSD", (255, 60, 60), False),
}

_SESSION_MAP = {
    "pre-market": MarketState.PRE,
    "regular": MarketState.OPEN,
    "post-market": MarketState.AFTER,
}


def state_from_status(payload: dict) -> MarketState:
    """Map Finnhub status. `closed = not isOpen` covers holidays + null session."""
    if not payload.get("isOpen"):
        return MarketState.CLOSED
    session = payload.get("session")
    if isinstance(session, str):
        return _SESSION_MAP.get(session, MarketState.OPEN)
    return MarketState.OPEN


def state_from_clock(now_eastern: datetime.datetime) -> MarketState:
    """US/Eastern fallback: weekday + regular-session windows."""
    if now_eastern.weekday() >= 5:  # Sat/Sun
        return MarketState.CLOSED
    minutes = now_eastern.hour * 60 + now_eastern.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return MarketState.PRE
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return MarketState.OPEN
    if 16 * 60 <= minutes < 20 * 60:
        return MarketState.AFTER
    return MarketState.CLOSED
