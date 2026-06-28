import logging

from led_ticker.plugin import HeadlessCanvas

logger = logging.getLogger(__name__)

_ESC = "\x1b"


class TelnetBackend:
    """Renders frames as ANSI color over a telnet/TCP socket. Output device is a
    terminal; the backend owns its transport (like rgbmatrix owns GPIO)."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self.brightness = 100
        self._buffers = [
            HeadlessCanvas(width, height),
            HeadlessCanvas(width, height),
        ]
        self._back = 0

    def setup(self) -> None:
        # Network added in Task B3.
        pass

    def create_canvas(self) -> HeadlessCanvas:
        return self._buffers[self._back]

    def swap(self, canvas: HeadlessCanvas) -> HeadlessCanvas:
        # `canvas` is the just-drawn back buffer (the "presented" frame).
        # Frame broadcast is added in B3. Flip + return the OTHER buffer so the
        # caller draws into a different object next tick (constraint #8).
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
