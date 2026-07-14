"""StocksTicker Container (stocks.ticker) + per-symbol crawl story."""

import logging
import os
from typing import Any, Self

import attrs
from led_ticker.plugin import (
    Canvas,
    DrawResult,
    FrameAwareBase,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_stocks.demo import DemoFeed
from led_ticker_stocks.finnhub import FinnhubClient, parse_quote
from led_ticker_stocks.layouts import LAYOUTS, resolve_layout
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState, state_from_status


@attrs.define
class _StockStory(FrameAwareBase):
    """One symbol's crawl segment — reads the shared, live-mutated quote dict."""

    sym: str
    quotes: dict[str, SymbolQuote]
    state_ref: list[MarketState]  # 1-item list holding the live MarketState
    layout: str | None
    green_up: bool = True
    padding: int = 6
    _resolved: str | None = attrs.field(init=False, default=None)

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
        renderer = LAYOUTS[self._resolved]
        quote = self.quotes[self.sym]
        end = renderer(
            canvas,
            quote,
            self.state_ref[0],
            cursor_pos,
            frame=self.frame_for("crawl"),
            y_offset=y_offset,
            end_padding=self.padding,
        )
        return canvas, end


@attrs.define
class StocksTicker:
    """Equity price Container cycling one `_StockStory` per symbol (Finnhub)."""

    symbols: list[str]
    session: object
    token: str = ""
    demo: bool = False
    layout: str | None = None
    green_up: bool = True
    padding: int = 6
    update_interval: int = 60
    feed_title: None = attrs.field(init=False, default=None)
    feed_stories: list[_StockStory] = attrs.field(init=False, factory=list)
    _quotes: dict[str, SymbolQuote] = attrs.field(init=False, factory=dict)
    _state_ref: list[MarketState] = attrs.field(
        init=False, factory=lambda: [MarketState.CLOSED]
    )
    _client: FinnhubClient | None = attrs.field(init=False, default=None)
    _demo_feed: DemoFeed | None = attrs.field(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        if self.demo or not self.token:
            self._demo_feed = DemoFeed(self.symbols)
            self._quotes = self._demo_feed.quotes
            self._state_ref[0] = MarketState.OPEN
        else:
            self._client = FinnhubClient(self.token, self.session)
            self._quotes = {s: parse_quote(s, {"c": 0, "pc": 0}) for s in self.symbols}
        self.feed_stories = [
            _StockStory(
                sym=s,
                quotes=self._quotes,
                state_ref=self._state_ref,
                layout=self.layout,
                green_up=self.green_up,
                padding=self.padding,
            )
            for s in self.symbols
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
        for s in symbols:
            if "/" in s:
                msgs.append(
                    f"stocks.ticker: {s!r} looks like forex — FX requires a paid "
                    "Finnhub tier (v1 is equities only)"
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
        padding: int = 6,
        demo: bool = False,
        update_interval: int = 60,
        token: str | None = None,
        **kwargs: Any,
    ) -> Self:
        # `token` may be injected explicitly (tests, alternate call sites);
        # otherwise resolved from the env — never from config (secrets
        # convention, see CLAUDE.md "Secrets belong in .env, not config.toml").
        resolved_token = token if token else os.getenv("FINNHUB_API_TOKEN", "")
        # Rate discipline: N quote calls + 1 status call must stay under 60/min.
        effective = max(update_interval, len(symbols) + 1)
        widget = cls(
            symbols=list(symbols),
            session=session,
            token=resolved_token,
            demo=demo,
            layout=layout,
            green_up=green_up,
            padding=padding,
            update_interval=effective,
        )
        # Tolerate a failed INITIAL fetch (e.g. a rate-limited or unreachable
        # Finnhub at boot) so the widget still constructs and the monitor
        # loop can recover, rather than the whole widget being skipped for
        # the session.
        try:
            await widget.update()
        except Exception as e:
            logging.warning(
                "stocks.ticker initial fetch failed (%s); "
                "starting with placeholders, will retry",
                e,
            )
        spawn_tracked(run_monitor_loop(widget, widget.update_interval))
        return widget

    async def update(self) -> None:
        if self._demo_feed is not None:
            for _ in range(len(self.symbols)):
                self._demo_feed.step()
            self._state_ref[0] = MarketState.OPEN
            logging.info("stocks.ticker demo tick: %d symbols", len(self.symbols))
            return

        # Live mode: __attrs_post_init__ always sets _client when _demo_feed
        # is None, so this narrows _client for the type checker without a
        # suppression.
        assert self._client is not None, "stocks.ticker: live mode requires a client"

        status = await self._client.fetch_market_status()
        self._state_ref[0] = state_from_status(status)
        if self._state_ref[0] is MarketState.CLOSED:
            logging.info("stocks.ticker: market closed — holding last prices")
            return  # frozen when closed (no quote calls)

        updated = 0
        for sym in self.symbols:
            payload = await self._client.fetch_quote(sym)
            fresh = parse_quote(sym, payload)
            existing = self._quotes[sym]
            existing.price, existing.prev = fresh.price, fresh.prev
            existing.d, existing.dp = fresh.d, fresh.dp
            if fresh.has_data:
                existing.spark.append(fresh.price)
            updated += 1
        logging.info("stocks.ticker updated: %d/%d symbols", updated, len(self.symbols))
