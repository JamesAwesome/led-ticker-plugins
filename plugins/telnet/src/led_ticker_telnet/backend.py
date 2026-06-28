import logging

from led_ticker.plugin import HeadlessCanvas

logger = logging.getLogger(__name__)


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
