# Stocks State-Dimming Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Twelve Data wall-clock state refinement (state is data, never fabricated) and soften the shared CLOSED dim from 0.45 to 0.70 for both providers, keeping the `dim_by_state` opt-out knob exactly as built.

**Architecture:** All changes live in `plugins/stocks`. The quote parser returns to reporting TD's binary `is_market_open` verbatim; the presentation change is a single constant in the shared `STATE_META` table that every layout already reads. Spec: `docs/superpowers/specs/2026-07-17-stocks-state-dimming-redesign.md`.

**Tech Stack:** Python 3.14, pytest, attrs. Monorepo working copy: `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `stocks-state-dimming` (PR #58 — amended in place; branch already has origin/main merged).

## Global Constraints

- Work ONLY on branch `stocks-state-dimming`; run `git branch --show-current` first and abort if it prints anything else (never main).
- CLOSED dim value is exactly `0.70`; ordering `OPEN 1.0 > PRE 0.85 == AFTER 0.85 > CLOSED 0.70` must hold.
- `state.py`'s `state_from_clock` / `state_now_from_clock` functions are NOT deleted or modified — the Finnhub status-fetch fallback still consumes them.
- The `dim_by_state` knob (widget field, `_StockStory`, `start()`, all three layout kwargs) is NOT modified.
- No `from __future__ import annotations` (project rule).
- Test command: `uv run --extra dev pytest plugins/stocks/tests/ -q` from the monorepo root. Lint: `uv run --extra dev ruff check plugins/stocks/` and `uv run --extra dev ruff format --check plugins/stocks/`.

---

### Task 1: Revert the TD clock refinement — state reported verbatim

**Files:**
- Modify: `plugins/stocks/src/led_ticker_stocks/twelvedata.py` (imports + `parse_quote`)
- Modify: `plugins/stocks/tests/test_twelvedata.py` (replace `TestClosedEquityClockRefinement`)

**Interfaces:**
- Consumes: `MarketState` from `led_ticker_stocks.state` (unchanged).
- Produces: `parse_quote(sym, payload) -> SymbolQuote` whose `.state` is only ever `MarketState.OPEN` or `MarketState.CLOSED`. Task 2+ rely on no other TD states existing.

- [ ] **Step 1: Replace the clock-refinement test class with the verbatim-binary class**

In `plugins/stocks/tests/test_twelvedata.py`, delete the entire `class TestClosedEquityClockRefinement:` block (its docstring, `_closed` helper, and all six test methods — everything from `class TestClosedEquityClockRefinement:` through the end of `test_clock_failure_degrades_to_closed_not_raising`). In its place put:

```python
class TestClosedIsVerbatim:
    """TD's binary is_market_open is reported VERBATIM — the 2026-07-17
    redesign removed the wall-clock PRE/AH refinement (state is data; the
    gentler closed look now lives in STATE_META's 0.70 CLOSED dim). This
    also makes parsing deterministic: the old refinement made closed-equity
    tests time-of-day dependent."""

    def _payload(self, is_open):
        return {
            "symbol": "AAPL",
            "close": "208.89",
            "previous_close": "210.35",
            "is_market_open": is_open,
        }

    def test_closed_stays_closed_at_any_runtime_clock(self):
        q = parse_quote("AAPL", self._payload(False))
        assert q.state is MarketState.CLOSED

    def test_open_maps_to_open(self):
        q = parse_quote("AAPL", self._payload(True))
        assert q.state is MarketState.OPEN

    def test_module_has_no_clock_dependency(self):
        """The parser must not import the wall clock — refinement must not
        quietly return."""
        import led_ticker_stocks.twelvedata as td

        assert not hasattr(td, "state_now_from_clock")
```

(`parse_quote` and `MarketState` are already imported at the top of the test file.)

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run --extra dev pytest plugins/stocks/tests/test_twelvedata.py -q`
Expected: `test_module_has_no_clock_dependency` FAILS (the module still has `state_now_from_clock`). `test_closed_stays_closed_at_any_runtime_clock` may pass or fail depending on the actual time of day — that nondeterminism is exactly what this task removes.

- [ ] **Step 3: Revert `parse_quote` and the import**

In `plugins/stocks/src/led_ticker_stocks/twelvedata.py`:

Change the import line

```python
from led_ticker_stocks.state import MarketState, state_now_from_clock
```

to

```python
from led_ticker_stocks.state import MarketState
```

Replace the whole state block inside `parse_quote` — from `if payload.get("is_market_open"):` down through the final `state = clock` line (including the KNOWN APPROXIMATIONS comment block and the `"/" not in sym` refinement) — with:

```python
    # TD reports only open/closed per symbol (no pre/after-hours sessions).
    # That binary is reported VERBATIM — no wall-clock refinement (state is
    # data; the closed-look policy lives in STATE_META's dim values). See
    # docs/superpowers/specs/2026-07-17-stocks-state-dimming-redesign.md.
    state = MarketState.OPEN if payload.get("is_market_open") else MarketState.CLOSED
```

The `return SymbolQuote(...)` call that follows is unchanged.

- [ ] **Step 4: Run the twelvedata tests to verify they pass**

Run: `uv run --extra dev pytest plugins/stocks/tests/test_twelvedata.py -q`
Expected: ALL PASS (including the pre-existing `test_parse_sets_open_state_from_is_market_open`, now deterministic).

- [ ] **Step 5: Commit**

```bash
git add plugins/stocks/src/led_ticker_stocks/twelvedata.py plugins/stocks/tests/test_twelvedata.py
git commit -m "revert(stocks): drop TD wall-clock state refinement — is_market_open reported verbatim"
```

---

### Task 2: Soften CLOSED dim to 0.70 + ordering tripwire + ratio-bound fixes

**Files:**
- Modify: `plugins/stocks/src/led_ticker_stocks/state.py` (one `STATE_META` entry)
- Modify: `plugins/stocks/tests/test_state.py` (assertion + new tripwire)
- Modify: `plugins/stocks/tests/test_card.py` (luminance ratio bound — WILL FAIL at 0.70 without this)
- Modify: `plugins/stocks/tests/test_render_smoke.py` (ratio bound margin + docstrings)

**Interfaces:**
- Consumes: `STATE_META` dict shape from `state.py` (unchanged shape).
- Produces: `STATE_META[MarketState.CLOSED].dim == 0.70`. Task 3's doc text states 70%.

- [ ] **Step 1: Update the dim assertions and add the ordering tripwire**

In `plugins/stocks/tests/test_state.py`, in `test_state_meta_dims_and_labels`, change

```python
    assert STATE_META[MarketState.CLOSED].dim == 0.45
```

to

```python
    assert STATE_META[MarketState.CLOSED].dim == 0.70
```

and add below that function:

```python
def test_state_meta_dim_ordering():
    """Brightness semantics tripwire: LIVE brightest, extended-hours middle,
    closed dimmest. A future dim tweak must not silently invert this."""
    assert (
        STATE_META[MarketState.OPEN].dim
        > STATE_META[MarketState.PRE].dim
        == STATE_META[MarketState.AFTER].dim
        > STATE_META[MarketState.CLOSED].dim
    )
```

- [ ] **Step 2: Run test_state to verify the 0.70 assertion fails**

Run: `uv run --extra dev pytest plugins/stocks/tests/test_state.py -q`
Expected: `test_state_meta_dims_and_labels` FAILS (`0.45 != 0.70`); `test_state_meta_dim_ordering` PASSES (ordering already holds at 0.45).

- [ ] **Step 3: Change the constant**

In `plugins/stocks/src/led_ticker_stocks/state.py`, replace

```python
    MarketState.CLOSED: StateMeta(0.45, "CLSD", (255, 60, 60), False),
```

with

```python
    # CLOSED at 0.70 (was 0.45): with per-symbol state under Twelve Data a
    # mixed rotation shows LIVE and CLOSED cards side by side, and 45% read
    # as a broken panel at storefront distance. 0.70 keeps the ordering
    # OPEN 1.0 > PRE/AH 0.85 > CLOSED 0.70 while staying clearly readable.
    MarketState.CLOSED: StateMeta(0.70, "CLSD", (255, 60, 60), False),
```

- [ ] **Step 4: Fix the two luminance-ratio bounds that assume 0.45**

In `plugins/stocks/tests/test_card.py`, in `test_dim_by_state_false_renders_closed_at_full_brightness`: the true undimmed/dimmed ratio is now ~1/0.70 ≈ 1.43, so the existing `* 1.5` bound fails. Change

```python
    assert _lum(False) > _lum(True) * 1.5, (
        "undimmed CLOSED card must be substantially brighter"
    )
```

to

```python
    # True ratio ≈ 1/0.70 ≈ 1.43; 1.25 leaves margin for rounding while
    # still proving the knob is not a no-op.
    assert _lum(False) > _lum(True) * 1.25, (
        "undimmed CLOSED card must be substantially brighter"
    )
```

and in its docstring change `the 45% dim goes` to `the state dim goes`.

In `plugins/stocks/tests/test_render_smoke.py`, in `test_state_dimming_lowers_total_brightness`: the true CLOSED/OPEN ratio is now ~0.70, so the existing `* 0.75` bound passes with almost no margin. Change

```python
    # Roughly matches the 0.45/1.0 palette dim ratio; loose bound to tolerate
    # font antialiasing / rounding — just confirms it's not a no-op scale.
    assert brightness_closed < brightness_open * 0.75
```

to

```python
    # Roughly matches the 0.70/1.0 palette dim ratio; loose bound to tolerate
    # font antialiasing / rounding — just confirms it's not a no-op scale.
    assert brightness_closed < brightness_open * 0.85
```

Also update that test's docstring `CLOSED (dim=0.45)` to `CLOSED (dim=0.70)` and its assertion message `expected CLOSED (dim=0.45) brightness` to `expected CLOSED (dim=0.70) brightness`.

- [ ] **Step 5: Run the affected test files to verify all pass**

Run: `uv run --extra dev pytest plugins/stocks/tests/test_state.py plugins/stocks/tests/test_card.py plugins/stocks/tests/test_render_smoke.py -q`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/stocks/src/led_ticker_stocks/state.py plugins/stocks/tests/test_state.py plugins/stocks/tests/test_card.py plugins/stocks/tests/test_render_smoke.py
git commit -m "feat(stocks): soften shared CLOSED dim 0.45 -> 0.70 + dim-ordering tripwire"
```

---

### Task 3: Docs and example-config collateral

**Files:**
- Modify: `plugins/stocks/README.md` (`dim_by_state` table row)
- Modify: `plugins/stocks/examples/config.stocks-multiasset.longboi.toml` (item 2b)
- Modify: `plugins/stocks/examples/config.stocks-multiasset.bigsign.toml` (item 2b)
- Modify: `plugins/stocks/examples/config.stocks-smoke.longboi.toml` (dim mention)
- Modify: `plugins/stocks/examples/config.stocks-smoke.bigsign.toml` (dim mention)

**Interfaces:**
- Consumes: the 0.70 value from Task 2. No code produced.

- [ ] **Step 1: Rewrite the README `dim_by_state` row (drop the removed-behavior caveats)**

In `plugins/stocks/README.md`, replace the entire `dim_by_state` table row with:

```markdown
| `dim_by_state` | bool | `true` | Layouts dim by market state: LIVE 100%, pre/after-hours 85% (Finnhub's status feed reports those sessions; Twelve Data reports only open/closed), closed 70%. With per-symbol state under Twelve Data, a mixed rotation alternates bright and dim — informative, but set `false` for uniform full brightness (the LIVE/CLSD chip still carries the state). |
```

- [ ] **Step 2: Rewrite item 2b in both multiasset smoke configs**

In `plugins/stocks/examples/config.stocks-multiasset.longboi.toml` AND `plugins/stocks/examples/config.stocks-multiasset.bigsign.toml`, replace the six 2b comment lines (`#   2b BRIGHTNESS FOLLOWS STATE — closed cards render dimmer (45%) than` through `#                    brightness (the chip keeps the LIVE/CLSD info).`) with:

```
#   2b BRIGHTNESS FOLLOWS STATE — closed cards render dimmer (70%) than
#                    LIVE ones (100%). Twelve Data reports only open/closed,
#                    so there is no PRE/AH tier here. Mixed bright/dim across
#                    the rotation is the state signal, not a fault; set
#                    dim_by_state = false on the widget for uniform
#                    brightness (the chip keeps the LIVE/CLSD info).
```

- [ ] **Step 3: Update the Finnhub smoke configs' dim numbers**

In `plugins/stocks/examples/config.stocks-smoke.longboi.toml` change `CLOSED ~0.45 dim, frozen` to `CLOSED ~0.70 dim, frozen`.
In `plugins/stocks/examples/config.stocks-smoke.bigsign.toml` change `CLOSED ~0.45 dimmest + "AT CLOSE", frozen` to `CLOSED ~0.70 dimmest + "AT CLOSE", frozen`.

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -rn "0\.45\|45%" plugins/stocks/src plugins/stocks/examples plugins/stocks/README.md`
Expected: the ONLY hit is `layouts/_common.py:29` (`0.55 + 0.45 * math.sin(...)` — the pulse waveform, unrelated to dim). Any other hit is a missed reference; fix it.

- [ ] **Step 5: Commit**

```bash
git add plugins/stocks/README.md plugins/stocks/examples/
git commit -m "docs(stocks): CLOSED dim 70% in README + smoke-config expectations; drop clock-refinement caveats"
```

---

### Task 4: Full verification and PR update

**Files:**
- No new files; runs the suite, lint, push, and PR-body update.

- [ ] **Step 1: Full stocks suite**

Run: `uv run --extra dev pytest plugins/stocks/tests/ -q`
Expected: ALL PASS (≈227: 230 at #58 head, −6 clock tests, +3 verbatim tests; exact count may differ slightly — zero failures is the requirement).

- [ ] **Step 2: Lint**

Run: `uv run --extra dev ruff check plugins/stocks/ && uv run --extra dev ruff format --check plugins/stocks/`
Expected: clean. Fix and re-run if not.

- [ ] **Step 3: Push the branch**

```bash
git push origin stocks-state-dimming
```

- [ ] **Step 4: Update PR #58 title/body to match the redesign**

Update the PR so it describes what will merge: title `feat(stocks): market-state dimming — softer CLOSED (70%) + dim_by_state knob`. Body must state: (1) state is data — TD's binary reported verbatim, clock refinement removed per the spec; (2) shared CLOSED dim 0.45→0.70, both providers, ordering tripwire added; (3) `dim_by_state` opt-out knob unchanged; (4) link `docs/superpowers/specs/2026-07-17-stocks-state-dimming-redesign.md`; (5) the standing "Test on the sign" section with the branch-ref requirements-plugins.txt line:

```
## Test on the sign

In `config/requirements-plugins.txt`:

    led-ticker-stocks @ git+https://github.com/JamesAwesome/led-ticker-plugins.git@stocks-state-dimming#subdirectory=plugins/stocks

then `docker compose down -v && docker compose up -d` (the `-v` refresh is required so reconcile reinstalls the branch build).
```

Use `gh pr edit 58 --title ... --body-file <tmpfile>` (body via file — parens/backticks break `-m`-style args).

- [ ] **Step 5: Report CI status**

Run: `gh pr checks 58 --watch` (or poll `gh pr checks 58`).
Expected: all checks green. Do NOT merge — merging requires explicit user go-ahead.
