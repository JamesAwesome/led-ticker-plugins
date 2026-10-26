"""Physical (scale>1) held scoreboard — PLACEHOLDER until Task 7: paints the
crawl's wording held at cursor 0 so the card lights the panel."""

from led_ticker_football._models import GameInfo
from led_ticker_football.layouts.crawl import render_crawl


def render_scoreboard(
    canvas,
    game: GameInfo,
    now: float,
    tz,
    *,
    y_offset: int = 0,
    stale: bool = False,
    highlight: tuple[str, float] | None = None,
    bye: bool = False,
) -> None:
    render_crawl(canvas, game, now, tz, 0, y_offset=y_offset, stale=stale, bye=bye)
