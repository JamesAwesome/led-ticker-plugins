import asyncio
import contextlib
import logging
import os

from led_ticker.plugin import HeadlessCanvas

logger = logging.getLogger(__name__)

_ESC = "\x1b"


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
        self.brightness = 100
        self._buffers = [
            HeadlessCanvas(width, height),
            HeadlessCanvas(width, height),
        ]
        self._back = 0
        self._clients: set = set()
        self._server = None
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
        loop.create_task(self._serve())

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

    async def _on_client(self, reader, writer) -> None:
        self._clients.add(writer)
        writer.write(b"\x1b[2J")  # clear the client's screen on connect
        try:
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
        # block swap on a slow client; its TCP send buffer grows and frames drop
        # naturally (constraint: swap() must never block the render loop).
        if self._clients:
            frame = render_ansi(canvas).encode("utf-8", "replace")
            for w in list(self._clients):
                try:
                    if getattr(w, "is_closing", lambda: False)():
                        self._clients.discard(w)
                        continue
                    w.write(frame)
                except Exception:
                    self._clients.discard(w)
        # Flip + return the OTHER buffer so the caller draws into a different
        # object next tick (constraint #8).
        self._back ^= 1
        return self._buffers[self._back]


def render_ansi(canvas) -> str:
    """One pixel row pair per text row: ▀ with fg=top pixel, bg=bottom pixel.
    Reads the backend's own canvas via the public get_pixel (constraint #3 bans
    Canvas GetPixel for the ENGINE, not a backend reading the canvas it made)."""
    out = [f"{_ESC}[H"]  # cursor home — terminal repaints in place each frame
    for y in range(0, canvas.height, 2):
        for x in range(canvas.width):
            tr, tg, tb = canvas.get_pixel(x, y)
            if y + 1 < canvas.height:
                br, bg, bb = canvas.get_pixel(x, y + 1)
            else:
                br, bg, bb = 0, 0, 0
            out.append(f"{_ESC}[38;2;{tr};{tg};{tb}m{_ESC}[48;2;{br};{bg};{bb}m▀")
        out.append(f"{_ESC}[0m\r\n")  # reset attrs + CRLF (telnet line ending)
    return "".join(out)
