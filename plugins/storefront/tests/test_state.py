import logging
from datetime import datetime

from led_ticker_storefront.config import parse_config
from led_ticker_storefront.state import POLL_INTERVAL_S, StorefrontState


def _state():
    cfg = parse_config({"schedule": {"mon": "09:00-17:00"}})
    return StorefrontState(config=cfg)


def test_poll_interval_default():
    assert POLL_INTERVAL_S == 30.0


def test_refresh_sets_open_closed():
    st = _state()
    st.refresh(datetime(2024, 1, 1, 10, 0))  # Monday 10:00
    assert st.is_open is True
    st.refresh(datetime(2024, 1, 1, 20, 0))  # Monday 20:00
    assert st.is_open is False


def test_refresh_returns_changed_flag():
    st = _state()
    assert st.refresh(datetime(2024, 1, 1, 10, 0)) is True  # first call = change
    assert st.refresh(datetime(2024, 1, 1, 11, 0)) is False  # still open, no change
    assert st.refresh(datetime(2024, 1, 1, 20, 0)) is True  # flipped closed


def test_refresh_logs_on_change(caplog):
    st = _state()
    with caplog.at_level(logging.INFO, logger="led_ticker_storefront"):
        st.refresh(datetime(2024, 1, 1, 10, 0))
        st.refresh(datetime(2024, 1, 1, 11, 0))  # no new log
        st.refresh(datetime(2024, 1, 1, 20, 0))
    msgs = [r.message for r in caplog.records]
    assert any("OPEN" in m and "mon 09:00-17:00" in m for m in msgs)
    assert any("CLOSED" in m for m in msgs)
    assert sum(1 for m in msgs if "storefront:" in m) == 2  # only on changes
