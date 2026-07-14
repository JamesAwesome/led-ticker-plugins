"""led-ticker-stocks: equity ticker widget for led-ticker (Finnhub)."""

from led_ticker_stocks.ticker import StocksTicker


def register(api):
    api.widget("ticker")(StocksTicker)
