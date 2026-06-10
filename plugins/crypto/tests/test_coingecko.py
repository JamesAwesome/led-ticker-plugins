"""Tests for led_ticker_crypto (coingecko widget + shared renderer)."""

import unittest.mock as mock

import pytest

from led_ticker.plugin import Widget

from led_ticker_crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)
from led_ticker_crypto._ticker_render import (
    FONT_VALUE,
    FONT_VALUE_SMALL,
    _get_change_color,
    _get_price_font,
    draw_price_ticker,
)
from led_ticker_crypto.coingecko import (
    CoinGeckoPriceMonitor,
    _find_coingecko_symbol_id,
)


class TestRenderHelpers:
    def test_change_color_positive(self):
        assert _get_change_color("2.55%") == UP_TREND_COLOR

    def test_change_color_negative(self):
        assert _get_change_color("-1.23%") == DOWN_TREND_COLOR

    def test_change_color_zero_is_neutral(self):
        assert _get_change_color("0.00%") == NEUTRAL_TREND_COLOR
        assert _get_change_color("0%") == NEUTRAL_TREND_COLOR

    def test_change_color_unparseable_is_neutral(self):
        assert _get_change_color("N/A") == NEUTRAL_TREND_COLOR
        assert _get_change_color("") == NEUTRAL_TREND_COLOR

    def test_price_font_short(self):
        assert _get_price_font("1234.5678") == FONT_VALUE

    def test_price_font_long(self):
        assert _get_price_font("12345678.90") == FONT_VALUE_SMALL


class TestDrawPriceTicker:
    def test_returns_canvas(self, canvas):
        result, pos = draw_price_ticker(canvas, "BTC", "50000.00", "2.55%")
        assert result is canvas
        assert pos > 0

    def test_centered_fills_canvas(self, canvas):
        _, pos = draw_price_ticker(canvas, "BTC", "50000.00", "2.55%", center=True)
        assert pos == 160


class TestCoinGeckoPriceMonitor:
    @pytest.fixture
    def monitor(self):
        m = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=mock.Mock()
        )
        m.price_data = {"price": "3,000.0000", "change_24h": "1.50%"}
        return m

    def test_conforms_to_widget_protocol(self, monitor):
        assert isinstance(monitor, Widget)

    def test_draw_returns_canvas(self, canvas, monitor):
        result, pos = monitor.draw(canvas)
        assert result is canvas
        assert pos > 0

    def test_find_symbol_id(self):
        coin_list = [
            {"id": "ethereum", "symbol": "eth"},
            {"id": "dogecoin", "symbol": "doge"},
        ]
        assert _find_coingecko_symbol_id(coin_list, "ETH") == "ethereum"
        assert _find_coingecko_symbol_id(coin_list, "BTC") is None

    def test_bg_color_default_is_none(self):
        w = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=mock.Mock()
        )
        assert w.bg_color is None

    def test_accepts_bg_color(self):
        from led_ticker.plugin import make_color

        w = CoinGeckoPriceMonitor(
            symbol="ETH",
            symbol_id="ethereum",
            currency="USD",
            session=mock.Mock(),
            bg_color=make_color(10, 20, 30),
        )
        assert w.bg_color is not None

    async def test_update_parses_price(self):
        session = mock.Mock()
        resp = mock.AsyncMock()
        resp.json = mock.AsyncMock(
            return_value={"ethereum": {"usd": 3000.5, "usd_24h_change": 1.5}}
        )
        ctx = mock.AsyncMock()
        ctx.__aenter__ = mock.AsyncMock(return_value=resp)
        ctx.__aexit__ = mock.AsyncMock(return_value=False)
        session.get = mock.Mock(return_value=ctx)

        w = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=session
        )
        await w.update()
        assert w.price_data["price"] == "3,000.5000"
        assert w.price_data["change_24h"] == "1.50%"
