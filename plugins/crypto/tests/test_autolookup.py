import pytest

from led_ticker_crypto.coingecko import _build_coins, _resolve_symbols

COIN_LIST = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
    {"id": "ethereum", "symbol": "eth", "name": "Ethereum"},
    {"id": "binance-peg-ethereum", "symbol": "eth", "name": "Binance-Peg Ethereum"},
]


def test_unique_symbol_resolves():
    assert _resolve_symbols(["BTC"], COIN_LIST) == [("BTC", "bitcoin")]


def test_unknown_symbol_raises():
    with pytest.raises(ValueError, match="not found"):
        _resolve_symbols(["NOPE"], COIN_LIST)


def test_ambiguous_symbol_raises_listing_candidates():
    with pytest.raises(ValueError) as exc:
        _resolve_symbols(["ETH"], COIN_LIST)
    msg = str(exc.value)
    assert "ethereum" in msg and "binance-peg-ethereum" in msg
    assert "symbol_id" in msg  # tells the user how to disambiguate


# ---------------------------------------------------------------------------
# _build_coins unit tests
# ---------------------------------------------------------------------------

class TestBuildCoins:
    """Unit tests for _build_coins — the highest-value coverage gap."""

    def test_legacy_symbol_and_symbol_id(self):
        result = _build_coins(
            symbol="BTC", symbol_id="bitcoin",
            symbols=None, symbol_ids=None, coin_list=None,
        )
        assert result == [("BTC", "bitcoin")]

    def test_symbol_ids_uppercased_display(self):
        # symbol_ids entries produce (cid.upper(), cid) — display is uppercased,
        # coin_id stays lowercased (matches the code: coins.append((cid.upper(), cid)))
        result = _build_coins(
            symbol=None, symbol_id=None,
            symbols=None, symbol_ids=["bitcoin", "ethereum"], coin_list=None,
        )
        assert result == [("BITCOIN", "bitcoin"), ("ETHEREUM", "ethereum")]

    def test_combined_order_legacy_then_symbol_ids_then_symbols(self):
        # A small, unambiguous coin_list so symbols can be resolved
        coin_list = [{"id": "solana", "symbol": "sol", "name": "Solana"}]
        result = _build_coins(
            symbol="BTC", symbol_id="bitcoin",
            symbols=["SOL"], symbol_ids=["ethereum"], coin_list=coin_list,
        )
        # Legacy first, then symbol_ids, then resolved symbols
        assert result == [
            ("BTC", "bitcoin"),
            ("ETHEREUM", "ethereum"),
            ("SOL", "solana"),
        ]

    def test_dedup_keeps_first_occurrence(self):
        # "bitcoin" arrives via legacy AND symbol_ids — second occurrence dropped
        result = _build_coins(
            symbol="BTC", symbol_id="bitcoin",
            symbols=None, symbol_ids=["bitcoin"], coin_list=None,
        )
        assert result == [("BTC", "bitcoin")]

    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError, match="at least one"):
            _build_coins(
                symbol=None, symbol_id=None,
                symbols=None, symbol_ids=None, coin_list=None,
            )
