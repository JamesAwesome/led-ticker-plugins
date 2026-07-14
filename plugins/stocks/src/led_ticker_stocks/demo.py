"""Offline random-walk feed for demo mode (no token). Mirrors the handoff simulation."""

import random
import time

from led_ticker_stocks.model import SymbolQuote


def _seed_price(sym: str) -> float:
    # Deterministic 50-500 range from the symbol, no RNG-at-import.
    h = sum(ord(c) for c in sym)
    return 50.0 + (h * 7 % 450)


def seed_quotes(symbols):
    out = {}
    for sym in symbols:
        p = _seed_price(sym)
        out[sym] = SymbolQuote(sym=sym, price=p, prev=p)
        out[sym].spark.append(p)
    return out


class DemoFeed:
    def __init__(self, symbols):
        self.quotes = seed_quotes(symbols)
        self._symbols = list(symbols)
        self._rng = random.Random(1234)
        self._i = 0

    def step(self) -> None:
        sym = self._symbols[self._i % len(self._symbols)]
        self._i += 1
        q = self.quotes[sym]
        drift = self._rng.uniform(-0.0016, 0.0016) + 0.0001  # ±0.16%, slight up bias
        q.push_price(round(q.price * (1 + drift), 2))
        q.flash_t = time.monotonic()
