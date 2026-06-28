from led_ticker.plugin import run_backend_conformance

from led_ticker_telnet.backend import TelnetBackend


def test_telnet_backend_passes_conformance():
    run_backend_conformance(lambda: TelnetBackend(width=64, height=32))


def test_swap_returns_a_different_buffer():
    b = TelnetBackend(width=8, height=8)
    b.setup()
    c0 = b.create_canvas()
    c1 = b.swap(c0)
    assert c1 is not c0
