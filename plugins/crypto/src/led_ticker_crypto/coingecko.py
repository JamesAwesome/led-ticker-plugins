"""CoinGecko price monitor widget (crypto.coingecko).

`CoinGeckoMonitor` is a Container: it cycles one `_CoinTicker` "story" per
configured coin (each reusing the pixel-validated `draw_price_ticker`). The
container does ONE batched `/simple/price` fetch per update and routes each
coin's price into its story. Symbols can be auto-resolved to CoinGecko ids
(unique-or-error), and an optional demo API key raises the free-tier limit.
"""

import logging
import os
from typing import Any, Self

import aiohttp
import attrs
from led_ticker.plugin import (
    Canvas,
    Color,
    ColorProvider,
    DrawResult,
    FrameAwareBase,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_crypto._ticker_render import (
    _ConstantColor,
    _format_price,
    draw_price_ticker,
    make_default_font_color,
)

COINGECKO_API: str = "https://api.coingecko.com/api/v3"
COINGECKO_COIN_LIST: str = f"{COINGECKO_API}/coins/list"
COINGECKO_PRICE_API: str = f"{COINGECKO_API}/simple/price"


@attrs.define
class _CoinTicker(FrameAwareBase):
    """One coin's price line — a Container "story" drawn via draw_price_ticker."""

    symbol: str
    center: bool = True
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider = attrs.field(default=None, kw_only=True)
    price_data: dict[str, str] = attrs.field(
        init=False,
        factory=lambda: {"price": "0.0000", "change_24h": "0.00%"},
    )

    def __attrs_post_init__(self) -> None:
        if self.font_color is None:
            self.font_color = make_default_font_color()
        elif not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        return draw_price_ticker(
            canvas,
            self.symbol,
            self.price_data["price"],
            self.price_data["change_24h"],
            cursor_pos=cursor_pos,
            center=self.center,
            padding=self.padding,
            end_padding=self.padding,
            y_offset=y_offset,
            font_color=self.font_color,
            frame_count=self.frame_for("font_color"),
        )


def _resolve_symbols(
    symbols: list[str], coin_list: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    """Resolve display symbols to CoinGecko ids (unique-or-error).

    For each symbol (case-insensitive on `coin_meta["symbol"]`):
    exactly one match → `(symbol.upper(), id)`; zero → ValueError;
    multiple → ValueError listing all candidate ids and telling the user
    to set `symbol_id`/`symbol_ids` explicitly. Input order preserved.
    """
    resolved: list[tuple[str, str]] = []
    for symbol in symbols:
        matches = [
            coin_meta["id"]
            for coin_meta in coin_list
            if coin_meta["symbol"].lower() == symbol.lower()
        ]
        if len(matches) == 1:
            resolved.append((symbol.upper(), matches[0]))
        elif not matches:
            raise ValueError(f"symbol {symbol!r} not found on CoinGecko")
        else:
            candidates = ", ".join(matches)
            raise ValueError(
                f"symbol {symbol!r} is ambiguous on CoinGecko "
                f"(candidate ids: {candidates}); set symbol_id or symbol_ids "
                f"explicitly to disambiguate"
            )
    return resolved


def _build_coins(
    symbol: str | None,
    symbol_id: str | None,
    symbols: list[str] | None,
    symbol_ids: list[str] | None,
    coin_list: list[dict[str, Any]] | None,
) -> list[tuple[str, str]]:
    """Assemble an ordered, de-duplicated `(display_symbol, coin_id)` list.

    Order: legacy `symbol`+`symbol_id` → each `symbol_ids` entry →
    `symbols` (auto-resolved). De-duplicate by coin_id (keep first).
    Raise if the result is empty.
    """
    coins: list[tuple[str, str]] = []
    if symbol and symbol_id:
        coins.append((symbol.upper(), symbol_id))
    for cid in symbol_ids or []:
        coins.append((cid.upper(), cid))
    if symbols:
        coins.extend(_resolve_symbols(symbols, coin_list or []))

    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for display, cid in coins:
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append((display, cid))

    if not deduped:
        raise ValueError(
            "crypto.coingecko: specify at least one of symbol/symbol_id, "
            "symbol_ids, or symbols"
        )
    return deduped


@attrs.define
class CoinGeckoMonitor:
    """Crypto price Container cycling one _CoinTicker per coin (CoinGecko API)."""

    coins: list[tuple[str, str]]
    currency: str
    session: aiohttp.ClientSession
    center: bool = True
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider = attrs.field(default=None, kw_only=True)
    api_key: str = attrs.field(
        factory=lambda: os.getenv("COINGECKO_API_KEY", ""), kw_only=True
    )
    feed_title: None = attrs.field(init=False, default=None)
    feed_stories: list[_CoinTicker] = attrs.field(init=False, factory=list)
    _story_by_id: dict = attrs.field(init=False, factory=dict)

    def __attrs_post_init__(self) -> None:
        self.feed_stories = [
            _CoinTicker(
                symbol=display,
                center=self.center,
                padding=self.padding,
                hold_time=self.hold_time,
                bg_color=self.bg_color,
                font_color=self.font_color,
            )
            for display, _ in self.coins
        ]
        self._story_by_id = {
            cid: story
            for (_, cid), story in zip(self.coins, self.feed_stories, strict=True)
        }

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any returned
        messages into a pre-flight ValueError.
        """
        msgs: list[str] = []

        has_legacy = bool(cfg.get("symbol") or cfg.get("symbol_id"))
        has_symbols = bool(cfg.get("symbols"))
        has_symbol_ids = bool(cfg.get("symbol_ids"))

        if not (has_legacy or has_symbols or has_symbol_ids):
            msgs.append(
                "crypto.coingecko: specify at least one coin via "
                "symbol+symbol_id, symbol_ids, or symbols"
            )
            return msgs

        if has_symbols:
            symbols = cfg["symbols"]
            if not (
                isinstance(symbols, list)
                and all(isinstance(s, str) and s for s in symbols)
            ):
                msgs.append(
                    "crypto.coingecko: symbols must be a non-empty list of strings"
                )

        if has_symbol_ids:
            symbol_ids = cfg["symbol_ids"]
            if not (
                isinstance(symbol_ids, list)
                and all(isinstance(s, str) and s for s in symbol_ids)
            ):
                msgs.append(
                    "crypto.coingecko: symbol_ids must be a non-empty list of strings"
                )

        return msgs

    def _headers(self) -> dict[str, str]:
        return {"x-cg-demo-api-key": self.api_key} if self.api_key else {}

    @classmethod
    async def start(
        cls,
        *,
        currency: str = "USD",
        symbol: str | None = None,
        symbol_id: str | None = None,
        symbols: list[str] | None = None,
        symbol_ids: list[str] | None = None,
        session: aiohttp.ClientSession,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        api_key = kwargs.get("api_key") or os.getenv("COINGECKO_API_KEY", "")
        headers = {"x-cg-demo-api-key": api_key} if api_key else {}
        coin_list = (
            await _get_coingecko_coin_list(session, headers=headers)
            if symbols
            else None
        )
        coins = _build_coins(symbol, symbol_id, symbols, symbol_ids, coin_list)

        valid = {f.name for f in attrs.fields(cls)}
        widget = cls(
            coins=coins,
            currency=currency,
            session=session,
            **{k: v for k, v in kwargs.items() if k in valid},
        )
        # Tolerate a failed INITIAL price fetch (e.g. a CoinGecko 429 at boot)
        # so the widget still constructs and the monitor loop can recover, rather
        # than the whole widget being skipped for the session. The broad except
        # also swallows a coding bug in update() — that surfaces only as a
        # repeating warning log + frozen placeholder data, which is the
        # acceptable tradeoff for "a data fetch must never crash startup".
        try:
            await widget.update()
        except Exception as e:
            logging.warning(
                "crypto.coingecko initial fetch failed (%s); "
                "starting with placeholder data, will retry",
                e,
            )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        # MULTIPLE ids MUST be comma-joined in ONE string — passing a list
        # makes aiohttp emit ids=a&ids=b, which CoinGecko rejects for >1 id.
        ids = ",".join(coin_id for _, coin_id in self.coins)
        params: dict[str, Any] = {
            "ids": ids,
            "vs_currencies": self.currency,
            "include_24hr_change": "true",
        }
        async with self.session.get(
            COINGECKO_PRICE_API, params=params, headers=self._headers()
        ) as response:
            if response.status != 200:
                retry = response.headers.get("retry-after")
                suffix = f" (retry-after {retry})" if retry else ""
                logging.warning(
                    "CoinGecko price fetch failed: HTTP %s%s", response.status, suffix
                )
                # Raise so run_monitor_loop's backoff engages; never parse an
                # error body as prices.
                response.raise_for_status()

            data = await response.json()

        cur = self.currency.lower()
        cur_change = f"{cur}_24h_change"

        updated = 0
        for coin_id, story in self._story_by_id.items():
            entry = data.get(coin_id)
            if not entry or cur not in entry or cur_change not in entry:
                logging.warning(
                    "CoinGecko: no price for %s (keeping prior value): %s",
                    coin_id,
                    entry,
                )
                continue
            story.price_data = {
                "price": _format_price(entry[cur]),
                "change_24h": f"{entry[cur_change]:.2f}%",
            }
            updated += 1

        # One INFO line per successful update (Container contract): a silent
        # log stream after startup signals the background task died.
        logging.info(
            "CoinGecko updated: %s/%s coins (%s)",
            updated,
            len(self.coins),
            ", ".join(coin_id for _, coin_id in self.coins),
        )


async def _get_coingecko_coin_list(
    session: aiohttp.ClientSession,
    headers: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    logging.info("Fetching CoinGecko coin list...")
    req_headers = {"Accept": "application/json", **(headers or {})}
    async with session.get(COINGECKO_COIN_LIST, headers=req_headers) as response:
        return await response.json()
