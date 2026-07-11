"""Package-level smoke: the entry point target imports and is callable."""

from led_ticker_flight import register


def test_register_is_callable():
    assert callable(register)
