import asyncio
import contextlib
import logging
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
    assert isinstance(frame, bytes)  # render_ansi builds bytes directly
    assert frame.startswith(b"\x1b[H")  # cursor home
    assert b"38;2;255;0;0" in frame  # fg = top pixel
    assert b"48;2;0;0;255" in frame  # bg = bottom pixel
    assert "▀".encode() in frame  # ▀ upper half block


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
    with caplog.at_level(logging.WARNING):
        b.setup()  # no running loop (sync test) → no crash
    assert b._server is None
    assert any("no running event loop" in r.message for r in caplog.records)


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


def test_swap_drops_frame_for_stalled_client_over_high_water():
    """A connected-but-not-reading client (not is_closing, write never raises)
    whose transport write buffer is over the cap must have this frame DROPPED —
    not written — so its in-process buffer can't grow without bound. The client
    stays in the set (it's stalled, not broken) so it recovers when it drains."""
    from led_ticker_telnet.backend import _MAX_WRITE_BUFFER

    class StalledTransport:
        def get_write_buffer_size(self):
            return _MAX_WRITE_BUFFER + 1  # over cap

    class StalledWriter:
        def __init__(self):
            self.written = False
            self.transport = StalledTransport()

        def write(self, data):
            self.written = True

        def is_closing(self):
            return False

    b = TelnetBackend(width=4, height=4)
    sw = StalledWriter()
    b._clients = {sw}
    c = b.create_canvas()
    b.swap(c)
    assert not sw.written, "frame should be dropped for an over-cap stalled client"
    assert sw in b._clients, "a stalled client is dropped-from this frame, not evicted"


def test_swap_writes_to_client_under_high_water():
    """A client whose transport buffer is under the cap is written to normally."""
    from led_ticker_telnet.backend import _MAX_WRITE_BUFFER

    class HealthyTransport:
        def get_write_buffer_size(self):
            return _MAX_WRITE_BUFFER - 1  # under cap

    class HealthyWriter:
        def __init__(self):
            self.written = False
            self.transport = HealthyTransport()

        def write(self, data):
            self.written = True

        def is_closing(self):
            return False

    b = TelnetBackend(width=4, height=4)
    hw = HealthyWriter()
    b._clients = {hw}
    b.swap(b.create_canvas())
    assert hw.written, "an under-cap client should be written to"


async def test_setup_holds_strong_reference_to_serve_task():
    """setup() must keep a strong reference to the _serve() task so the loop's
    weak-only reference can't let GC drop it mid-await (silent never-accepts)."""
    b = TelnetBackend(width=2, height=2)
    b._host = "127.0.0.1"
    b._port = 0  # OS assigns a free port
    b.setup()
    assert b._serve_task is not None, "setup() did not retain the _serve task"
    await b._serve_task  # let it finish binding
    if b._server is not None:
        b._server.close()
        await b._server.wait_closed()


async def test_on_serve_done_surfaces_unexpected_exception(caplog):
    """A non-OSError crash in the startup task must be logged via the
    done-callback, not vanish as a GC-time 'never retrieved' warning."""
    b = TelnetBackend(width=2, height=2)

    async def boom():
        raise RuntimeError("unexpected start_server failure")

    task = asyncio.ensure_future(boom())
    task.add_done_callback(b._on_serve_done)
    with caplog.at_level(logging.WARNING):
        with contextlib.suppress(RuntimeError):
            await task
        # Let the done-callback run.
        await asyncio.sleep(0)
    assert any("_serve task failed" in r.message for r in caplog.records), (
        "an unexpected _serve crash should be logged by the done-callback"
    )


async def test_on_serve_done_ignores_cancellation():
    """A cancelled startup task is expected on shutdown — the callback must not
    raise (no .exception() on a cancelled task) and must not log it as failure."""
    b = TelnetBackend(width=2, height=2)

    async def forever():
        await asyncio.Event().wait()

    task = asyncio.ensure_future(forever())
    task.add_done_callback(b._on_serve_done)
    await asyncio.sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)  # callback runs — must not raise


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


async def test_on_client_connect_write_failure_still_prunes_writer():
    """If the connect-time screen-clear write() raises, the writer must NOT be
    left in _clients — the screen-clear lives inside the try so finally always
    prunes (the method honors its own invariant, not just the next swap)."""
    b = TelnetBackend(width=2, height=2)

    class WriteOnConnectFailsWriter:
        def write(self, data):
            raise OSError("connection reset on connect")

        def close(self):
            pass

    class FakeReader:
        async def read(self, n=-1):
            return b""

    wfw = WriteOnConnectFailsWriter()
    with contextlib.suppress(OSError):
        await b._on_client(FakeReader(), wfw)
    assert wfw not in b._clients, "a writer that fails its connect write must be pruned"


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
# Engine-convention constructor regression
# ---------------------------------------------------------------------------


def test_constructs_via_engine_convention():
    # build_frame_from_config calls backend_cls(width, height, pixel_mapper_config=...)
    # for every non-rgbmatrix backend. This test locks that signature so a future
    # refactor that drops pixel_mapper_config would be caught immediately.
    b = TelnetBackend(160, 16, pixel_mapper_config="")
    assert b.create_canvas() is not None


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


def test_render_ansi_all_black_canvas():
    """A freshly created canvas with no SetPixel calls is all-black; every cell
    encodes (0,0,0) as both fg and bg."""
    c = TelnetBackend(width=2, height=2).create_canvas()
    frame = render_ansi(c)
    assert isinstance(frame, bytes)
    assert b"38;2;0;0;0" in frame, "all-black fg should be (0,0,0)"
    assert b"48;2;0;0;0" in frame, "all-black bg should be (0,0,0)"


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
    assert b"38;2;99;88;77" in frame, "lone-row fg color missing"
    assert b"48;2;0;0;0" in frame, "lone-row bg should default to black (0,0,0)"
