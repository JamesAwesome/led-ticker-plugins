"""StocksTicker Container (stocks.ticker) + per-symbol crawl story."""

import logging
from typing import Any, Self

import attrs
from led_ticker.plugin import (
    Canvas,
    DrawResult,
    FrameAwareBase,
)

from led_ticker_stocks._cache import QuoteCache, get_cache
from led_ticker_stocks.layouts import LAYOUTS, resolve_layout
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.source import _PROVIDERS

# Soft cap on configured symbols: each poll cycle costs len(symbols) + 1
# Finnhub requests, and the free tier is 60 req/min per token. Above this,
# a short update_interval risks the per-token budget (see the rate rule in
# CLAUDE.md); start() logs one warning rather than enforcing a hard limit.
SYMBOL_SOFT_CAP = 20


@attrs.define
class _StockStory(FrameAwareBase):
    """One symbol's crawl segment — reads the shared, live `QuoteCache`."""

    sym: str
    layout: str | None
    green_up: bool = True
    dim_by_state: bool = True
    padding: int = 6
    focus_index: int = 0
    all_symbols: list[str] = attrs.field(factory=list)
    _resolved: str | None = attrs.field(init=False, default=None)

    @staticmethod
    def _quote_for(cache: QuoteCache, sym: str) -> SymbolQuote:
        """Live cache lookup, falling back to a fresh zeroed placeholder.

        `QuoteCache.register()` always seeds a zeroed quote, so a `None`
        here only happens for a symbol nobody has registered yet — the
        layouts already render a zeroed/no-data quote correctly (via
        `SymbolQuote.has_data`), so a fresh placeholder is enough; there is
        nothing here to persist. Takes the already-bound `cache` rather
        than calling `get_cache()` itself, so a held-layout draw (which
        looks up every watch-column symbol) hits the singleton lookup once
        per `draw()` instead of once per symbol.
        """
        quote = cache.get(sym)
        return quote if quote is not None else SymbolQuote(sym=sym, price=0.0, prev=0.0)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if self._resolved is None:
            self._resolved = resolve_layout(canvas, self.layout)
        cache = get_cache()
        quote = self._quote_for(cache, self.sym)
        state = quote.state
        if self._resolved == "crawl":
            end = LAYOUTS["crawl"](
                canvas,
                quote,
                state,
                cursor_pos,
                frame=self.frame_for("crawl"),
                y_offset=y_offset,
                end_padding=self.padding,
                green_up=self.green_up,
                dim_by_state=self.dim_by_state,
            )
            return canvas, end
        # Held layouts (card/dashboard) paint in place; return a stable
        # cursor (canvas width) rather than a scroll position. `quotes`
        # feeds the dashboard's watch-column neighbor lookups.
        quotes = {s: self._quote_for(cache, s) for s in self.all_symbols}
        LAYOUTS[self._resolved](
            canvas,
            quote,
            state,
            quotes,
            self.all_symbols,
            focus_index=self.focus_index,
            total=len(self.all_symbols),
            frame=self.frame_for("held"),
            green_up=self.green_up,
            dim_by_state=self.dim_by_state,
            y_offset=y_offset,
        )
        return canvas, getattr(canvas, "width", 0)


@attrs.define
class StocksTicker:
    """Equity price Container cycling one `_StockStory` per symbol.

    Owns no data itself: `start()` registers its symbols with the shared
    `QuoteCache` (`_cache.py`) and ensures the cache's single poll loop is
    running. Every story reads live off the cache on each `draw()` — there
    is no widget-owned poll loop or `update()` anymore.
    """

    symbols: list[str]
    layout: str | None = None
    green_up: bool = True
    # State-based brightness (LIVE 100% / PRE·AH 85% / CLOSED 70%) is the
    # default; dim_by_state = false renders every card at full brightness
    # while the state CHIP keeps carrying the LIVE/CLSD information. With
    # per-symbol state (multi-asset), mixed open/closed rotations otherwise
    # alternate bright/dim — informative, but at storefront distance some
    # prefer uniform brightness.
    dim_by_state: bool = True
    padding: int = 6
    update_interval: int = 60
    # Accepted-but-IGNORED: exists only so a v0.3.0 config with
    # `token = "..."` still validates (core allowlists a widget's config
    # keys from `start()` params ∪ attrs-init fields). The value is never
    # read here or forwarded anywhere — the Finnhub token comes from env
    # ONLY, resolved inside the shared `QuoteCache` (see CLAUDE.md
    # "Secrets belong in .env, not config.toml"). A config-supplied
    # `token` flows into `self.token` and dead-ends there. Keep the
    # token-leak regression tests (`test_config_token_is_ignored*`) green
    # if you touch this.
    token: str = attrs.field(default="", kw_only=True)
    # Unlike `token`, `demo` IS wired: `start()` forwards it to
    # `QuoteCache.ensure_started(force_demo=...)`. See that docstring for
    # the shared-cache "first widget to start wins" semantics.
    demo: bool = attrs.field(default=False, kw_only=True)
    # Which quote provider the shared cache uses for THIS widget's symbols
    # (forwarded to `QuoteCache.ensure_started`; see the shared-cache
    # single-mode caveat there — first `start()` to run wins for the whole
    # process). "twelvedata" is required for forex/crypto symbols (a `/`),
    # which "finnhub" (the default) rejects at validate time.
    provider: str = attrs.field(default="finnhub", kw_only=True)
    feed_title: None = attrs.field(init=False, default=None)
    feed_stories: list[_StockStory] = attrs.field(init=False, factory=list)

    def __attrs_post_init__(self) -> None:
        self.feed_stories = [
            _StockStory(
                sym=s,
                layout=self.layout,
                green_up=self.green_up,
                dim_by_state=self.dim_by_state,
                padding=self.padding,
                focus_index=i,
                all_symbols=self.symbols,
            )
            for i, s in enumerate(self.symbols)
        ]

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any
        returned messages into a pre-flight ValueError.
        """
        msgs: list[str] = []
        symbols = cfg.get("symbols")
        if not (
            isinstance(symbols, list)
            and symbols
            and all(isinstance(s, str) and s for s in symbols)
        ):
            msgs.append("stocks.ticker: symbols must be a non-empty list of strings")
            return msgs
        provider = cfg.get("provider", "finnhub")
        if provider not in _PROVIDERS:
            msgs.append(
                f"stocks.ticker: unknown provider {provider!r} "
                f"(known: {', '.join(_PROVIDERS)})"
            )
        if provider == "finnhub":
            for s in symbols:
                if "/" in s:
                    msgs.append(
                        f"stocks.ticker: {s!r} looks like forex — FX requires a paid "
                        'Finnhub tier. Use provider = "twelvedata" for forex/crypto'
                    )
        layout = cfg.get("layout")
        if layout is not None and layout not in LAYOUTS:
            msgs.append(
                f"stocks.ticker: unknown layout {layout!r} "
                f"(registered: {sorted(LAYOUTS)})"
            )
        return msgs

    @classmethod
    async def start(
        cls,
        *,
        symbols: list[str],
        session: object,
        layout: str | None = None,
        green_up: bool = True,
        dim_by_state: bool = True,
        padding: int = 6,
        update_interval: int = 60,
        demo: bool = False,
        provider: str = "finnhub",
        **kwargs: Any,
    ) -> Self:
        # `token` is deliberately NOT a `start()` parameter (unlike `demo`,
        # which needs active wiring below): core's widget factory unions
        # `start()`'s signature into the allowed config keys, and `token`
        # is already an accepted attrs field on the class (see the field
        # comment), so it still validates and flows through **kwargs into
        # `cls(...)` — bound to `widget.token` and never read again. The
        # Finnhub token comes from env ONLY, resolved inside the shared
        # `QuoteCache` (see CLAUDE.md "Secrets belong in .env, not
        # config.toml").
        if len(symbols) > SYMBOL_SOFT_CAP:
            logging.warning(
                "stocks.ticker: %d symbols configured (soft cap %d) — Finnhub's "
                "free tier is 60 req/min per token; cadence is bounded by "
                "max(update_interval, len(symbols) + 1) so a large symbol list "
                "may exceed the per-token budget",
                len(symbols),
                SYMBOL_SOFT_CAP,
            )
        valid = {f.name for f in attrs.fields(cls)}
        widget = cls(
            symbols=list(symbols),
            layout=layout,
            green_up=green_up,
            dim_by_state=dim_by_state,
            padding=padding,
            update_interval=update_interval,
            demo=demo,
            provider=provider,
            **{k: v for k, v in kwargs.items() if k in valid},
        )
        get_cache().register(widget.symbols)
        # `force_demo`: the shared cache is single-mode, so `demo = true`
        # on THIS widget forces the whole cache into demo mode even if a
        # live token is present — but only if this is the widget that wins
        # the "first to call ensure_started" race (see that docstring).
        await get_cache().ensure_started(
            session, interval=update_interval, force_demo=demo, provider=provider
        )
        return widget
