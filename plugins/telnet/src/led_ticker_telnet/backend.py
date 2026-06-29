import asyncio
import contextlib
import logging
import os

from led_ticker.plugin import HeadlessCanvas

logger = logging.getLogger(__name__)

# Pre-encoded ANSI fragments. render_ansi builds bytes directly (bytearray) so
# the hot path skips the str-join + .encode() double-copy — meaningful on the
# bigsign (256x64) where every swap serializes ~16K cells.
_CURSOR_HOME = b"\x1b[H"  # terminal repaints in place each frame
_HALF_BLOCK = "▀".encode()  # b"\xe2\x96\x80" — Unicode UPPER HALF BLOCK
_RESET_CRLF = b"\x1b[0m\r\n"  # reset attrs + CRLF (telnet line ending)

# Per-client write-buffer cap (bytes). A client that is connected but not
# reading (suspended `nc`, terminal under Ctrl-S/XOFF flow control, congested
# link) is NOT is_closing() and writer.write() never raises — asyncio's
# transport buffers the unread bytes in-process with no high-water cap on this
# path, so the buffer grows without bound (a 256x64 sign at ~20 fps is roughly
# 6 MB/sec of accumulation per stalled client). We read the transport's write
# buffer size each tick and skip the write for a stalled client — that, not the
# write() itself, is what actually drops frames.
_MAX_WRITE_BUFFER = 4 * 1024 * 1024  # 4 MiB ≈ a few frames at 256x64


class TelnetBackend:
    """Renders frames as ANSI color over a telnet/TCP socket. Output device is a
    terminal; the backend owns its transport (like rgbmatrix owns GPIO)."""

    def __init__(
        self,
        width: int = 160,
        height: int = 16,
        *,
        pixel_mapper_config: str = "",
    ) -> None:
        # pixel_mapper_config is accepted (matches HeadlessBackend's constructor
        # shape — build_frame_from_config always passes it as a keyword arg) but
        # intentionally ignored: the telnet backend renders the logical canvas
        # to a terminal; physical-panel chain-folding (U-mapper, etc.) is a
        # hardware-layout concern irrelevant to a terminal preview.
        self.width = width
        self.height = height
        # Required by the Backend protocol; no effect on ANSI output — terminal
        # brightness/contrast applies.
        self.brightness = 100
        self._buffers = [
            HeadlessCanvas(width, height),
            HeadlessCanvas(width, height),
        ]
        self._back = 0
        self._clients: set[asyncio.StreamWriter] = set()
        self._server = None
        # Strong reference to the _serve() startup task. The event loop holds
        # only a WEAK reference to a task, so a fire-and-forget create_task()
        # whose result is discarded can be garbage-collected mid-await — here
        # that would mean _serve() never finishes start_server(), the listener
        # is never created, and NO log line is emitted (silent "never accepts").
        # Keeping the reference closes that GC window.
        self._serve_task = None
        self._host = os.environ.get("LED_TICKER_TELNET_HOST", "0.0.0.0")
        self._port = int(os.environ.get("LED_TICKER_TELNET_PORT", "2300"))

    def setup(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "telnet backend: no running event loop at setup(); server not "
                "started (rendering still works, no clients)"
            )
            return
        self._serve_task = loop.create_task(self._serve())
        self._serve_task.add_done_callback(self._on_serve_done)

    def _on_serve_done(self, task) -> None:
        # Surface a crash in the startup task instead of letting it vanish as a
        # GC-time "exception was never retrieved" warning. Cancellation is
        # expected on shutdown and is not an error.
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("telnet backend: _serve task failed: %s", exc)

    async def _serve(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._on_client, self._host, self._port
            )
        except OSError as e:  # bind failure must NOT freeze the panel (constraint #1)
            logger.warning(
                "telnet backend: could not bind %s:%s — %s", self._host, self._port, e
            )
            return
        logger.info("telnet backend ready — connect: telnet <host> %s", self._port)

    async def _on_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        try:
            writer.write(b"\x1b[2J")  # clear the client's screen on connect
            await reader.read()  # block until the client disconnects
        finally:
            self._clients.discard(writer)
            with contextlib.suppress(Exception):
                writer.close()

    def create_canvas(self) -> HeadlessCanvas:
        return self._buffers[self._back]

    def swap(self, canvas: HeadlessCanvas) -> HeadlessCanvas:
        # `canvas` is the just-drawn back buffer (the "presented" frame).
        # Broadcast to all connected clients WITHOUT await drain — we must never
        # block swap on a slow client (constraint: swap() must never block the
        # render loop). A stalled client's bytes would otherwise accumulate in
        # asyncio's transport write buffer with no cap, so we drop this frame for
        # any client whose buffer is already over _MAX_WRITE_BUFFER.
        #
        # Pre-filter to clients that can actually receive this frame (open AND
        # under the high-water cap) BEFORE rendering — when every client is
        # stalled (or none is connected) we skip building the frame entirely
        # rather than serialize ~16K cells nobody will read.
        writable = []
        for w in list(self._clients):
            # getattr guard: test fakes may omit is_closing.
            if getattr(w, "is_closing", lambda: False)():
                self._clients.discard(w)
                continue
            # getattr guard: test fakes may omit transport.
            transport = getattr(w, "transport", None)
            if (
                transport is not None
                and transport.get_write_buffer_size() > _MAX_WRITE_BUFFER
            ):
                continue  # stalled client — drop this frame, don't pile on
            writable.append(w)
        if writable:
            frame = render_ansi(canvas)
            for w in writable:
                try:
                    w.write(frame)
                except Exception:
                    self._clients.discard(w)
        # Flip + return the OTHER buffer so the caller draws into a different
        # object next tick (constraint #8).
        self._back ^= 1
        return self._buffers[self._back]


def render_ansi(canvas) -> bytes:
    """One pixel row pair per text row: ▀ with fg=top pixel, bg=bottom pixel.
    Reads the backend's own canvas via the public get_pixel (constraint #3 bans
    Canvas GetPixel for the ENGINE, not a backend reading the canvas it made).

    Builds bytes directly into a bytearray so the broadcast hot path avoids the
    str-join + .encode() double-copy (meaningful on the bigsign)."""
    out = bytearray(_CURSOR_HOME)
    for y in range(0, canvas.height, 2):
        for x in range(canvas.width):
            tr, tg, tb = canvas.get_pixel(x, y)
            if y + 1 < canvas.height:
                br, bg, bb = canvas.get_pixel(x, y + 1)
            else:
                br, bg, bb = 0, 0, 0
            out += b"\x1b[38;2;"
            out += f"{tr};{tg};{tb}".encode()
            out += b"m\x1b[48;2;"
            out += f"{br};{bg};{bb}".encode()
            out += b"m"
            out += _HALF_BLOCK
        out += _RESET_CRLF
    return bytes(out)
