"""Hi-res held scoreboard (scale>1). PLACEHOLDER until the scoreboard task
lands: it paints the crawl line held at the left edge so the card has
something to show. The signature is final; only the body changes.
"""

from led_ticker_hockey._models import GameInfo
from led_ticker_hockey.layouts.crawl import render_crawl


def render_scoreboard(
    canvas,
    game: GameInfo,
    now: float,
    tz,
    *,
    y_offset: int = 0,
    stale: bool = False,
    highlight: tuple[str, float] | None = None,
) -> None:
    render_crawl(canvas, game, now, tz, 0, y_offset=y_offset)
