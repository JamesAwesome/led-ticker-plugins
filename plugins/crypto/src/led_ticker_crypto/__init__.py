"""led-ticker-crypto: crypto-price widgets for led-ticker (CoinGecko)."""

from led_ticker_crypto.coingecko import CoinGeckoMonitor


def register(api):
    api.widget("coingecko")(CoinGeckoMonitor)
