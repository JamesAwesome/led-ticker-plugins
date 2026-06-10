"""CoinGecko price monitor widget (crypto.coingecko)."""

import logging
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
    draw_price_ticker,
    make_default_font_color,
)

COINGECKO_API: str = "https://api.coingecko.com/api/v3"
COINGECKO_COIN_LIST: str = f"{COINGECKO_API}/coins/list"
COINGECKO_PRICE_API: str = f"{COINGECKO_API}/simple/price"


@attrs.define
class CoinGeckoPriceMonitor(FrameAwareBase):
    """Crypto price monitor using the CoinGecko API."""

    symbol: str
    symbol_id: str
    currency: str
    session: aiohttp.ClientSession
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

    @classmethod
    async def start(
        cls,
        symbol: str,
        symbol_id: str,
        currency: str,
        session: aiohttp.ClientSession,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        valid = {f.name for f in attrs.fields(cls)}
        widget = cls(
            symbol=symbol,
            symbol_id=symbol_id,
            currency=currency,
            session=session,
            **{k: v for k, v in kwargs.items() if k in valid},
        )
        await widget.update()
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating monitor for %s via CoinGecko", self.symbol)
        params: dict[str, Any] = {
            "ids": [self.symbol_id],
            "vs_currencies": self.currency,
            "include_24hr_change": "true",
        }
        async with self.session.get(COINGECKO_PRICE_API, params=params) as response:
            price_data = await response.json()
            cur = self.currency.lower()
            cur_change = f"{cur}_24h_change"

            for coin_id, data in price_data.items():
                try:
                    price = f"{data[cur]:,.4f}"
                    change_24h = f"{data[cur_change]:.2f}%"
                except (KeyError, TypeError):
                    logging.warning("API data not complete for %s: %s", coin_id, data)
                    continue

                self.price_data = {"price": price, "change_24h": change_24h}

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


async def _get_coingecko_coin_list(
    session: aiohttp.ClientSession,
) -> list[dict[str, Any]]:
    logging.info("Fetching CoinGecko coin list...")
    headers = {"Accept": "application/json"}
    async with session.get(COINGECKO_COIN_LIST, headers=headers) as response:
        return await response.json()


def _find_coingecko_symbol_id(
    coin_list: list[dict[str, Any]], symbol: str
) -> str | None:
    for coin_meta in coin_list:
        if symbol.lower() == coin_meta["symbol"].lower():
            return coin_meta["id"]
    return None
