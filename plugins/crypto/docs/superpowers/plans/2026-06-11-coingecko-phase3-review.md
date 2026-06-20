# CoinGecko Plugin — Phase 3 Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make `led-ticker-crypto`'s `crypto.coingecko` widget correct and current against today's CoinGecko API, well tested, and add four approved enhancements (validate_config, demo-API-key, symbol→id auto-lookup, multi-coin).

**Architecture:** Localized correctness fixes first (adaptive price formatting; HTTP-status awareness), then a Container restructure so one widget can cycle several coins (one ticker "story" per coin, reusing the pixel-validated `draw_price_ticker`), with symbol→id auto-lookup (unique-or-error) and an optional demo-API-key header, gated by a `validate_config`. Backward compatible: an existing single `symbol`/`symbol_id` config still works.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest (asyncio_mode=auto), ruff. Import only `led_ticker.plugin`.

**Diagnostic basis (2026-06-10 live check):** price + coin-list API shapes UNCHANGED; `ids=[id]` encodes correctly as `ids=bitcoin`; keyless free tier rate-limits hard (429 after ~4 calls/min, `retry-after ~53s`); sub-cent prices render `0.0000`; 429 bodies are silently parsed as price data.

**Standing rules (every task):** work in worktree `/Users/james/projects/github/jamesawesome/ltc-phase3` (branch `feat/phase3-review`); run `git branch --show-current`, abort if `main`. Commit `--no-verify`. End commit messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No "footgun"/"gun" metaphors. Verify against the sibling `../led-ticker` (on main, has `compute_cursor`). Run `uv run pytest -q` + `uv run ruff check src tests` after each task. Do NOT push/PR/merge without controller instruction.

---

## Config schema (final shape, backward compatible)

```toml
[[playlist.section.widget]]
type = "crypto.coingecko"
currency = "USD"

# ONE of these coin-specification styles:
# (a) legacy single coin (still supported):
symbol = "BTC"
symbol_id = "bitcoin"
# (b) explicit ids (no lookup, unambiguous):
symbol_ids = ["bitcoin", "ethereum", "dogecoin"]
# (c) symbols, auto-resolved via /coins/list (unique-or-error):
symbols = ["BTC", "ETH"]

api_key = ""          # optional; or env COINGECKO_API_KEY -> x-cg-demo-api-key header
# unchanged render knobs: center, padding, hold_time, bg_color, font_color, update_interval
```

Resolution → an ordered list of `(display_symbol, coin_id)`: legacy `symbol`/`symbol_id` = one coin; each `symbol_ids` entry used directly (display = the id upper-cased unless a matching symbol known); each `symbols` entry auto-resolved (unique-or-error). At least one coin must be specified.

## File structure (final)

```
src/led_ticker_crypto/
  __init__.py        # register(api): api.widget("coingecko")(CoinGeckoMonitor) + validate_config
  coingecko.py       # CoinGeckoMonitor (Container: feed_title + feed_stories), _CoinTicker (per-coin story), update(), API client, auto-lookup
  _ticker_render.py  # draw_price_ticker (unchanged) + _format_price (new adaptive formatter)
  _colors.py         # unchanged
tests/
  test_coingecko.py      # expanded
  test_format_price.py   # new
  test_autolookup.py     # new
  test_import_purity.py / test_smoke.py  # unchanged
  conftest.py
tools/compare_render.py  # NOTE: imports core's deleted renderer — now stale post-#188; Task 0 handles it
```

---

## Task 0: Retire the now-stale pixel-compare tool

**Files:** Modify `tools/compare_render.py`; Modify `CLAUDE.md`.

`tools/compare_render.py` imports `led_ticker.widgets.crypto.coinbase._draw_price_ticker`, which #188 deleted from core — it can no longer run. It served its one-time Phase-1 purpose.

- [ ] **Step 1:** `git rm tools/compare_render.py`.
- [ ] **Step 2:** In `CLAUDE.md`, change the invariant line that says the renderer is "proven pixel-identical to core's original via `tools/compare_render.py`" to past tense: "was proven pixel-identical to core's original during extraction (PR history); core's renderer has since been removed." Keep the rest.
- [ ] **Step 3:** Commit.
```bash
git add -A && git commit --no-verify -m "chore: retire pixel-compare tool (core renderer removed in led-ticker#188)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## Task 1: Adaptive price formatting (fix sub-cent `0.0000`)

**Files:** Modify `src/led_ticker_crypto/_ticker_render.py`; Create `tests/test_format_price.py`.

- [ ] **Step 1: Write failing test** `tests/test_format_price.py`:
```python
from led_ticker_crypto._ticker_render import _format_price


def test_normal_price_keeps_four_decimals():
    assert _format_price(50000.1234) == "50,000.1234"
    assert _format_price(3000.5) == "3,000.5000"


def test_value_at_one_uses_four_decimals():
    assert _format_price(1.0) == "1.0000"


def test_sub_cent_shows_significant_figures_not_zero():
    s = _format_price(4.64e-06)
    assert s not in ("0.0000", "0")
    assert float(s.replace(",", "")) > 0
    # ~4 significant figures retained
    assert "4640" in s.replace(".", "").replace(",", "")


def test_zero_is_zeroed():
    assert _format_price(0.0) == "0.0000"


def test_small_but_above_one_cent():
    assert _format_price(0.1234) == "0.1234"
```
- [ ] **Step 2: Run, expect FAIL** (`_format_price` undefined): `uv run pytest tests/test_format_price.py -q`.
- [ ] **Step 3: Implement** in `_ticker_render.py` (add near the top, after imports):
```python
import math


def _format_price(value: float) -> str:
    """Format a price with adaptive precision.

    Normal coins (>= 1) keep the historical 4-decimal, thousands-separated form.
    Sub-dollar coins get extra decimals so cheap tokens (e.g. SHIB ~4.6e-06)
    don't collapse to "0.0000".
    """
    if value >= 1 or value == 0:
        return f"{value:,.4f}"
    # ~4 significant figures for small magnitudes, capped at 12 decimals.
    decimals = min(12, max(4, 3 - int(math.floor(math.log10(abs(value))))))
    return f"{value:.{decimals}f}"
```
- [ ] **Step 4: Run, expect PASS.** `uv run pytest tests/test_format_price.py -q`.
- [ ] **Step 5: Commit** (the `update()` call site is rewired in Task 3; for now `_format_price` is standalone). `git add -A && git commit --no-verify -m "feat: adaptive price formatting (fix sub-cent prices rendering as 0.0000)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

## Task 2 & 3: Restructure to a Container with HTTP-status awareness, multi-coin, auto-lookup, demo-key

This is the core structural task — done as one coherent rewrite of `coingecko.py` because the data model (single coin → coin list), the Container shape, auto-lookup, status handling, demo-key header, and adaptive formatting all touch the same fetch/update/draw path. Implement carefully and TDD the behaviors.

**Files:** Rewrite `src/led_ticker_crypto/coingecko.py`; Modify `src/led_ticker_crypto/__init__.py`; Modify `tests/test_coingecko.py`; Create `tests/test_autolookup.py`.

### Design

- **`_CoinTicker(FrameAwareBase)`** — a per-coin "story" widget. Fields: `symbol: str`, `currency: str`, render knobs (`center`, `padding`, `bg_color`, `font_color`), and mutable `price_data: dict[str,str]` (default `{"price": "0.0000", "change_24h": "0.00%"}`). Its `draw()` is exactly today's `CoinGeckoPriceMonitor.draw` (delegates to `draw_price_ticker`). `__attrs_post_init__` does the font_color coercion (today's logic).
- **`CoinGeckoMonitor`** — a Container. Holds the resolved `coins: list[tuple[str,str]]` (display_symbol, coin_id), `currency`, `session`, `api_key`, render knobs, and:
  - `feed_title: Widget | None` (None — no title needed)
  - `feed_stories: list[_CoinTicker]` (one per coin, rebuilt each `update()`)
  - `update()`: ONE batched call `GET /simple/price?ids=<comma-joined ids>&vs_currencies=<cur>&include_24hr_change=true` (comma-joined STRING, not a list — aiohttp would emit repeated keys which CoinGecko rejects for multiple ids). Status-checked. Parses each coin into the matching story's `price_data` using `_format_price`.
  - `start()`: resolves the coin list (auto-lookup for `symbols`), builds the stories, does the initial `update()`, spawns `run_monitor_loop`.
- **Auto-lookup** `_resolve_symbols(symbols, coin_list) -> list[tuple[str,str]]`: for each symbol, find matching ids (case-insensitive on `coin_meta["symbol"]`); exactly one → use it; zero → raise `ValueError(f"symbol {sym!r} not found on CoinGecko")`; multiple → raise `ValueError` listing candidate ids and instructing the user to set `symbol_ids`/`symbol_id` explicitly. (unique-or-error)
- **Demo-key**: if `api_key` set (config or `COINGECKO_API_KEY` env), send header `{"x-cg-demo-api-key": api_key}` on both the price and coin-list requests.
- **Status handling**: after each request, `if response.status != 200:` log a warning naming the status (and `retry-after` if present on 429), then `response.raise_for_status()` so `run_monitor_loop`'s backoff engages instead of parsing an error body as prices.

- [ ] **Step 1: Write failing tests.** Add to `tests/test_coingecko.py` (keep the existing render-helper + protocol tests, update widget construction to the new `CoinGeckoMonitor`/`_CoinTicker`), and create `tests/test_autolookup.py`. Concretely:

`tests/test_autolookup.py`:
```python
import pytest

from led_ticker_crypto.coingecko import _resolve_symbols

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
```

Add to `tests/test_coingecko.py` (new behaviors — write against the new API):
```python
# multi-coin update parses each coin into its story
async def test_update_parses_multiple_coins():
    session = _mock_session({
        "bitcoin": {"usd": 50000.0, "usd_24h_change": 1.0},
        "ethereum": {"usd": 3000.0, "usd_24h_change": -2.0},
    })
    w = CoinGeckoMonitor(
        coins=[("BTC", "bitcoin"), ("ETH", "ethereum")],
        currency="USD", session=session,
    )
    await w.update()
    prices = {s.symbol: s.price_data["price"] for s in w.feed_stories}
    assert prices["BTC"] == "50,000.0000"
    assert prices["ETH"] == "3,000.0000"

# 429 is not parsed as price data and triggers backoff (raises)
async def test_non_200_raises_for_backoff():
    import aiohttp
    session = _mock_session({"status": {"error_code": 429}}, status=429)
    w = CoinGeckoMonitor(coins=[("BTC", "bitcoin")], currency="USD", session=session)
    with pytest.raises(aiohttp.ClientResponseError):
        await w.update()
    # stale price preserved (not overwritten with garbage)
    assert w.feed_stories[0].price_data["price"] == "0.0000"

# sub-cent coin renders via adaptive formatting
async def test_sub_cent_coin_formats_nonzero():
    session = _mock_session({"shiba-inu": {"usd": 4.64e-06, "usd_24h_change": 5.0}})
    w = CoinGeckoMonitor(coins=[("SHIB", "shiba-inu")], currency="USD", session=session)
    await w.update()
    assert w.feed_stories[0].price_data["price"] not in ("0.0000", "0")

# ids are comma-joined (string), not a list, in the request
async def test_ids_param_is_comma_joined_string():
    captured = {}
    session = _mock_session({"bitcoin": {"usd": 1.0, "usd_24h_change": 0.0},
                             "ethereum": {"usd": 1.0, "usd_24h_change": 0.0}},
                            capture=captured)
    w = CoinGeckoMonitor(coins=[("BTC", "bitcoin"), ("ETH", "ethereum")],
                         currency="USD", session=session)
    await w.update()
    assert captured["params"]["ids"] == "bitcoin,ethereum"

# demo api key -> header
async def test_api_key_sets_demo_header():
    captured = {}
    session = _mock_session({"bitcoin": {"usd": 1.0, "usd_24h_change": 0.0}}, capture=captured)
    w = CoinGeckoMonitor(coins=[("BTC", "bitcoin")], currency="USD",
                         session=session, api_key="demo-123")
    await w.update()
    assert captured["headers"]["x-cg-demo-api-key"] == "demo-123"

# container conformance
def test_is_container_with_stories():
    w = CoinGeckoMonitor(coins=[("BTC", "bitcoin")], currency="USD", session=mock.Mock())
    assert isinstance(w.feed_stories, list)
    from led_ticker.plugin import Widget
    assert all(isinstance(s, Widget) for s in w.feed_stories)
```
Add a `_mock_session(json_body, status=200, capture=None)` helper to `tests/test_coingecko.py` that returns a Mock whose `.get(url, params=, headers=)` records into `capture` and yields an async-context response with `.status`, `.json()`, and a `.raise_for_status()` that raises `aiohttp.ClientResponseError` when status != 200 (mirror aiohttp's behavior). Use the existing async-context mock shape already in the file as the base.

- [ ] **Step 2: Run, expect FAIL.** `uv run pytest tests/test_coingecko.py tests/test_autolookup.py -q`.

- [ ] **Step 3: Implement `coingecko.py`** (rewrite). Key pieces (write the full module — the per-coin story, the container, the resolver, the client):
  - `_CoinTicker(FrameAwareBase)` with `draw()` delegating to `draw_price_ticker` (today's `draw` body, using `self.symbol`, `self.price_data`).
  - `_resolve_symbols(symbols, coin_list)` — unique-or-error as specified.
  - `_build_coins(symbol, symbol_id, symbols, symbol_ids, coin_list)` — assemble the ordered `(display, id)` list from the four config inputs; raise if none given.
  - `CoinGeckoMonitor` container: `update()` issues ONE `session.get(COINGECKO_PRICE_API, params={"ids": ",".join(ids), "vs_currencies": currency, "include_24hr_change": "true"}, headers=self._headers())`; status-check + `raise_for_status()`; parse into stories via `_format_price`. `_headers()` returns `{"x-cg-demo-api-key": self.api_key}` when `api_key` else `{}`.
  - `start(cls, ...)`: if `symbols` given, fetch `/coins/list` (with headers) and resolve; build coins; construct stories; `await self.update()`; `spawn_tracked(run_monitor_loop(self, update_interval))`.
  - `api_key` default: `attrs.field(factory=lambda: os.getenv("COINGECKO_API_KEY", ""), kw_only=True)`.
  - Preserve `run_monitor_loop`/`spawn_tracked`/`FrameAwareBase` usage. Keep the `valid = {f.name ...}` kwarg filter in `start()`.

- [ ] **Step 4: Update `__init__.py`** — registration unchanged (`api.widget("coingecko")(CoinGeckoMonitor)`); rename the imported class to `CoinGeckoMonitor`.

- [ ] **Step 5: Run, expect PASS.** `uv run pytest -q` (all, including the existing suite adapted). Fix until green. `uv run ruff check src tests`.

- [ ] **Step 6: Commit.** `git add -A && git commit --no-verify -m "feat: multi-coin container, symbol auto-lookup, demo-key, HTTP-status backoff\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

## Task 4: `validate_config` + register it

**Files:** Modify `src/led_ticker_crypto/coingecko.py` (or `__init__.py`); Modify `tests/test_coingecko.py`.

- [ ] **Step 1: Write failing tests** (add to `tests/test_coingecko.py`):
```python
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
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** a `validate_config(cls, cfg) -> list[str]` classmethod on `CoinGeckoMonitor` (the `led_ticker.plugin` contract — returns messages, engine raises): returns a message if NONE of `symbol`/`symbol_id`/`symbols`/`symbol_ids` is present (at least one coin required); optionally validate `currency` is a non-empty string and `symbols`/`symbol_ids` are lists of strings. Keep it minimal (match baseball's return-list style).
- [ ] **Step 4: Run, expect PASS.** `uv run pytest -q`; `uv run ruff check src tests`.
- [ ] **Step 5: Commit.** `git add -A && git commit --no-verify -m "feat: validate_config for the coingecko widget (require at least one coin)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

## Task 5: Docs — README + CLAUDE.md for the new surface

**Files:** Modify `README.md`, `CLAUDE.md`.

- [ ] **Step 1:** Update `README.md`: the options table gains `symbols`, `symbol_ids`, `api_key`; document the three coin-spec styles + that `symbols` auto-resolves (unique-or-error, set `symbol_id`/`symbol_ids` to disambiguate); note `COINGECKO_API_KEY` env + the free-tier rate limit (≈5/min keyless) and that a free demo key raises it; keep the "Finding symbol_id" section but frame it as the disambiguation/override path. Add a multi-coin TOML example.
- [ ] **Step 2:** Update `CLAUDE.md` invariants: the widget is now a Container (`feed_stories` per coin, cycled by the engine); `ids` MUST be comma-joined (aiohttp list = repeated keys, which CoinGecko rejects for multiple); non-200 raises for `run_monitor_loop` backoff (429 must not be parsed as prices); `_format_price` adaptive precision; auto-lookup is unique-or-error; demo-key header `x-cg-demo-api-key`.
- [ ] **Step 3: Commit.** `git add -A && git commit --no-verify -m "docs: README + CLAUDE.md for multi-coin / auto-lookup / demo-key surface\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

## Task 6: Full verification

- [ ] **Step 1:** `uv run pytest -q` — all green; confirm the new tripwires (sub-cent, 429-backoff, comma-joined ids, ambiguous-symbol, container) pass.
- [ ] **Step 2:** `uv run ruff check src tests` — clean.
- [ ] **Step 3:** Smoke the entry point: `uv run python -c "from led_ticker import _plugin_loader as L; L.reset_plugins(); r=L.load_plugins(None, entry_points_enabled=True); from led_ticker.widgets import get_widget_class; print(get_widget_class('crypto.coingecko')); L.reset_plugins()"`.
- [ ] **Step 4:** (controller) push `feat/phase3-review`, open a PR on led-ticker-crypto, confirm CI green (deploy key is now set), hold for user merge.

---

## Self-review notes
- **Diagnostic coverage:** sub-cent bug → Task 1; 429/status → Task 2&3 (status handling + test); test gaps → Tasks 1–4 tests; enhancements validate_config/demo-key/auto-lookup/multi-coin → Tasks 2&3 + 4. The stranded `_find_coingecko_symbol_id` is replaced by `_resolve_symbols` (unique-or-error). The latent `ids`-list issue is fixed by comma-joining.
- **Back-compat:** legacy `symbol`/`symbol_id` still yields a one-coin container (Task 2&3 `_build_coins`).
- **Name consistency:** `CoinGeckoMonitor` (renamed from `CoinGeckoPriceMonitor`) used in `__init__.py`, all tests, validate_config; `_CoinTicker`, `_resolve_symbols`, `_build_coins`, `_format_price` consistent across tasks.
- **Render fidelity preserved:** `_CoinTicker.draw` still calls `draw_price_ticker` (the Phase-1-validated renderer); only the formatting input (`_format_price`) changes, and only for sub-dollar values.
