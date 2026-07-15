# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-stocks**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install,
rate limits, FX limitation, demo mode). This file keeps the **load-bearing invariants** a
contributor must respect, plus navigation aids. When a fact here and the README disagree
about *how a feature works*, the README wins; this file is the source of truth for *how to
keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `stocks.ticker` — live equity price Container from the Finnhub REST API. Cycles one
  `_StockStory` "story" per configured symbol (the engine reads `feed_stories` via
  `_expand_sources` on every pass). Trend-colored green/red, dimmed by market state. Three
  layouts are registered and auto-selected by real panel width: `crawl` (smallsign,
  scrolling), `card` (bigsign, held), `dashboard` (longboi, held) — see the README's
  [Layouts](README.md#layouts) section for the user-facing shape of each.

The entry-point name `stocks` is the plugin namespace, so the config `type` is
`stocks.ticker` (see `register()` in `__init__.py`).

## Commands

`led-ticker-core` resolves from PyPI (`>=4.9`) like any other dependency — no sibling
checkout, no `[tool.uv.sources]`, no deploy key. Tests that need a headless canvas obtain
one via `HeadlessBackend(...).create_canvas()` from `led_ticker.plugin` — no rgbmatrix stub
on the path.

```bash
uv sync --extra dev                          # install deps (led-ticker-core from PyPI)
uv run pytest --cov=led_ticker_stocks -q     # full suite, coverage gate fail_under = 90
uv run ruff check src/ tests/                # or: make lint (monorepo root)
uv run ruff format --check src/ tests/
uv run pyright src
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_stocks/
  __init__.py         # register(api) → api.widget("ticker")(StocksTicker)
  ticker.py            # StocksTicker (Container): validate_config(), start(), update();
                       #   _StockStory: per-symbol story reading the shared quote dict
  finnhub.py           # FinnhubClient (quote + market-status GETs); parse_quote()
  model.py             # SymbolQuote + format_price/format_change/format_pct
  state.py             # MarketState enum + STATE_META (dim/label/color/pulses) +
                       #   state_from_status() (Finnhub) + state_from_clock()/
                       #   state_now_from_clock() (US/Eastern wall-clock fallback, wired
                       #   into update()'s market-status except branch)
  demo.py              # DemoFeed: seeded offline random-walk feed for demo=true / no-token
  _palette.py           # Semantic RGB palette (SYM/PRICE/UP/DOWN/FLAT/LABEL) + dim()
  _paint.py             # phys_wrap() (scale-1 ScaledCanvas shim) + hires()/right_align_x()/
                        #   px()/paging_dots() physical-pixel paint helpers for card/dashboard
  _chip.py              # draw_chip(): abstract two-tone brand chip (hash-of-symbol colors)
  _sparkline.py         # draw_sparkline(): prev-close reference + up/down trend line
  layouts/
    __init__.py         # LAYOUTS registry ({"crawl", "card", "dashboard"}) + resolve_layout()
    _common.py           # shared arrow()/chg_color()/flash_price_color()/live_pulse()/
                         #   endpoint_pulse() used by card.py + dashboard.py (crawl.py also
                         #   uses flash_price_color())
    crawl.py             # draw_crawl_story(): smallsign scrolling line (Phase 1)
    card.py              # draw_card_story(): bigsign held hero card (Phase 2)
    dashboard.py         # draw_dashboard_story(): longboi held dashboard + watch column (Phase 2)
```

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("ticker")(StocksTicker)
```

## Load-bearing invariants

Each rule must hold when modifying the named files.

**Import only the public surface** — every `led_ticker` import MUST come from
`led_ticker.plugin`, never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`,
which AST-walks every source file. Intra-package imports
(`from led_ticker_stocks._palette import …`) are fine.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as
core). Bare `dict[str, SymbolQuote]` / `tuple` annotations are fine.

**`StocksTicker` is a Container** — it exposes `feed_stories: list[_StockStory]` (one story
per symbol), all reading a SHARED `self._quotes: dict[str, SymbolQuote]` mutated in place by
`update()`. The engine reads `feed_stories` via `_expand_sources` on every pass, so a price
update surfaces within at most one cycle. **Never** snapshot `feed_stories` into a cycle
iterator, and never give each `_StockStory` its own copy of a quote — that was the longboi
stale-display pattern (a container that updates correctly in the background but a frozen
snapshot never sees it). `_StockStory.quotes` and `state_ref` are the SAME dict/list object
handed to every story and mutated by `StocksTicker.update()`; a story never owns its data.

**Token is env-only, never a `start()` parameter** — `StocksTicker.start()` deliberately does
NOT declare a `token` parameter. Core's widget factory unions a Container's `start()` keyword
signature into the set of config keys it will bind, so if `token` were a `start()` parameter,
a user's `token = "..."` in `config.toml` would silently override the env secret and flow
straight into Finnhub HTTP requests — exactly the leak `resolve_secret_token` /
"secrets belong in `.env`" is meant to prevent. `start()` always resolves
`os.getenv("FINNHUB_API_TOKEN", "")` itself. Defense in depth: even if a stray `token` arrives
via `start(**kwargs)` (e.g. a future config field collision), it is explicitly filtered out of
the `cls(...)` call (`k != "token"`) before the resolved env value is applied last, so a
config-supplied value can never win. Tripwires: `test_config_token_is_ignored`,
`test_config_token_is_ignored_no_env` (`tests/test_ticker.py`).

**Empty token silently routes to demo, not an error** — `__attrs_post_init__` treats
`self.demo or not self.token` as one condition: `demo = true` OR a missing/empty
`FINNHUB_API_TOKEN` both land on the exact same `DemoFeed` path. This is intentional (a sign
that forgot to set the env var boots with a visible, moving placeholder rather than a
dead/erroring widget) — do not turn "no token" into a hard failure without updating the
README's demo-mode section, which documents this fallback as the recommended smoke-test path.

**Rate rule: `effective_interval = max(update_interval, len(symbols) + 1)`** — computed once
in `start()` before construction and stored as `self.update_interval` (passed to
`run_monitor_loop`). Each `update()` costs `len(symbols) + 1` Finnhub requests (1 status +
1-per-symbol quote) while the market is open, or exactly **1** while closed (see the no-quote-
calls-when-closed rule below). Finnhub's free tier is 60 req/min **per API key**, not per
widget instance — the README's rate-limit section documents that two signs or two
Finnhub-backed widgets sharing one token divide the same budget; this code cannot see or
enforce that cross-widget sharing, only the single-widget floor. `start()` also logs ONE
`logging.warning` when `len(symbols) > SYMBOL_SOFT_CAP` (20) noting the free-tier 60/min
budget and the `max(update_interval, N+1)` cadence — advisory only, does not clamp or reject.

**No quote calls while the market is closed** — `update()` always fetches market status
first; if `state_from_status(...)` resolves to `MarketState.CLOSED` it returns immediately
without calling `fetch_quote` for any symbol (comment: "frozen when closed — hold last
prices"). This is both a rate-budget optimization (1 request instead of `N+1`) and the
correct product behavior (equity prices don't change when the exchange is shut). Don't add a
"keep polling anyway" mode without updating the rate-rule math above.

**No-data guard: `pc == 0` (or `c == 0`) never divides** — `SymbolQuote.has_data` is
`self.prev != 0 and self.price != 0`; `change`/`pct` both return `None` — never attempt
`(price - prev) / prev` — whenever `has_data` is false. `parse_quote` maps a missing/zero
Finnhub `c`/`pc` straight through (`float(payload.get("c") or 0.0)`), which is exactly the
shape Finnhub returns for an unrecognized symbol or a not-yet-fetched initial placeholder
(`{"c": 0, "pc": 0}`, set in `__attrs_post_init__` before the first live fetch completes).
`draw_crawl_story` checks `quote.has_data` and short-circuits to an em-dash placeholder row
before touching `format_price`/`format_change`/`format_pct` — do not reorder the has_data
check to run after any arithmetic on `price`/`prev`. Tripwire:
`test_no_data_placeholder_renders_without_raising` (`tests/test_render_smoke.py`).

**A no-data tick never clobbers a good last-known quote** — in `update()`'s per-symbol loop,
`existing.price/prev/d/dp` (and the spark append) are only overwritten when the FRESH parsed
quote has `has_data`. A transient zeroed payload (e.g. Finnhub briefly returning `{"c": 0,
"pc": 0}` mid-session for a normally-valid symbol) is logged at DEBUG and skipped — the
symbol keeps rendering its last-known price for that tick instead of flashing the em-dash
placeholder. This is orthogonal to the closed-market freeze above (that skips the whole
per-symbol loop; this skips one symbol's write within it).

**Market-state mapping: `closed = not isOpen`, else map `session`** —
`state_from_status(payload)` treats ANY falsy `isOpen` (including a missing key) as
`MarketState.CLOSED` — this correctly covers holidays and weekends where Finnhub's `session`
key may be null or absent, without a separate holiday calendar. Only when `isOpen` is truthy
does the code look at `session` (`"pre-market"` → `PRE`, `"regular"` → `OPEN`,
`"post-market"` → `AFTER`; an unrecognized/missing session string while `isOpen` is true
defaults to `OPEN`, not `CLOSED` — don't flip that default). `state_from_clock()` /
`state_now_from_clock()` are the US/Eastern wall-clock fallback: `update()` wraps
`fetch_market_status()` in try/except, and on ANY exception (timeout, non-2xx, malformed
JSON) it logs a warning and sets `self._state_ref[0] = state_now_from_clock()` instead of
propagating — the CLOSED-skip logic below then applies to the clock-derived state exactly
as it would to a status-derived one. `state_from_clock(now_eastern)` is the pure/testable
half (weekday + regular-session-window check); `state_now_from_clock()` is the thin runtime
wrapper that supplies the real `datetime.now(zoneinfo.ZoneInfo("America/New_York"))`. Quote
fetches (`fetch_quote`) are NOT wrapped this way — a per-symbol quote failure is expected to
propagate (see the initial-fetch tolerance note in `start()` above); only the status call has
a clock fallback.

**`STATE_META` drives both label and dim, keep them paired** — `StateMeta.dim` (`0.45` CLSD /
`0.85` PRE/AFTER / `1.0` OPEN) is applied via `_palette.dim(color, factor)` in every layout's
render function, and `chip_label` (`CLSD`/`PRE`/`AH`/`LIVE`) + `chip_rgb` drive the state-chip
label `card`/`dashboard` paint bottom-right/left of the hero block (Phase 1's `crawl` has no
room for a chip; it's consumed by `dim` only there). Don't repurpose `dim` for anything else
without checking the README's "dims visibly lower when CLSD" claim, which is validated by
`test_state_dimming_lowers_total_brightness` (`tests/test_render_smoke.py`).

**Geometry auto-select happens in `draw()`, not `validate_config`** — `resolve_layout(canvas,
override)` needs a real `canvas.width`, which does not exist at config-validation time
(`validate_config` only sees the raw TOML dict, no canvas). `validate_config` can only check
that an explicit `layout` STRING names a registered layout (`LAYOUTS` membership); the actual
width-based auto-select fires lazily inside `_StockStory.draw()` on first draw (cached to
`self._resolved` so it only resolves once per story, not once per frame). Do not try to move
the width check into `validate_config` — there's nothing to check it against yet.

**`resolve_layout` MUST read the REAL canvas width, never the wrapper's** — on bigsign/longboi
the widget-facing canvas is a `ScaledCanvas`, and `ScaledCanvas.width` is the LOGICAL width
(`real.width // scale`, e.g. 64 at scale=4 on a 256px-wide bigsign) — reading it directly would
always resolve to `crawl` regardless of panel size. `resolve_layout` unwraps via
`unwrap_to_real(canvas).width` before comparing against the `≤160` / `≥400` thresholds; a
plain/mock canvas passes through `unwrap_to_real` unchanged so the same code path works in
tests. Don't "simplify" this back to `canvas.width` — it silently breaks auto-select on both
big panels.

**Held-layout renderers share ONE call signature** — `_StockStory.draw` dispatches every
non-`crawl` layout (currently `card`, `dashboard`) through the identical uniform signature:
`renderer(canvas, quote, state, quotes, symbols, *, focus_index, total, frame, y_offset)`.
`quotes` (the shared sym→`SymbolQuote` dict) and `symbols` (the ordered display-symbol list)
are unused by `card` but present so a NEW held layout doesn't need a widget-shape change to add
a dashboard-style feature later — see `dashboard.py`'s watch column for the shape a future
layout would reuse. A new held layout MUST adopt this exact signature (positional `quotes`/
`symbols`, keyword-only `focus_index`/`total`/`frame`/`y_offset`) even if it ignores some of the
arguments, so `ticker.py`'s dispatch stays a single unconditional call with no per-layout branch.

**Hi-res paints go through `phys_wrap`, not the wrapper canvas directly** — `card`/`dashboard`
call `_paint.phys_wrap(canvas)` to get `(shim, real)`: `real` is `unwrap_to_real(canvas)` (the
underlying physical canvas) and `shim` is a scale-1 `ScaledCanvas` around it, so `hires()` (via
core's `draw_text`) can place hi-res glyphs at exact PHYSICAL coordinates without the
scale-4 block-expansion a normal widget canvas would apply. All hand-rolled pixel paints in
`card.py`/`dashboard.py`/`_sparkline.py`/`_chip.py` (`px()`, `paging_dots()`, the sparkline/chip
loops) write to `real`, never to `canvas` or `shim` — mixing scales mid-function is how a
"half-hi-res, half-4x-blocky" render bug would show up. `_sparkline.py`/`_chip.py` gate their
own physical-vs-logical branch with the public `is_scaled(canvas)` check (from
`led_ticker.plugin`) rather than a `hasattr(canvas, "scale")` duck-check — prefer `is_scaled`
for any future physical-pixel helper in this plugin.

**`measure_width` needs a scale-1 canvas probe, not `None`** — `right_align_x` (in `_paint.py`)
measures hi-res text width to right-align it against the real panel edge; core's
`measure_width`/`get_text_width` falls back to `SCALE_FALLBACK = 4` when handed `canvas=None`
(a pre-canvas-existence assumption baked into core — see core's CLAUDE.md "Width tracking"
note), which would divide the measured width by 4 it shouldn't. `_paint._ScaleOneProbe`
(`scale = 1`) stands in for a real canvas so the division is a no-op and the measured width
stays in the same physical-px units `hires()` actually paints in. Passing `None` here silently
undercounts hi-res text width by 4x and right-aligned text (the price, the change line, the
watch-column percents) drifts left of where it should sit.

**Phase 3 animation layer: two clocks, not one** — all three layouts now animate, and the two
effects are driven by DIFFERENT clocks that must not be confused:

- **Price flash** (`flash_price_color` in `layouts/_common.py`, called from `crawl.py`,
  `card.py`, and `dashboard.py`) is WALL-CLOCK, via `time.monotonic()`. `ticker.py`'s
  `update()` stamps `quote.flash_t = time.monotonic()` only when a live poll observes
  `fresh.price != existing.price` (demo mode's `DemoFeed` stamps it every step instead, so
  demo renders always show a flash — see `demo.py`). Each layout's `draw_*_story` reads its
  own `now = time.monotonic()` at draw time and passes it to `flash_price_color(quote.flash_t,
  dim, now=now)`, which decays the price color from white back to steady amber over
  `_FLASH_DECAY_SECONDS` (0.420s). Because it's wall-clock, **the flash intentionally does NOT
  freeze during transitions** — `pause_frame()` only freezes `FrameAwareBase`'s frame counter,
  not `time.monotonic()`. This is deliberate (a flash mid-fade should keep decaying even if the
  panel is transitioning away), not a bug to "fix" by threading it through `frame_for`.
- **LIVE-chip pulse** (`live_pulse`) and **sparkline-endpoint pulse** (`endpoint_pulse`), both
  in `layouts/_common.py`, are FRAME-driven — sine functions of the held renderer's own frame
  counter, passed in as `frame=self.frame_for("held")` from `_StockStory.draw` (shared by
  `card` and `dashboard`; `crawl` doesn't use either pulse). Because they read `frame_for`, they
  DO freeze via `pause_frame()`/`resume_frame()` during transitions, same as any other
  frame-aware effect (see core's constraint #12). `live_pulse` is gated by `STATE_META.pulses`
  (currently `True` only for `MarketState.OPEN`) — `card.py`/`dashboard.py` compute
  `chip_dim = dim * live_pulse(frame) if meta.pulses else dim`, so CLOSED/PRE/POST render the
  state chip at a steady dim with no breathing. `endpoint_pulse` pulses the sparkline tip
  regardless of market state. Both periods (`STATE_PULSE_PERIOD = 7`,
  `ENDPOINT_PULSE_PERIOD = 5`) are tuned in engine ticks (`ENGINE_TICK_MS = 50ms`), giving a
  ~2.2s LIVE-chip cycle and a ~1.6s sparkline-tip cycle (`2π·PERIOD·0.05`) — don't retune one
  without recomputing the other's comment, and don't hardcode a peak/trough frame constant in a
  test; derive it from the period (`round(ENDPOINT_PULSE_PERIOD * math.pi / 2)`) so a future
  retune can't silently desync a test from the code (see `tests/test_sparkline.py`,
  `tests/test_pulse.py`).

**`green_up` is wired end-to-end** — `StocksTicker.green_up` / `_StockStory.green_up` are
threaded from config through construction and into `draw_crawl_story(..., green_up=...)`,
which picks `up_color`/`down_color` from `pal.UP`/`pal.DOWN` (swapped when `green_up=False`)
before applying `pal.dim(...)`. Flat/no-data rendering is unaffected. Tripwire:
`test_green_up_false_flips_up_quote_color` (`tests/test_render_smoke.py`) — a pixel-level
test proving the SAME up-quote renders green-dominant at `green_up=True` and red-dominant at
`green_up=False`.

**`_StockStory` is `FrameAwareBase`** — it calls `self.frame_for("crawl")` for the crawl
dispatch and `self.frame_for("held")` (shared by BOTH `card` and `dashboard`) for the held
dispatch, passing the result as `frame=`. `card`/`dashboard` read `frame` to drive `live_pulse`/
`endpoint_pulse` (see the "Phase 3 animation layer" note above); `crawl` accepts a `frame`
keyword in its own signature but doesn't read it — its only animation (`flash_price_color`) is
wall-clock, not frame-driven.

**One INFO log per successful `update()`** — the Container contract: a silent log stream
after startup signals the background task died. Demo mode logs
`"stocks.ticker demo tick: N symbols"`; live mode logs `"stocks.ticker updated: N/M symbols"`
(or `"market closed — holding last prices"` when it short-circuits). Never log the raw
Finnhub response body (it doesn't contain secrets, but keep the convention consistent with
other first-party plugins).

**Initial fetch failure is tolerated, not fatal** — `start()` wraps its first `update()` call
in `try/except Exception`, logs a warning, and still constructs + starts the monitor loop on
failure (e.g. Finnhub rate-limited or unreachable at boot). The widget always renders
something (last-known or placeholder prices) rather than being dropped from the section for
the whole session.

## Tests / CI

`uv run pytest --cov=led_ticker_stocks -q` runs the suite (`tests/`), coverage gate 90%:

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts
  `stocks.ticker` registers under the `stocks` namespace (entry-point wiring guard).
- `test_ticker.py` — `StocksTicker`/`_StockStory` behavior: `validate_config` (empty symbols,
  FX rejection, unknown layout), shared-quote story draw, demo-mode `start()`, live `update()`,
  and the token-leak-prevention pair above.
- `test_finnhub.py` — `FinnhubClient` request shaping + `parse_quote`.
- `test_model.py` — `SymbolQuote.has_data`/`change`/`pct` no-data guard + formatting.
- `test_state.py` — `state_from_status` mapping (isOpen/session) + `state_from_clock` fallback.
- `test_demo.py` — `DemoFeed` deterministic seeding + `step()`.
- `test_crawl.py` — Mock-canvas `draw_crawl_story` cursor-arithmetic coverage.
- `test_render_smoke.py` — REAL `HeadlessBackend` canvas pixel assertions (state dimming
  actually lowers brightness, up/down colors actually flip, no-data placeholder actually
  lights pixels) — the class of bug a Mock-canvas test structurally cannot catch.
- `test_card.py` / `test_dashboard.py` — REAL `ScaledCanvas`-wrapped `HeadlessBackend` canvas
  (scale=4) pixel assertions for the held layouts: hero symbol/price/change paint, sparkline
  presence, state-chip label, paging dots, nothing clipped at the panel edge; `test_dashboard.py`
  additionally covers the watch column (next-3-symbols rendering + wraparound at the end of the
  symbol list).
- `test_chip.py` — `chip_colors_for` determinism/distinctness/override + `draw_chip` two-tone
  fill + corner-knockout pixel assertions.
- `test_sparkline.py` — `draw_sparkline` reference-line-only cold start, up/down point coloring
  relative to `prev`, white leading-edge endpoint, dim-lowers-brightness.
- `test_paint.py` — `_paint.py` helpers: `phys_wrap`, `hires` advance-width return,
  `right_align_x` against the scale-1 probe, `px` bounds-clamping, `paging_dots`.
- `test_palette.py` — `dim()` scaling.

CI is the monorepo's single root path-filtered per-member matrix (`.github/workflows/ci.yml`):
Python 3.14, `uv sync --extra dev` (led-ticker-core from PyPI), then runs ruff check,
ruff format --check, pyright, and pytest for the changed member.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget`); it becomes
`stocks.<name>`. Import any core dependency from `led_ticker.plugin` only, and keep the
import-purity test green. A new layout goes in `layouts/`, registered in `LAYOUTS`
(`layouts/__init__.py`), added to `resolve_layout`'s width thresholds, and shaped by which
dispatch branch it belongs to in `ticker.py`'s `_StockStory.draw`:

- The `"crawl"` (scrolling) branch calls
  `renderer(canvas, quote, state, cursor_pos, frame=..., y_offset=..., end_padding=...)` and
  returns the new cursor position — this shape is specific to `draw_crawl_story` and isn't
  meant to be reused; a new scrolling layout would need its own dispatch branch.
- Every OTHER (held) layout goes through the uniform signature —
  `renderer(canvas, quote, state, quotes, symbols, *, focus_index, total, frame, y_offset)` —
  the SAME call for `card` and `dashboard` today. A new held layout MUST adopt this exact
  signature (see the "Held-layout renderers share ONE call signature" invariant above) even if
  it ignores `quotes`/`symbols`, so no per-layout branch needs to be added to the dispatch.
- If `_arrow`/`_chg_color`-shaped logic is needed again, reuse `layouts/_common.py`
  (`arrow()`/`chg_color()`) rather than re-defining it in the new layout module.
