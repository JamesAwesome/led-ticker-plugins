"""Layout registry + geometry-based resolver.

Phase 1 shipped `crawl` (smallsign) only. Phase 2 Task 4 added `card`
(bigsign, ~256px). Task 5 adds the longboi `dashboard` (~512px).
"""

from led_ticker.plugin import unwrap_to_real

from led_ticker_stocks.layouts.card import draw_card_story
from led_ticker_stocks.layouts.crawl import draw_crawl_story
from led_ticker_stocks.layouts.dashboard import draw_dashboard_story

LAYOUTS = {
    "crawl": draw_crawl_story,
    "card": draw_card_story,
    "dashboard": draw_dashboard_story,
}


def resolve_layout(canvas, override: str | None) -> str:
    """Explicit `override` (a registered name) wins; else pick by PHYSICAL
    canvas width. On bigsign the widget-facing canvas is a `ScaledCanvas`
    whose `.width` is the small LOGICAL width (`real.width // scale`, e.g.
    64 for a 256-px-wide panel at scale=4) — using it directly would always
    resolve to `crawl`. Unwrap to the real canvas first so the threshold
    reads the actual panel width (plain/mock canvases pass through
    `unwrap_to_real` unchanged).
    """
    if override is not None:
        if override not in LAYOUTS:
            raise ValueError(
                f"stocks.ticker: unknown layout {override!r} "
                f"(registered: {sorted(LAYOUTS)})"
            )
        return override
    width = getattr(unwrap_to_real(canvas), "width", 0)
    if width <= 160:
        return "crawl"
    if width >= 400:
        return "dashboard"  # longboi ~512 (real)
    return "card"  # ~256 bigsign
