import asyncio
import os

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


def test_swap_broadcasts_frame_to_connected_clients():
    b = TelnetBackend(width=2, height=2)

    class FakeWriter:
        def __init__(self):
            self.buf = b""

        def write(self, data):
            self.buf += data

        def is_closing(self):
            return False

    fw = FakeWriter()
    b._clients = {fw}  # simulate a connected client
    c = b.create_canvas()
    c.SetPixel(0, 0, 1, 2, 3)
    b.swap(c)
    assert b"\x1b[H" in fw.buf and b"38;2;1;2;3" in fw.buf


def test_setup_without_running_loop_degrades(caplog):
    b = TelnetBackend()
    b.setup()  # no running loop (sync test) → no crash
    assert b._server is None


def test_swap_skips_closing_clients():
    """A writer that is_closing() should be pruned, not written to."""
    b = TelnetBackend(width=2, height=2)

    class ClosingWriter:
        def __init__(self):
            self.written = False

        def write(self, data):
            self.written = True

        def is_closing(self):
            return True

    cw = ClosingWriter()
    b._clients = {cw}
    c = b.create_canvas()
    b.swap(c)
    assert not cw.written
    assert cw not in b._clients


def test_swap_prunes_writers_that_raise():
    """A writer whose write() raises should be pruned silently."""
    b = TelnetBackend(width=2, height=2)

    class BrokenWriter:
        def write(self, data):
            raise OSError("connection reset")

        def is_closing(self):
            return False

    bw = BrokenWriter()
    b._clients = {bw}
    c = b.create_canvas()
    b.swap(c)  # must not raise
    assert bw not in b._clients


async def test_setup_with_running_loop_spawns_server():
    """setup() inside a running loop creates the server task (no crash)."""
    b = TelnetBackend(width=2, height=2)
    # Use an OS-assigned port to avoid conflict.
    b._port = int(os.environ.get("LED_TICKER_TELNET_PORT_TEST", "0"))
    b._host = "127.0.0.1"
    b.setup()
    # Give the task a chance to run and set _server.
    await asyncio.sleep(0.05)
    # Server may still be None if there's a race; just assert no crash.
    # The server being set is covered by test_serve_binds_and_accepts below.
    if b._server is not None:
        b._server.close()
        await b._server.wait_closed()


async def test_serve_binds_and_accepts():
    """_serve() starts asyncio.start_server and stores it in _server."""
    b = TelnetBackend(width=2, height=2)
    b._host = "127.0.0.1"
    b._port = 0  # OS assigns a free port
    await b._serve()
    assert b._server is not None
    b._server.close()
    await b._server.wait_closed()


async def test_serve_bind_failure_degrades(caplog):
    """_serve() logs and returns (no crash) when the port cannot be bound."""
    b = TelnetBackend(width=2, height=2)
    b._host = "127.0.0.1"
    b._port = 1  # port 1 is privileged — bind will fail unless root
    await b._serve()
    # Either the bind failed (expected in CI) or we're root (very unlikely).
    # Either way, no exception should have propagated.
    if b._server is None:
        assert any("could not bind" in r.message for r in caplog.records)
    else:
        # In the rare root case, clean up.
        b._server.close()
        await b._server.wait_closed()


async def test_on_client_adds_and_removes_writer():
    """_on_client adds a writer on connect, removes it when the reader closes."""
    b = TelnetBackend(width=2, height=2)

    written = []

    class FakeWriter:
        def write(self, data):
            written.append(data)

        def close(self):
            pass

    class FakeReader:
        async def read(self, n=-1):
            return b""  # EOF — disconnect immediately

    fw = FakeWriter()
    fr = FakeReader()

    assert len(b._clients) == 0
    await b._on_client(fr, fw)
    # After coroutine finishes (client disconnected), writer should be pruned.
    assert fw not in b._clients
    # The initial screen-clear should have been sent.
    assert any(b"\x1b[2J" in chunk for chunk in written)


async def test_on_client_close_exception_is_silenced():
    """An exception in writer.close() inside _on_client must not propagate."""
    b = TelnetBackend(width=2, height=2)

    class BadWriter:
        def write(self, data):
            pass

        def close(self):
            raise RuntimeError("close failed")

    class FakeReader:
        async def read(self, n=-1):
            return b""

    await b._on_client(FakeReader(), BadWriter())  # must not raise


# ---------------------------------------------------------------------------
# B4 carry-forward additions
# ---------------------------------------------------------------------------


def test_register_wires_backend_under_telnet_namespace():
    """register(api) must call api.backend("telnet")(TelnetBackend).

    The entry-point name is "telnet" (the plugin namespace); api.backend("telnet")
    then makes the fully-qualified backend id "telnet.telnet".
    """
    from led_ticker_telnet import register

    registered: dict = {}

    class FakeApi:
        def backend(self, name):
            def decorator(cls):
                registered[name] = cls
                return cls

            return decorator

    register(FakeApi())
    assert "telnet" in registered, "api.backend('telnet') was not called"
    assert registered["telnet"] is TelnetBackend


def test_render_ansi_odd_height_bottom_pixel_is_black():
    """On an odd-height canvas the unpaired bottom row uses (0,0,0) as bg.

    render_ansi pairs rows with range(0, height, 2); when height is odd the
    last row has no partner, so the bottom-pixel default is black.
    """
    # 1-wide, 3-tall: rows 0+1 pair normally; row 2 has no row 3 partner.
    c = TelnetBackend(width=1, height=3).create_canvas()
    c.SetPixel(0, 0, 10, 20, 30)  # top of first pair — fg
    c.SetPixel(0, 1, 40, 50, 60)  # bottom of first pair — bg
    c.SetPixel(0, 2, 99, 88, 77)  # lone bottom row — fg; bg must be (0,0,0)

    frame = render_ansi(c)

    # The lone bottom row: fg = (99,88,77), bg must be black (0,0,0).
    assert "38;2;99;88;77" in frame, "lone-row fg color missing"
    assert "48;2;0;0;0" in frame, "lone-row bg should default to black (0,0,0)"
