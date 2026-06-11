"""Tests for led_ticker_crypto (coingecko widget + shared renderer)."""

import unittest.mock as mock

import aiohttp
import pytest

from led_ticker.plugin import Widget

from led_ticker_crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)
from led_ticker_crypto._ticker_render import (
    FONT_VALUE,
    FONT_VALUE_SMALL,
    _get_change_color,
    _get_price_font,
    draw_price_ticker,
)
from led_ticker_crypto.coingecko import (
    CoinGeckoMonitor,
    _CoinTicker,
)


def _mock_session(json_body, status=200, capture=None):
    """Build a Mock aiohttp session.

    `.get(url, params=, headers=)` records its url/params/headers into
    `capture` (if given) and returns an async-context manager yielding a
    response with `.status`, async `.json()`, and a `.raise_for_status()`
    that raises `aiohttp.ClientResponseError` when status != 200 (mirroring
    aiohttp's own behavior).
    """
    session = mock.Mock()

    resp = mock.AsyncMock()
    resp.status = status
    resp.json = mock.AsyncMock(return_value=json_body)
    resp.headers = {}

    def _raise_for_status():
        if status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=mock.Mock(),
                history=(),
                status=status,
            )

    resp.raise_for_status = mock.Mock(side_effect=_raise_for_status)

    ctx = mock.AsyncMock()
    ctx.__aenter__ = mock.AsyncMock(return_value=resp)
    ctx.__aexit__ = mock.AsyncMock(return_value=False)

    def _get(url, params=None, headers=None):
        if capture is not None:
            capture["url"] = url
            capture["params"] = params
            capture["headers"] = headers
        return ctx

    session.get = mock.Mock(side_effect=_get)
    return session


class TestRenderHelpers:
    def test_change_color_positive(self):
        assert _get_change_color("2.55%") == UP_TREND_COLOR

    def test_change_color_negative(self):
        assert _get_change_color("-1.23%") == DOWN_TREND_COLOR

    def test_change_color_zero_is_neutral(self):
        assert _get_change_color("0.00%") == NEUTRAL_TREND_COLOR
        assert _get_change_color("0%") == NEUTRAL_TREND_COLOR

    def test_change_color_unparseable_is_neutral(self):
        assert _get_change_color("N/A") == NEUTRAL_TREND_COLOR
        assert _get_change_color("") == NEUTRAL_TREND_COLOR

    def test_price_font_short(self):
        assert _get_price_font("1234.5678") == FONT_VALUE

    def test_price_font_long(self):
        assert _get_price_font("12345678.90") == FONT_VALUE_SMALL


class TestDrawPriceTicker:
    def test_returns_canvas(self, canvas):
        result, pos = draw_price_ticker(canvas, "BTC", "50000.00", "2.55%")
        assert result is canvas
        assert pos > 0

    def test_centered_fills_canvas(self, canvas):
        _, pos = draw_price_ticker(canvas, "BTC", "50000.00", "2.55%", center=True)
        assert pos == 160


class TestCoinTicker:
    @pytest.fixture
    def story(self):
        s = _CoinTicker(symbol="ETH", currency="USD")
        s.price_data = {"price": "3,000.0000", "change_24h": "1.50%"}
        return s

    def test_conforms_to_widget_protocol(self, story):
        assert isinstance(story, Widget)

    def test_draw_returns_canvas(self, canvas, story):
        result, pos = story.draw(canvas)
        assert result is canvas
        assert pos > 0

    def test_default_price_data(self):
        s = _CoinTicker(symbol="BTC", currency="USD")
        assert s.price_data == {"price": "0.0000", "change_24h": "0.00%"}


class TestCoinGeckoMonitor:
    def test_bg_color_default_is_none(self):
        w = CoinGeckoMonitor(
            coins=[("ETH", "ethereum")], currency="USD", session=mock.Mock()
        )
        assert w.bg_color is None

    def test_accepts_bg_color(self):
        from led_ticker.plugin import make_color

        w = CoinGeckoMonitor(
            coins=[("ETH", "ethereum")],
            currency="USD",
            session=mock.Mock(),
            bg_color=make_color(10, 20, 30),
        )
        assert w.bg_color is not None

    def test_feed_title_is_none(self):
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")], currency="USD", session=mock.Mock()
        )
        assert w.feed_title is None

    def test_stories_built_at_construction(self):
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin"), ("ETH", "ethereum")],
            currency="USD",
            session=mock.Mock(),
        )
        assert [s.symbol for s in w.feed_stories] == ["BTC", "ETH"]
        # stories exist with default price_data even before the first fetch
        assert w.feed_stories[0].price_data["price"] == "0.0000"

    async def test_update_parses_multiple_coins(self):
        session = _mock_session(
            {
                "bitcoin": {"usd": 50000.0, "usd_24h_change": 1.0},
                "ethereum": {"usd": 3000.0, "usd_24h_change": -2.0},
            }
        )
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin"), ("ETH", "ethereum")],
            currency="USD",
            session=session,
        )
        await w.update()
        prices = {s.symbol: s.price_data["price"] for s in w.feed_stories}
        assert prices["BTC"] == "50,000.0000"
        assert prices["ETH"] == "3,000.0000"

    async def test_non_200_raises_for_backoff(self):
        session = _mock_session({"status": {"error_code": 429}}, status=429)
        w = CoinGeckoMonitor(coins=[("BTC", "bitcoin")], currency="USD", session=session)
        with pytest.raises(aiohttp.ClientResponseError):
            await w.update()
        # stale price preserved (not overwritten with garbage)
        assert w.feed_stories[0].price_data["price"] == "0.0000"

    async def test_sub_cent_coin_formats_nonzero(self):
        session = _mock_session({"shiba-inu": {"usd": 4.64e-06, "usd_24h_change": 5.0}})
        w = CoinGeckoMonitor(
            coins=[("SHIB", "shiba-inu")], currency="USD", session=session
        )
        await w.update()
        assert w.feed_stories[0].price_data["price"] not in ("0.0000", "0")

    async def test_ids_param_is_comma_joined_string(self):
        captured = {}
        session = _mock_session(
            {
                "bitcoin": {"usd": 1.0, "usd_24h_change": 0.0},
                "ethereum": {"usd": 1.0, "usd_24h_change": 0.0},
            },
            capture=captured,
        )
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin"), ("ETH", "ethereum")],
            currency="USD",
            session=session,
        )
        await w.update()
        assert captured["params"]["ids"] == "bitcoin,ethereum"

    async def test_api_key_sets_demo_header(self):
        captured = {}
        session = _mock_session(
            {"bitcoin": {"usd": 1.0, "usd_24h_change": 0.0}}, capture=captured
        )
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")],
            currency="USD",
            session=session,
            api_key="demo-123",
        )
        await w.update()
        assert captured["headers"]["x-cg-demo-api-key"] == "demo-123"

    async def test_no_api_key_sends_no_demo_header(self):
        captured = {}
        session = _mock_session(
            {"bitcoin": {"usd": 1.0, "usd_24h_change": 0.0}}, capture=captured
        )
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")], currency="USD", session=session, api_key=""
        )
        await w.update()
        assert "x-cg-demo-api-key" not in (captured["headers"] or {})

    async def test_missing_coin_preserves_prior_price(self):
        session = _mock_session({})  # coin-not-found → {} (HTTP 200)
        w = CoinGeckoMonitor(coins=[("BTC", "bitcoin")], currency="USD", session=session)
        await w.update()
        assert w.feed_stories[0].price_data["price"] == "0.0000"

    def test_is_container_with_stories(self):
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")], currency="USD", session=mock.Mock()
        )
        assert isinstance(w.feed_stories, list)
        assert all(isinstance(s, Widget) for s in w.feed_stories)

    def test_hold_time_threads_to_stories(self):
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")], currency="USD", session=mock.Mock(), hold_time=4.0
        )
        assert all(s.hold_time == 4.0 for s in w.feed_stories)


class TestValidateConfig:
    def test_no_coin_specified_is_rejected(self):
        msgs = CoinGeckoMonitor.validate_config({"currency": "USD"})
        assert any("symbol" in m for m in msgs)

    def test_legacy_single_coin_ok(self):
        assert CoinGeckoMonitor.validate_config(
            {"symbol": "BTC", "symbol_id": "bitcoin", "currency": "USD"}) == []

    def test_symbols_list_ok(self):
        assert CoinGeckoMonitor.validate_config({"symbols": ["BTC", "ETH"]}) == []

    def test_symbol_ids_list_ok(self):
        assert CoinGeckoMonitor.validate_config({"symbol_ids": ["bitcoin"]}) == []

    def test_symbols_not_a_list_rejected(self):
        msgs = CoinGeckoMonitor.validate_config({"symbols": "BTC"})
        assert len(msgs) > 0
        assert any("symbols" in m for m in msgs)

    def test_symbols_with_empty_string_or_non_string_rejected(self):
        msgs = CoinGeckoMonitor.validate_config({"symbols": ["", 5]})
        assert len(msgs) > 0
        assert any("symbols" in m for m in msgs)


def _mock_session_seq(bodies, status=200):
    """Like _mock_session but returns successive bodies on successive .get calls."""
    session = mock.Mock()
    call_count = 0
    responses = []

    for body in bodies:
        resp = mock.AsyncMock()
        resp.status = status
        resp.json = mock.AsyncMock(return_value=body)
        resp.headers = {}

        def _raise_for_status(s=status):
            if s >= 400:
                raise aiohttp.ClientResponseError(
                    request_info=mock.Mock(),
                    history=(),
                    status=s,
                )

        resp.raise_for_status = mock.Mock(side_effect=_raise_for_status)

        ctx = mock.AsyncMock()
        ctx.__aenter__ = mock.AsyncMock(return_value=resp)
        ctx.__aexit__ = mock.AsyncMock(return_value=False)
        responses.append(ctx)

    def _get(url, params=None, headers=None):
        nonlocal call_count
        idx = call_count
        call_count += 1
        return responses[idx]

    session.get = mock.Mock(side_effect=_get)
    return session


class TestCoinGeckoMonitorAdditional:
    """Additional update() and start() tests (Phase-3 coverage gaps)."""

    async def test_update_partial_entry_keeps_prior_price(self):
        """A coin whose entry lacks usd_24h_change must NOT overwrite price_data."""
        session = _mock_session(
            {
                "bitcoin": {"usd": 50000.0, "usd_24h_change": 1.0},
                "ethereum": {"usd": 3000.0},  # missing usd_24h_change
            }
        )
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin"), ("ETH", "ethereum")],
            currency="USD",
            session=session,
        )
        # Preset ETH to a known prior value so we can confirm it is preserved.
        w.feed_stories[1].price_data = {"price": "2,500.0000", "change_24h": "0.50%"}
        await w.update()

        # BTC (complete entry) should have updated.
        assert w.feed_stories[0].price_data["price"] == "50,000.0000"
        # ETH (incomplete entry) must keep its prior price_data intact.
        assert w.feed_stories[1].price_data["price"] == "2,500.0000"
        assert w.feed_stories[1].price_data["change_24h"] == "0.50%"

    async def test_start_classmethod_resolves_and_updates(self):
        """start() via symbol_ids resolves coins and populates prices."""
        session = _mock_session_seq([
            # First .get = /simple/price (no symbols → no coin-list fetch)
            {"bitcoin": {"usd": 50000.0, "usd_24h_change": 1.0}},
        ])
        widget = await CoinGeckoMonitor.start(
            symbol_ids=["bitcoin"],
            currency="USD",
            session=session,
        )
        assert widget.coins == [("BITCOIN", "bitcoin")]
        assert widget.feed_stories[0].price_data["price"] == "50,000.0000"

    async def test_start_with_symbols_fetches_coin_list_first(self):
        """start() with symbols= fetches the coin list then prices."""
        session = _mock_session_seq([
            # First .get = /coins/list
            [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}],
            # Second .get = /simple/price
            {"bitcoin": {"usd": 60000.0, "usd_24h_change": 2.5}},
        ])
        widget = await CoinGeckoMonitor.start(
            symbols=["BTC"],
            currency="USD",
            session=session,
        )
        assert widget.coins == [("BTC", "bitcoin")]
        assert widget.feed_stories[0].price_data["price"] == "60,000.0000"

    async def test_update_non_usd_currency(self):
        """update() with currency=EUR uses eur/eur_24h_change keys."""
        captured: dict = {}
        session = _mock_session(
            {"bitcoin": {"eur": 47000.0, "eur_24h_change": 0.5}},
            capture=captured,
        )
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")],
            currency="EUR",
            session=session,
        )
        await w.update()
        assert w.feed_stories[0].price_data["price"] == "47,000.0000"
        assert captured["params"]["vs_currencies"] == "EUR"

    def test_env_api_key_read_at_construction(self, monkeypatch):
        """COINGECKO_API_KEY env var is picked up and wired into _headers()."""
        monkeypatch.setenv("COINGECKO_API_KEY", "env-key-9")
        w = CoinGeckoMonitor(
            coins=[("BTC", "bitcoin")],
            currency="USD",
            session=mock.Mock(),
        )
        assert w.api_key == "env-key-9"
        assert w._headers()["x-cg-demo-api-key"] == "env-key-9"

    async def test_get_coingecko_coin_list_passes_headers(self):
        """_get_coingecko_coin_list forwards caller-supplied headers to .get."""
        from led_ticker_crypto.coingecko import _get_coingecko_coin_list

        captured: dict = {}
        session = _mock_session(
            [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}],
            capture=captured,
        )
        result = await _get_coingecko_coin_list(
            session, headers={"x-cg-demo-api-key": "k"}
        )
        assert result[0]["id"] == "bitcoin"
        assert captured["headers"]["x-cg-demo-api-key"] == "k"
