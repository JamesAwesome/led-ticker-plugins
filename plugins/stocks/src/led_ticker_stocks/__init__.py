"""led-ticker-stocks: equity ticker widget for led-ticker (Finnhub)."""

from led_ticker_stocks.source import StockSource
from led_ticker_stocks.ticker import StocksTicker
from led_ticker_stocks.trend_color import StocksTrendColor


def register(api):
    api.widget("ticker")(StocksTicker)
    api.source("quote")(StockSource)
    api.color_provider("trend")(StocksTrendColor)
