"""Per-symbol quote model + display formatting."""

import collections

import attrs

_MINUS = "−"  # U+2212 MINUS SIGN (renders wider/cleaner than hyphen)
_DASH = "—"  # U+2014 EM DASH placeholder for no-data


@attrs.define
class SymbolQuote:
    sym: str
    price: float
    prev: float
    d: float | None = None
    dp: float | None = None
    dp_decimals: int = 2
    spark: collections.deque = attrs.field(factory=lambda: collections.deque(maxlen=64))
    chip_colors: tuple | None = None
    flash_t: float | None = None
    high: float | None = None
    low: float | None = None

    @property
    def has_data(self) -> bool:
        return self.prev != 0 and self.price != 0

    @property
    def change(self) -> float | None:
        if not self.has_data:
            return None
        if self.d is not None:
            return self.d
        return self.price - self.prev

    @property
    def pct(self) -> float | None:
        if not self.has_data:
            return None
        if self.dp is not None:
            return self.dp
        return (self.price - self.prev) / self.prev * 100.0

    def push_price(self, price: float) -> None:
        self.price = price
        self.spark.append(price)


def format_price(v: float, decimals: int) -> str:
    return f"{v:,.{decimals}f}"


def format_change(v: float | None, decimals: int) -> str:
    if v is None:
        return _DASH
    sign = "+" if v >= 0 else _MINUS
    return f"{sign}{abs(v):.{decimals}f}"


def format_pct(v: float | None) -> str:
    if v is None:
        return _DASH
    sign = "+" if v >= 0 else _MINUS
    return f"{sign}{abs(v):.2f}%"
