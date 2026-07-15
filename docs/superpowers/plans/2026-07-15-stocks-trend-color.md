# `stocks.trend` color provider — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a `stocks.trend` plugin color provider that tints a text widget green (up) / red (down) / neutral (flat/no-data) by a symbol's day change, reading the shared `QuoteCache`.

**Architecture:** A `ColorProvider` (via core's `api.color_provider`) registered as `stocks.trend`. Whole-string (`per_char=False`), live (`frame_invariant=False`). Reads `get_cache().get(symbol)`, mirrors the widget's `chg_color` logic. Registers the symbol into the cache (does not start it).

**Tech Stack:** Python 3.14, attrs-free plain class, pytest. `led-ticker-core>=4.9` (already the floor; `api.color_provider` shipped in v4.9.0).

## Global Constraints

- Never work on `main`; worktree `led-ticker-plugins--stocks-trend`, branch `feat/stocks-trend-color`. Verify `git branch --show-current` before editing.
- Plugins import ONLY from `led_ticker.plugin` (public surface) — never `led_ticker.<internal>`. (Reading `led_ticker_stocks._cache` / `_palette` is same-plugin, fine.)
- No `from __future__ import annotations` (PEP 649 / py3.14).
- `color_for` MUST NEVER raise — a color provider runs in the render loop.
- The provider READS the cache; it must NOT start the cache or perform I/O.
- Tests/lint from the plugin dir or worktree root: `uv run --extra dev pytest plugins/stocks -q`, `uv run --extra dev ruff check plugins/stocks`, `uv run --extra dev ruff format --check plugins/stocks`, `uv run --extra dev pyright plugins/stocks/src`. No `# type: ignore`.

---

### Task 1: `StocksTrendColor` provider + registration

**Files:**
- Create: `plugins/stocks/src/led_ticker_stocks/trend_color.py`
- Modify: `plugins/stocks/src/led_ticker_stocks/__init__.py` (register the provider)
- Test: `plugins/stocks/tests/test_trend_color.py` (new), `plugins/stocks/tests/test_smoke.py` (extend)

**Interfaces:**
- Consumes: `from led_ticker.plugin import Color, ColorProviderBase, make_color`; `from led_ticker_stocks._cache import get_cache` (`.register([sym])`, `.get(sym) -> SymbolQuote | None`); `from led_ticker_stocks import _palette as pal` (`pal.UP`, `pal.DOWN`); `SymbolQuote.change` (`price - prev`, or `None` when `not has_data`).
- Produces: `StocksTrendColor(symbol, up=None, down=None, flat=None, green_up=True)`; registered as `stocks.trend`.

- [ ] **Step 1: Write the failing unit tests**

Create `plugins/stocks/tests/test_trend_color.py`:

```python
"""stocks.trend color provider: green up / red down / neutral flat."""

import pytest

from led_ticker_stocks import _cache
from led_ticker_stocks import _palette as pal
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.trend_color import _DEFAULT_FLAT, StocksTrendColor


@pytest.fixture(autouse=True)
def _reset_cache():
    _cache.get_cache().reset()
    yield
    _cache.get_cache().reset()


def _rgb(c):
    return (c.red, c.green, c.blue)


def _seed(symbol, price, prev):
    c = _cache.get_cache()
    c.register([symbol])
    c._quotes[symbol] = SymbolQuote(sym=symbol, price=price, prev=prev)


def test_up_returns_up_color():
    _seed("AAPL", price=110.0, prev=100.0)  # change +10
    assert _rgb(StocksTrendColor(symbol="AAPL").color_for(0, 0, 1)) == _rgb(pal.UP)


def test_down_returns_down_color():
    _seed("AAPL", price=90.0, prev=100.0)  # change -10
    assert _rgb(StocksTrendColor(symbol="AAPL").color_for(0, 0, 1)) == _rgb(pal.DOWN)


def test_flat_change_returns_flat_color():
    _seed("AAPL", price=100.0, prev=100.0)  # change 0
    assert _rgb(StocksTrendColor(symbol="AAPL").color_for(0, 0, 1)) == _rgb(_DEFAULT_FLAT)


def test_no_data_returns_flat_and_does_not_raise():
    # never seeded: __init__ registers a zeroed (no-data) quote -> change None -> flat
    p = StocksTrendColor(symbol="ZZZZ")
    assert _rgb(p.color_for(0, 0, 1)) == _rgb(_DEFAULT_FLAT)


def test_green_up_false_swaps_up_and_down():
    _seed("AAPL", price=110.0, prev=100.0)  # up
    p = StocksTrendColor(symbol="AAPL", green_up=False)
    assert _rgb(p.color_for(0, 0, 1)) == _rgb(pal.DOWN)  # up change -> down color


def test_color_overrides_applied():
    _seed("AAPL", price=110.0, prev=100.0)  # up
    p = StocksTrendColor(symbol="AAPL", up=[1, 2, 3])
    assert _rgb(p.color_for(0, 0, 1)) == (1, 2, 3)


def test_missing_symbol_raises():
    with pytest.raises(ValueError, match="symbol"):
        StocksTrendColor()


def test_fx_symbol_raises():
    with pytest.raises(ValueError, match="forex"):
        StocksTrendColor(symbol="EUR/USD")


@pytest.mark.parametrize("bad", [[300, 0, 0], [0, 0], [1, 2, "x"], [True, 0, 0]])
def test_bad_rgb_raises(bad):
    with pytest.raises(ValueError):
        StocksTrendColor(symbol="AAPL", up=bad)


def test_construction_registers_symbol():
    StocksTrendColor(symbol="MSFT")
    assert "MSFT" in _cache.get_cache()._symbols


def test_provider_flags():
    assert StocksTrendColor.per_char is False
    assert StocksTrendColor.frame_invariant is False
```

- [ ] **Step 2: Run tests — verify they FAIL (no module yet)**

Run: `uv run --extra dev pytest plugins/stocks/tests/test_trend_color.py -q`
Expected: collection error / ImportError (`trend_color` doesn't exist).

- [ ] **Step 3: Implement the provider**

Create `plugins/stocks/src/led_ticker_stocks/trend_color.py`:

```python
"""stocks.trend color provider: tint text by a symbol's day change.

Green (up) / red (down) / neutral (flat or no-data), read from the shared
QuoteCache. Whole-string provider. Requires a stocks.quote source or
stocks.ticker widget in the same config to feed the symbol — this provider
reads the cache but never starts it or performs I/O.
"""

from typing import Any

from led_ticker.plugin import Color, ColorProviderBase, make_color

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._cache import get_cache

_DEFAULT_FLAT: Color = make_color(150, 150, 150)  # neutral gray


def _coerce_rgb(value: Any, field: str) -> Color:
    if not (isinstance(value, (list, tuple)) and len(value) == 3):
        raise ValueError(f"stocks.trend '{field}' must be [r, g, b]; got {value!r}")
    if not all(isinstance(c, int) and not isinstance(c, bool) for c in value):
        raise ValueError(
            f"stocks.trend '{field}' components must be ints; got {list(value)!r}"
        )
    if not all(0 <= c <= 255 for c in value):
        raise ValueError(
            f"stocks.trend '{field}' RGB must be 0-255; got {list(value)!r}"
        )
    return make_color(*value)


class StocksTrendColor(ColorProviderBase):
    """Green up / red down / neutral flat, by a symbol's day change."""

    per_char: bool = False
    frame_invariant: bool = False  # tracks live data — re-evaluate each draw

    def __init__(
        self,
        symbol: Any = None,
        up: Any = None,
        down: Any = None,
        flat: Any = None,
        green_up: bool = True,
    ) -> None:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(
                "stocks.trend requires a non-empty 'symbol' string: "
                "font_color = {style = 'stocks.trend', symbol = 'AAPL'}"
            )
        if "/" in symbol:
            raise ValueError(
                f"stocks.trend symbol {symbol!r} looks like a forex pair; "
                "Finnhub's free tier is equities-only (forex requires a paid tier)."
            )
        self.symbol = symbol
        self._up = _coerce_rgb(up, "up") if up is not None else pal.UP
        self._down = _coerce_rgb(down, "down") if down is not None else pal.DOWN
        self._flat = _coerce_rgb(flat, "flat") if flat is not None else _DEFAULT_FLAT
        self._green_up = bool(green_up)
        # Join the symbol to the shared cache's union so it rides the poll loop
        # a source/widget starts (Phase-4 late-registrant catch-up covers this).
        # Does NOT start the cache — a provider has no session/async context.
        get_cache().register([symbol])

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        q = get_cache().get(self.symbol)
        chg = (q.change if q is not None else None) or 0
        up, down = (
            (self._up, self._down) if self._green_up else (self._down, self._up)
        )
        if chg > 0:
            return up
        if chg < 0:
            return down
        return self._flat
```

- [ ] **Step 4: Register the provider**

Modify `plugins/stocks/src/led_ticker_stocks/__init__.py`:

```python
"""led-ticker-stocks: equity ticker widget for led-ticker (Finnhub)."""

from led_ticker_stocks.source import StockSource
from led_ticker_stocks.ticker import StocksTicker
from led_ticker_stocks.trend_color import StocksTrendColor


def register(api):
    api.widget("ticker")(StocksTicker)
    api.source("quote")(StockSource)
    api.color_provider("trend")(StocksTrendColor)
```

- [ ] **Step 5: Run the unit tests — GREEN**

Run: `uv run --extra dev pytest plugins/stocks/tests/test_trend_color.py -q`
Expected: all PASS.

- [ ] **Step 6: Extend the registration smoke test**

Append to `plugins/stocks/tests/test_smoke.py` inside the existing `try:` block (after the source assertion, before `finally:`):

```python
        # color provider registered under the same namespace
        from led_ticker.color_providers import _PROVIDER_REGISTRY

        assert "stocks.trend" in _PROVIDER_REGISTRY

        # and it coerces from an inline font_color table
        from led_ticker.app.coercion import _coerce_color_provider

        prov = _coerce_color_provider({"style": "stocks.trend", "symbol": "AAPL"})
        assert prov is not None and prov.symbol == "AAPL"
```

- [ ] **Step 7: Full plugin suite + lint/format/pyright**

Run: `uv run --extra dev pytest plugins/stocks -q` then `uv run --extra dev ruff check plugins/stocks` and `uv run --extra dev ruff format --check plugins/stocks` and `uv run --extra dev pyright plugins/stocks/src/led_ticker_stocks/trend_color.py`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add plugins/stocks/src/led_ticker_stocks/trend_color.py plugins/stocks/src/led_ticker_stocks/__init__.py plugins/stocks/tests/test_trend_color.py plugins/stocks/tests/test_smoke.py
git commit -m "feat(stocks): stocks.trend color provider (green up / red down / neutral flat)"
```

---

### Task 2: Docs + example config

**Files:**
- Modify: `plugins/stocks/README.md` (a "Trend color" section)
- Modify: `plugins/stocks/CLAUDE.md` (an invariant for the provider + feeding requirement)
- Create: `plugins/stocks/examples/config.stocks-trend.smallsign.toml`

**Interfaces:** Consumes Task 1's `stocks.trend` provider + config surface.

- [ ] **Step 1: README "Trend color" section**

Add a section to `plugins/stocks/README.md` documenting: the `font_color = {style = "stocks.trend", symbol = "AAPL"}` usage; the field table (`symbol` required; `up`/`down`/`flat` `[r,g,b]` optional with defaults green/red/neutral-gray; `green_up` default true); that it tints the WHOLE message (whole-string), not per-token; and the **feeding requirement** — the symbol must be fed by a `stocks.quote` source or `stocks.ticker` widget in the same config (the provider reads the cache but doesn't start it); with no feeder the message renders the `flat` color. Cross-link the inline-price-tokens section. Match the README's existing voice.

- [ ] **Step 2: CLAUDE.md invariant**

Add an invariant to `plugins/stocks/CLAUDE.md`: `StocksTrendColor` is a whole-string `ColorProvider` (`per_char=False`, `frame_invariant=False`); mirrors `chg_color` (`chg>0→up`, `<0→down`, else flat; `green_up` flips); reads `get_cache().get(symbol)` and NEVER raises / NEVER starts the cache; registers the symbol at construction (rides the poll loop a feeder started, via the Phase-4 catch-up); config-load validation lives in `__init__` (raises `ValueError`). Tripwires: `tests/test_trend_color.py`.

- [ ] **Step 3: Example config**

Create `plugins/stocks/examples/config.stocks-trend.smallsign.toml` — a smallsign config with a `[[source]]` `stocks.quote` for AAPL feeding `:stocks.aapl:`, and a `message` with `text = "AAPL :stocks.aapl:"` + `font_color = {style = "stocks.trend", symbol = "AAPL"}`. Demo-friendly (no token needed — the shared cache runs demo, price walks up/down so the tint flips). Header comment: prereqs (core >= 4.9, led-ticker-stocks >= 0.5.0), the feeding requirement, and "what to look for" (message tints green when the demo price is up on the day, red when down). Validate: `uv run led-ticker validate <path>` → No issues found.

- [ ] **Step 4: Validate the example + commit**

Run: `uv run led-ticker validate plugins/stocks/examples/config.stocks-trend.smallsign.toml` (expect: No issues found).

```bash
git add plugins/stocks/README.md plugins/stocks/CLAUDE.md plugins/stocks/examples/config.stocks-trend.smallsign.toml
git commit -m "docs(stocks): stocks.trend color provider — README, invariant, example"
```

---

## Post-implementation (controller, not a task)

- **Visual GIF gate (required before merge):** render `examples/config.stocks-trend.smallsign.toml` (demo mode) and confirm the message tints green/red as the demo price walks, neutral on flat/no-data. (Requires the plugin installed in the render venv.)
- Final whole-branch review (opus), then open the PR. Release `stocks-v0.5.0` only on explicit user go-ahead.
