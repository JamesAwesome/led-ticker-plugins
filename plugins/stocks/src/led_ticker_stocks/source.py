"""stocks.quote polled SOURCE — an inline-price value token like `:stocks.aapl:`.

Subclasses the core PolledDataSource mechanism (led-ticker-core >= 4.9): core
drives a supervised poll loop that calls `update()` every `interval` seconds;
`update()` reads the shared `QuoteCache` (`_cache.py`) and renders a `format`
string over the exposed fields, then `self._set_value(...)` (write-order).

Unlike `weather.current` (which fetches directly per-call), stocks sources
read a SHARED cache that owns the actual Finnhub I/O — the same cache the
`stocks.ticker` widget reads. A token-only config (no widget in the same
process) still needs the cache's poll loop running, so `update()` calls
`get_cache().ensure_started(self.session)` on every tick; `ensure_started`
is idempotent (no-op after the first call, from ANY consumer), so this is
cheap and safe to call unconditionally rather than tracking a local
"have I started it yet" flag.
"""

import string
from typing import Any

import attrs
from led_ticker.plugin import PolledDataSource

from led_ticker_stocks._cache import get_cache
from led_ticker_stocks.model import SymbolQuote, format_change, format_pct, format_price

_DEFAULT_FORMAT = "{price}"

# Known `provider` values — single source of truth, imported by ticker.py.
_PROVIDERS = ("finnhub", "twelvedata")

# Fields exposed to `format`.
_FIELDS = (
    "price",
    "change",
    "pct",
    "arrow",
    "symbol",
    "prev",
    "high",
    "low",
    "day_range",
)

# Typed sample for validate_config dry-run: one value per field, covers all
# conversion specs (:d, :.1f, :s, etc.) without hitting the real cache.
_SAMPLE: dict[str, Any] = {
    "price": "0.00",
    "change": "+0.00",
    "pct": "+0.00%",
    "arrow": "▲",
    "symbol": "x",
    "prev": "0.00",
    "high": "0.00",
    "low": "0.00",
    "day_range": "0.00–0.00",
}


@attrs.define(eq=False)
class StockSource(PolledDataSource):
    symbol: str = attrs.field(default="", kw_only=True)
    format: str = attrs.field(default=_DEFAULT_FORMAT, kw_only=True)
    placeholder: str = attrs.field(default="…", kw_only=True)
    provider: str = attrs.field(default="finnhub", kw_only=True)
    decimals: int | None = attrs.field(default=None, kw_only=True)
    # Cached at construction: only the field names referenced in `format`.
    # Declared as an attrs field (slotted class) — set in __attrs_post_init__.
    _used_fields: tuple[str, ...] = attrs.field(init=False, factory=tuple)

    @classmethod
    def validate_config(cls, cfg: dict) -> list[str]:
        errors: list[str] = []
        provider = cfg.get("provider", "finnhub")
        if provider not in _PROVIDERS:
            errors.append(
                f"stocks.quote: unknown provider {provider!r} "
                f"(known: {', '.join(_PROVIDERS)})."
            )
        symbol = cfg.get("symbol")
        if not symbol:
            errors.append("stocks.quote: 'symbol' is required.")
        elif isinstance(symbol, str) and "/" in symbol and provider == "finnhub":
            errors.append(
                f"stocks.quote: {symbol!r} looks like forex — FX requires a paid "
                'Finnhub tier. Use provider = "twelvedata" for forex/crypto.'
            )
        fmt = cfg.get("format", _DEFAULT_FORMAT)
        if not isinstance(fmt, str):
            errors.append(
                f"stocks.quote: 'format' must be a string, got {type(fmt).__name__}."
            )
            return errors
        # Parse the format (guarded: an unclosed brace like "{price" raises
        # ValueError — surface it as a clean plugin error, not a raised exception).
        try:
            parsed = list(string.Formatter().parse(fmt))
        except ValueError as exc:
            errors.append(f"stocks.quote: malformed format string: {exc}")
            return errors
        # Check for unknown field names first (gives a clearer message).
        for _literal, field_name, _spec, _conv in parsed:
            if field_name and field_name not in _FIELDS:
                errors.append(
                    f"stocks.quote: unknown field '{{{field_name}}}' in format "
                    f"(known: {', '.join(_FIELDS)})."
                )
        # Dry-run against typed samples to catch bad conversion specs
        # (e.g. "{price:zzz}", "{symbol:d}", nested braces).
        # Skip if we already flagged an unknown field — the sample won't have it.
        if not errors:
            try:
                fmt.format(**_SAMPLE)
            except (ValueError, KeyError, IndexError) as exc:
                errors.append(f"stocks.quote: invalid format string: {exc}")
        return errors

    def __attrs_post_init__(self) -> None:
        get_cache().register([self.symbol])
        # Cache the field names actually referenced by the format string so
        # update() only computes the fields it needs (lazy, weather-style).
        self._used_fields = tuple(
            name for _, name, _, _ in string.Formatter().parse(self.format) if name
        )
        # Show the placeholder until the first successful quote arrives.
        self.current = self.placeholder

    def _field_value(self, q: SymbolQuote, name: str) -> Any:
        """Compute one field value by name from a live `SymbolQuote`.

        `self.decimals` (config override) wins over the quote's own
        auto-picked `dp_decimals` when set — e.g. forcing a forex pair to
        2 decimals instead of `decimals_for`'s auto 4.
        """
        dec = self.decimals if self.decimals is not None else q.dp_decimals
        if name == "price":
            return format_price(q.price, dec)
        if name == "change":
            return format_change(q.change, dec)
        if name == "pct":
            return format_pct(q.pct)
        if name == "arrow":
            if q.change is None or q.change == 0:
                return "·"
            return "▲" if q.change > 0 else "▼"
        if name == "symbol":
            return q.sym
        if name == "prev":
            return format_price(q.prev, dec)
        if name == "high":
            return "—" if q.high is None else format_price(q.high, dec)
        if name == "low":
            return "—" if q.low is None else format_price(q.low, dec)
        if name == "day_range":
            low = "—" if q.low is None else format_price(q.low, dec)
            high = "—" if q.high is None else format_price(q.high, dec)
            return f"{low}–{high}"
        raise KeyError(name)  # unreachable for validated formats

    async def update(self) -> None:
        # Idempotent: the shared cache starts its poll loop exactly once,
        # from whichever consumer (widget or source) reaches this first.
        # A token-only config with no `stocks.ticker` widget still needs
        # this to actually populate the cache.
        await get_cache().ensure_started(
            self.session, interval=self.interval, provider=self.provider
        )
        q = get_cache().get(self.symbol)
        if q is None or not q.has_data:
            # Leave the placeholder (or last good value) — no data yet.
            return
        fields = {name: self._field_value(q, name) for name in self._used_fields}
        # Minus-sign belt: a token is embedded in an arbitrary user message
        # font that may lack U+2212 MINUS SIGN (which format_change/format_pct
        # emit for negatives) — it renders as "?" there. Core PR #393 fixes
        # this generally in the hi-res rasterizer, but substitute here too so
        # the cure ships with the plugin, font-agnostic, before a core release.
        value = self.format.format(**fields).replace("−", "-")
        # write-order: _set_value writes current before version, no await between.
        self._set_value(value)
