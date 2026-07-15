"""Dedup integration test — the teeth for the shared-`QuoteCache` premise.

`_cache.py`'s whole reason for existing is that MULTIPLE consumers (a
`stocks.ticker` widget AND a `stocks.quote` source, possibly several of
each) can register overlapping symbol sets without multiplying Finnhub
request volume. This test proves that end-to-end: two independent
consumers register the SAME symbol, one live poll cycle runs, and the
underlying client's `fetch_quote` is asserted to have been called EXACTLY
ONCE for that symbol — not once per consumer. A cache that (regressively)
tracked fetches per-consumer instead of per-symbol-in-a-set would fail
this test.
"""

import unittest.mock as mock

from led_ticker_stocks import _cache
from led_ticker_stocks.source import StockSource


async def test_shared_symbol_fetched_exactly_once_per_cycle(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()

    # Consumer 1: widget-style registration (mirrors StocksTicker.start()'s
    # `get_cache().register(widget.symbols)` call).
    c.register(["AAPL"])

    # Consumer 2: an INDEPENDENT stocks.quote source registers the SAME
    # symbol via its own __attrs_post_init__ -> get_cache().register([...]).
    src = StockSource(
        id="stocks.aapl",
        session=mock.Mock(),
        interval=60,
        symbol="AAPL",
        format="{price}",
    )

    # Only one symbol is tracked even though two consumers registered it.
    assert c._symbols == {"AAPL"}

    # Start the shared poll loop (tolerates whatever the initial fetch does
    # against the mock session/client — same pattern as test_cache.py).
    await c.ensure_started(session=mock.Mock())

    calls: dict[str, int] = {}

    async def counting_fetch_quote(sym: str):
        calls[sym] = calls.get(sym, 0) + 1
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0, "h": 201, "l": 194}

    async def open_status(exchange: str = "US"):
        return {"isOpen": True, "session": "regular"}

    c._client.fetch_quote = counting_fetch_quote
    c._client.fetch_market_status = open_status

    await c.update()  # ONE poll cycle, live mode, market OPEN

    # The heart of the assertion: AAPL fetched exactly once this cycle, not
    # twice (once per consumer) and not zero (dropped/never reached).
    assert calls == {"AAPL": 1}

    # Both consumers observe the SAME data from that single fetch.
    assert c.get("AAPL").price == 200.0
    await src.update()
    assert src.current == "200.00"
