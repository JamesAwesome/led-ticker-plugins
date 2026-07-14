"""Layout registry + geometry-based resolver. Phase 1 registers `crawl` only."""

from led_ticker_stocks.layouts.crawl import draw_crawl_story

LAYOUTS = {"crawl": draw_crawl_story}


def resolve_layout(canvas, override: str | None) -> str:
    """Explicit `override` (a registered name) wins; else pick by canvas width.

    Phase 1 only ships `crawl` (smallsign). card/dashboard arrive in Phase 2.
    """
    if override is not None:
        if override not in LAYOUTS:
            raise ValueError(
                f"stocks.ticker: unknown layout {override!r} "
                f"(registered: {sorted(LAYOUTS)}; card/dashboard land in Phase 2)"
            )
        return override
    if getattr(canvas, "width", 0) <= 160:
        return "crawl"
    raise NotImplementedError(
        "stocks.ticker: only the smallsign crawl ships in Phase 1; "
        "bigsign card / longboi dashboard arrive in Phase 2"
    )
