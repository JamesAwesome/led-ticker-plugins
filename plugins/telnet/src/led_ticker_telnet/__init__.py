"""led-ticker-telnet: a telnet/ANSI terminal rendering backend, contributed via
the ``led_ticker.plugins`` entry point. Registers as ``telnet.telnet``; select
with ``[display] backend = "telnet.telnet"``."""

from led_ticker_telnet.backend import TelnetBackend


def register(api):
    api.backend("telnet")(TelnetBackend)
