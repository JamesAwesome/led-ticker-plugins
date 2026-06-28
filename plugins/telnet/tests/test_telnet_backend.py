from led_ticker.plugin import run_backend_conformance

from led_ticker_telnet.backend import TelnetBackend, render_ansi


def test_telnet_backend_passes_conformance():
    run_backend_conformance(lambda: TelnetBackend(width=64, height=32))


def test_swap_returns_a_different_buffer():
    b = TelnetBackend(width=8, height=8)
    b.setup()
    c0 = b.create_canvas()
    c1 = b.swap(c0)
    assert c1 is not c0


def test_render_ansi_encodes_top_and_bottom_pixel_colors():
    c = TelnetBackend(width=1, height=2).create_canvas()
    c.SetPixel(0, 0, 255, 0, 0)  # top → foreground
    c.SetPixel(0, 1, 0, 0, 255)  # bottom → background
    frame = render_ansi(c)
    assert frame.startswith("\x1b[H")  # cursor home
    assert "38;2;255;0;0" in frame  # fg = top pixel
    assert "48;2;0;0;255" in frame  # bg = bottom pixel
    assert "▀" in frame  # ▀ upper half block
