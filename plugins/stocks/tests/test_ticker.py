"""StocksTicker Container + _StockStory: shared-quote crawl stories."""

import unittest.mock as mock

import pytest

from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState
from led_ticker_stocks.ticker import StocksTicker, _StockStory


def _canvas():
    c = mock.Mock()
    c.width = 160
    c.height = 16
    c.scale = 1
    return c


def test_validate_rejects_empty_symbols():
    msgs = StocksTicker.validate_config({"symbols": []})
    assert any("symbol" in m for m in msgs)


def test_validate_rejects_fx_symbol():
    msgs = StocksTicker.validate_config({"symbols": ["EUR/USD"]})
    assert any("forex" in m.lower() or "paid" in m.lower() for m in msgs)


def test_validate_rejects_unknown_layout():
    msgs = StocksTicker.validate_config({"symbols": ["AAPL"], "layout": "bogus"})
    assert any("layout" in m for m in msgs)


def test_story_draw_reads_shared_quotes():
    quotes = {
        "AAPL": SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    }
    state_ref = [MarketState.OPEN]
    story = _StockStory(
        sym="AAPL",
        quotes=quotes,
        state_ref=state_ref,
        layout=None,
        green_up=True,
        padding=6,
    )
    canvas, cursor = story.draw(_canvas(), 0)
    assert cursor > 0


@pytest.mark.asyncio
async def test_demo_start_builds_stories_without_token():
    widget = await StocksTicker.start(
        symbols=["AAPL", "MSFT"], session=mock.Mock(), demo=True
    )
    assert len(widget.feed_stories) == 2
    assert all(s.quotes["AAPL"].has_data for s in widget.feed_stories)


@pytest.mark.asyncio
async def test_update_live_updates_shared_quotes(monkeypatch):
    widget = await StocksTicker.start(
        symbols=["AAPL"], session=mock.Mock(), demo=False, token="tok"
    )

    async def fake_quote(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0}

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    widget._client.fetch_quote = fake_quote
    widget._client.fetch_market_status = fake_status
    await widget.update()
    assert widget.feed_stories[0].quotes["AAPL"].price == 200.0
    assert widget._state_ref[0] is MarketState.OPEN
