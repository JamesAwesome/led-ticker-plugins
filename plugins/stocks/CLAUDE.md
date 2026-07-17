# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-stocks**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install,
rate limits, FX limitation, demo mode). This file keeps the **load-bearing invariants** a
contributor must respect, plus navigation aids. When a fact here and the README disagree
about *how a feature works*, the README wins; this file is the source of truth for *how to
keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, one widget, one source, and
one color provider:

- `stocks.ticker` — live equity price Container from the Finnhub REST API. Cycles one
  `_StockStory` "story" per configured symbol (the engine reads `feed_stories` via
  `_expand_sources` on every pass). Trend-colored green/red, dimmed by market state. Three
  layouts are registered and auto-selected by real panel width: `crawl` (smallsign,
  scrolling), `card` (bigsign, held), `dashboard` (longboi, held) — see the README's
  [Layouts](README.md#layouts) section for the user-facing shape of each.
- `stocks.quote` — a `PolledDataSource` (core `led_ticker.plugin`) exposing a live `:id:`
  price token embeddable in any other widget's text — see the README's
  [Inline price tokens](README.md#inline-price-tokens) section.
- `stocks.trend` — a `ColorProviderBase` (core `led_ticker.plugin`) that tints a text widget's
  `font_color` green/red/neutral by a symbol's day change, reading the same shared
  `QuoteCache` — see the README's [Trend color](README.md#trend-color) section and the
  `StocksTrendColor` invariant below.

As of Phase 4 (`_cache.py`), NEITHER `stocks.ticker` NOR `stocks.quote` owns any Finnhub I/O
itself — both are thin readers of a single process-wide `QuoteCache`. See "Phase 4: the
shared `QuoteCache`" below before touching either.

The entry-point name `stocks` is the plugin namespace, so the config types are
`stocks.ticker` / `stocks.quote` (see `register()` in `__init__.py`).

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
  __init__.py         # register(api) → api.widget("ticker")(StocksTicker),
                       #   api.source("quote")(StockSource),
                       #   api.color_provider("trend")(StocksTrendColor)
  _cache.py            # QuoteCache: the ONE Finnhub-owning singleton (Phase 4) —
                       #   register()/get()/state()/ensure_started()/update()/reset();
                       #   get_cache() returns the process-wide instance
  ticker.py            # StocksTicker (Container): validate_config(), start() (registers +
                       #   ensure_started, owns no data); _StockStory: per-symbol story
                       #   reading QuoteCache live on every draw()
  source.py            # StockSource (stocks.quote): PolledDataSource reading QuoteCache;
                       #   validate_config(), _field_value() per-format-field dispatch
  trend_color.py       # StocksTrendColor (stocks.trend): whole-string ColorProvider reading
                       #   QuoteCache; green up / red down / neutral flat; never starts the cache
  finnhub.py           # FinnhubClient (quote + market-status GETs); parse_quote()
  model.py             # SymbolQuote + format_price/format_change/format_pct
  state.py             # MarketState enum + STATE_META (dim/label/color/pulses) +
                       #   state_from_status() (Finnhub) + state_from_clock()/
                       #   state_now_from_clock() (US/Eastern wall-clock fallback, wired
                       #   into QuoteCache.update()'s market-status except branch)
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
    api.source("quote")(StockSource)
    api.color_provider("trend")(StocksTrendColor)
```

## Load-bearing invariants

Each rule must hold when modifying the named files.

**Positioned hi-res text is collision-guarded** — the layouts' symbol/price/watch-column fit ladders (`_fit_price_size` etc.) implement the monorepo layout invariant (measure via core's `hires_text_width`, plugin-owned ladders, pixel-separation tests, never <6px measured clearance — see CONTRIBUTING.md). Don't add a new fixed-position/right-aligned text surface without one.

**Import only the public surface** — every `led_ticker` import MUST come from
`led_ticker.plugin`, never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`,
which AST-walks every source file. Intra-package imports
(`from led_ticker_stocks._palette import …`) are fine.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as
core). Bare `dict[str, SymbolQuote]` / `tuple` annotations are fine.

**`StocksTicker` is a Container that owns no data** — it exposes `feed_stories:
list[_StockStory]` (one story per symbol); each story reads the shared `QuoteCache` live on
every `draw()` (`cache.get(sym)` / `cache.state()` — see "Phase 4: the shared `QuoteCache`"
below). `StocksTicker.update()` no longer exists — `start()` only registers symbols and calls
`ensure_started()`; polling and mutation happen entirely inside `QuoteCache`. The engine reads
`feed_stories` via `_expand_sources` on every pass, so a price update surfaces within at most
one cycle. **Never** snapshot `feed_stories` into a cycle iterator, and never give each
`_StockStory` its own copy of a quote — that was the longboi stale-display pattern (a
container that updates correctly in the background but a frozen snapshot never sees it).

**Token is env-only, never a `start()` parameter** — `StocksTicker.start()` deliberately does
NOT declare a `token` parameter (and `StockSource`/`PolledDataSource` never see one either).
Core's widget factory unions a Container's `start()` keyword signature into the set of config
keys it will bind, so if `token` were a `start()` parameter, a user's `token = "..."` in
`config.toml` would silently override the env secret and flow straight into Finnhub HTTP
requests — exactly the leak `resolve_secret_token` / "secrets belong in `.env`" is meant to
prevent. The actual env resolution (`os.getenv("FINNHUB_API_TOKEN", "")`) now happens ONCE,
inside `QuoteCache.ensure_started()` — not per-widget. `StocksTicker` still carries a `token`
attrs field only so a v0.3.0-era config with `token = "..."` still validates: the value flows
through `**kwargs` into `cls(...)` and binds to `widget.token`, but `start()` never reads or
forwards it, so a config-supplied token dead-ends on the instance and never reaches the cache.
(There is deliberately no `k != "token"` filter — `token` is a legitimate attrs field; it is
inert, not stripped.) Tripwires:
`test_config_token_is_ignored`, `test_config_token_is_ignored_no_env` (`tests/test_ticker.py`).

**Empty token silently routes to demo, not an error** — `QuoteCache.ensure_started()` treats
`force_demo or not token` as one condition: `demo = true` on ANY registered widget OR a
missing/empty `FINNHUB_API_TOKEN` both land on the exact same `DemoFeed` path, for the WHOLE
cache (not just the widget that set `demo = true`) — see the "single-mode, first-started-wins"
rule below. This is intentional (a sign that forgot to set the env var boots with a visible,
moving placeholder rather than a dead/erroring widget) — do not turn "no token" into a hard
failure without updating the README's demo-mode section, which documents this fallback as the
recommended smoke-test path.

**Rate rule: `effective_interval = max(base_interval, len(symbols) + 1)`, recomputed live** —
`QuoteCache._effective_interval()` is NOT cached; it reads `len(self._symbols)` fresh every
poll cycle (`_run_poll_loop`), so a symbol registered AFTER the loop already started (a second
widget in another section, a `stocks.quote` token added later) still widens the cadence on the
very next cycle — a fixed `run_monitor_loop` interval could not do this, which is why the
cache runs its own `_run_poll_loop` instead. `len(symbols)` here is the UNION of every symbol
any widget or source has EVER called `register()` with, process-wide — not one widget's own
list. Each `update()` costs `len(symbols) + 1` Finnhub requests (1 status + 1-per-symbol
quote, each DISTINCT symbol fetched exactly once regardless of how many consumers registered
it — see "Phase 4: the shared `QuoteCache`" and the dedup tripwire below) while the market is
open, or exactly **1** while closed (see the no-quote-calls-when-closed rule below). Finnhub's
free tier is 60 req/min **per API key**, not per widget instance — the README's rate-limit
section documents that two signs or two Finnhub-backed widgets/tokens sharing one token divide
the same budget; this code cannot see or enforce that cross-process sharing, only the
single-process floor. `StocksTicker.start()` still logs one `logging.warning` when
`len(symbols) > SYMBOL_SOFT_CAP` (20) for THIS widget's own list — advisory only, does not
clamp or reject.

**Closed-market freeze is per-symbol, NOT a whole-cycle skip** — `QuoteCache.update()` always
fetches market status first. When `MarketState.CLOSED`, it does NOT blanket-skip quotes:
it fetches only symbols it has **never attempted** (`sym not in self._attempted`) and freezes
(skips) the rest. This is load-bearing: a sign booted after hours has ALL symbols cold, and
Finnhub `/quote` returns the last close in `c` even while the exchange is shut — so one fetch
per cold symbol is what makes the card show the close and inline `:stocks.*:` tokens resolve
past their `…` placeholder. A whole-cycle `return` when closed (the original Phase-4 bug) left
every symbol empty forever on an after-hours boot: em-dash cards, dead tokens. The freeze keys
on `_attempted` (symbols we've called `fetch_quote` for at least once), NOT `has_data`: a bad
symbol has no data but must not refetch every closed cycle. Once a symbol is attempted, closed
cycles skip it (rate-budget: worst case `N+1` on the first closed cycle, then `1` status-only
per cycle as symbols warm up; steady-state closed is still 1 request). Late registrants added
while closed are un-attempted, so they too get their one fetch. Don't reintroduce an early
`return` on `CLOSED`. Tripwires: `test_closed_fetches_cold_symbols_once`,
`test_closed_holds_symbols_that_already_have_data` (`tests/test_cache.py`).

**Late-registrant catch-up in `ensure_started`** — the cache is single-mode, first-started-wins
(above), so whichever consumer boots the cache first runs the initial fetch over only the
symbols registered AT THAT MOMENT. A `stocks.ticker` widget whose `start()` runs AFTER a
`stocks.quote` token already started the cache would otherwise leave its extra symbols cold
until the next poll cycle (a full interval) — the after-hours symptom where only the card
sharing the token's symbol got data. So `ensure_started`'s already-started path is NOT a bare
`return`: it calls `_catch_up_new_symbols()`, which fetches any symbol in `_symbols - _attempted`
right now (a no-op when all warm, so it doesn't refire on the source's every-tick
`ensure_started` call or on bad symbols). The poll loop and the catch-up both drive `update()`,
so they share `self._poll_lock` (an `asyncio.Lock` created in the first-start path) to avoid a
concurrent double-fetch. Tripwires: `test_late_registrant_caught_up_on_ensure_started`,
`test_ensure_started_no_catchup_when_all_symbols_warm` (`tests/test_cache.py`).

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

**A no-data tick never clobbers a good last-known quote** — in `QuoteCache.update()`'s
per-symbol loop,
`existing.price/prev/d/dp` (and the spark append) are only overwritten when the FRESH parsed
quote has `has_data`. A transient zeroed payload (e.g. Finnhub briefly returning `{"c": 0,
"pc": 0}` mid-session for a normally-valid symbol) is logged at DEBUG and skipped — the
symbol keeps rendering its last-known price for that tick instead of flashing the em-dash
placeholder. This is orthogonal to the closed-market freeze above (that skips the *fetch* for
symbols already holding data; this skips one symbol's *write* when a fetch returns zeroed).

**Market-state mapping: `closed = not isOpen`, else map `session`** —
`state_from_status(payload)` treats ANY falsy `isOpen` (including a missing key) as
`MarketState.CLOSED` — this correctly covers holidays and weekends where Finnhub's `session`
key may be null or absent, without a separate holiday calendar. Only when `isOpen` is truthy
does the code look at `session` (`"pre-market"` → `PRE`, `"regular"` → `OPEN`,
`"post-market"` → `AFTER`; an unrecognized/missing session string while `isOpen` is true
defaults to `OPEN`, not `CLOSED` — don't flip that default). `state_from_clock()` /
`state_now_from_clock()` are the US/Eastern wall-clock fallback: `QuoteCache.update()` wraps
`fetch_market_status()` in try/except, and on ANY exception (timeout, non-2xx, malformed
JSON) it logs a warning and sets `self._state = state_now_from_clock()` instead of
propagating — the closed-market policy above then applies to the clock-derived state exactly
as it would to a status-derived one (a cold symbol still gets its one last-close fetch). `state_from_clock(now_eastern)` is the pure/testable
half (weekday + regular-session-window check); `state_now_from_clock()` is the thin runtime
wrapper that supplies the real `datetime.now(zoneinfo.ZoneInfo("America/New_York"))`. Quote
fetches (`fetch_quote`) are NOT wrapped this way — a per-symbol quote failure is expected to
propagate (see the initial-fetch tolerance note in "Phase 4: the shared `QuoteCache`" below);
only the status call has a clock fallback.

**`STATE_META` drives both label and dim, keep them paired** — `StateMeta.dim` (`0.70` CLSD /
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
  `card.py`, and `dashboard.py`) is WALL-CLOCK, via `time.monotonic()`. `_cache.py`'s
  `QuoteCache.update()` stamps `quote.flash_t = time.monotonic()` only when a live poll observes
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

**`StocksTrendColor` is a thin whole-string color provider, never a data owner** — registered
via `api.color_provider("trend")(StocksTrendColor)` (`stocks.trend`), `per_char = False`,
`frame_invariant = False` (color tracks live data, so it must be re-evaluated on every draw —
same reasoning as Rainbow/ColorCycle). `color_for` mirrors `layouts/_common.py`'s `chg_color`
*branching* (`chg > 0` → up, `chg < 0` → down, else flat; `green_up` swaps up/down) — but NOT
its market-state dimming or its amber `pal.FLAT`; the provider's flat default is a neutral gray
(`_DEFAULT_FLAT`), and its up/down default to `pal.UP`/`pal.DOWN`. It reads
`get_cache().get(symbol)` directly. It MUST NOT raise — a color provider runs in the render
loop — and it MUST NOT call `ensure_started()` or perform any I/O; a provider has no
session/async context to own a poll loop, unlike `StockSource`. `__init__` DOES call
`get_cache().register([symbol])` so the symbol joins the shared union and rides whichever
consumer starts the cache (the Phase-4 late-registrant catch-up above covers a provider
constructed after boot) — but registering is not starting: with no `stocks.quote` source or
`stocks.ticker` widget feeding the same symbol in the config, the cache never starts and
`color_for` always returns `flat` (not an error, just a steady neutral gray forever — see the
README's [Trend color](README.md#trend-color) feeding-requirement callout). Config-surface
validation (`symbol` required/non-empty, FX-pair rejection, `up`/`down`/`flat` RGB coercion —
ints 0-255, bool excluded) lives entirely in `__init__`, which raises `ValueError`; there is no
separate `validate_config` hook for a color provider — the coercion path
(`_build_plugin_style`) surfaces `__init__`'s raise at config-load. Tripwire:
`tests/test_trend_color.py`.

**`_StockStory` is `FrameAwareBase`** — it calls `self.frame_for("crawl")` for the crawl
dispatch and `self.frame_for("held")` (shared by BOTH `card` and `dashboard`) for the held
dispatch, passing the result as `frame=`. `card`/`dashboard` read `frame` to drive `live_pulse`/
`endpoint_pulse` (see the "Phase 3 animation layer" note above); `crawl` accepts a `frame`
keyword in its own signature but doesn't read it — its only animation (`flash_price_color`) is
wall-clock, not frame-driven.

**One INFO log per successful `update()` cycle** — lives in `_cache.py` now, not `ticker.py`:
a silent log stream after startup signals the shared poll task died (see
`test_reset_cancels_spawned_task`-style tripwires). Demo mode logs `"stocks QuoteCache demo
tick: N symbols"`; live mode logs `"stocks QuoteCache updated: F fetched, H held (M symbols)"`
(preceded, when closed, by `"stocks QuoteCache: market closed — fetching last close for cold
symbols, holding the rest"`). Never log the raw
Finnhub response body (it doesn't contain secrets, but keep the convention consistent with
other first-party plugins). There is exactly ONE such log stream for the whole process — it
covers every widget/token sharing the cache, not one per consumer.

## Phase 4: the shared `QuoteCache`

`_cache.py` centralizes ALL Finnhub I/O behind one process-wide `QuoteCache` singleton
(`get_cache()`), replacing the earlier design where each `stocks.ticker` widget instance ran
its own `FinnhubClient` + `run_monitor_loop`. This exists because a config with more than one
stocks-reading consumer (two `stocks.ticker` sections, or a widget plus one or more
`stocks.quote` tokens) would otherwise multiply Finnhub request volume per shared symbol —
the dedup rule below is the whole point of this file.

- **Consumers register, never fetch directly.** `StocksTicker.start()` calls
  `get_cache().register(widget.symbols)`; `StockSource.__attrs_post_init__` calls
  `get_cache().register([self.symbol])`. `register()` unions into `self._symbols: set[str]`
  and seeds a zeroed placeholder quote for any symbol not already tracked — registering the
  same symbol from N different consumers is a no-op after the first. Reads go through
  `get()`/`state()`, both O(1) dict lookups against cache state mutated by the shared poll
  loop — no consumer awaits or fetches on its own draw/update path.
- **Dedup is structural, not counted.** Because `_symbols` is a `set` and `update()`'s
  per-symbol loop iterates it exactly once per cycle, a symbol registered by both a widget
  AND a token is fetched exactly once per poll cycle — never once per consumer. Tripwire:
  `test_shared_symbol_fetched_exactly_once_per_cycle` (`tests/test_dedup.py`) — registers the
  same symbol via a widget-style `register()` call and an independent `StockSource`
  construction, monkeypatches the (stub) client's `fetch_quote` to count calls per symbol,
  runs one `update()` cycle live/OPEN, and asserts the count is exactly `{"AAPL": 1}`. If you
  ever change the cache to track fetches per-registrant instead of per-symbol-in-a-set, this
  test is the regression signal.
- **Single-mode, first-started-wins.** The MODE decision in `ensure_started(session, interval,
  force_demo)` is idempotent — `self._started` gates it, so the token resolution, live-vs-demo
  choice, `_base_interval`, and poll-loop spawn all happen exactly once, at the first call, and
  a later call with a different `force_demo` does NOT change them. The cache resolves
  `FINNHUB_API_TOKEN` from env exactly once — see the README's "Demo is a process-wide setting"
  callout. Do not add a per-consumer mode override; it would require re-architecting the
  first-start path, which the poll-loop-spawn logic depends on. NOTE the already-started path is
  no longer a pure no-op: it runs `_catch_up_new_symbols()` (see the "Late-registrant catch-up"
  invariant above) — that fetches new symbols but never touches the mode/token/loop state.
- **`update()` is the one method that performs I/O**, called both from inside
  `ensure_started()` (an initial, exception-tolerant fetch so a rate-limited/unreachable
  Finnhub at boot doesn't block startup) and from `_run_poll_loop()` on the recomputed
  `_effective_interval()` cadence (see the rate-rule invariant above). `StockSource.update()`
  (the `PolledDataSource` hook core calls on ITS OWN interval) never fetches Finnhub directly
  — it calls `get_cache().ensure_started(self.session, interval=self.interval)` (cheap no-op
  after the first call from anywhere) then reads `get_cache().get(self.symbol)`. This is how a
  token-only config (no `stocks.ticker` widget in the process) still gets a running poll loop:
  the FIRST `:id:` token to tick self-starts the cache.
- **`reset()` is a test seam, not production API** — cancels the spawned poll task and clears
  every field back to construction defaults. `tests/conftest.py`'s autouse
  `_reset_quote_cache` fixture calls it before AND after every test in the plugin's suite
  (also duplicated locally in `test_cache.py`'s own fixture) so symbol registration and a
  spawned `asyncio.Task` can never leak between tests — the SAME hermetic pattern the "keep
  the process-wide QuoteCache singleton hermetic" comment describes. Any NEW test file that
  touches `stocks.ticker`, `stocks.quote`, or `_cache` directly relies on this fixture already
  running (autouse, no explicit import needed) — don't add a second competing reset fixture
  with different scope.

**Initial fetch failure is tolerated, not fatal** — `QuoteCache.ensure_started()` wraps its
first `update()` call in `try/except Exception`, logs a warning, and still spawns the poll
loop on failure (e.g. Finnhub rate-limited or unreachable at boot). Every widget/token reading
the cache always renders something (last-known or placeholder prices) rather than being
dropped from the section for the whole session.

## Tests / CI

`uv run pytest --cov=led_ticker_stocks -q` runs the suite (`tests/`), coverage gate 90%:

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts
  `stocks.ticker` registers under the `stocks` namespace (entry-point wiring guard).
- `test_ticker.py` — `StocksTicker`/`_StockStory` behavior: `validate_config` (empty symbols,
  FX rejection, unknown layout), shared-cache story draw, demo-mode `start()`, and the
  token-leak-prevention pair above.
- `test_cache.py` — `QuoteCache` itself: register/dedup/seed, live `update()` mutation +
  flash-stamp, closed-market cold-fetch + warm-symbol freeze, demo synthesis (including a late registrant added
  after `ensure_started`), `_effective_interval` widening, `ensure_started` idempotence,
  `reset()` task cancellation.
- `test_source.py` — `StockSource` (`stocks.quote`): `validate_config` (unknown field,
  malformed/non-str format, bad conversion spec, FX rejection), placeholder-until-first-update,
  construction-registers-with-cache, `update()` rendering every format field off a seeded
  cache quote, lazy `_used_fields` (an unreferenced field is never computed), and the
  token-only self-start path (`update()` calls `ensure_started` idempotently).
- `test_dedup.py` — the shared-cache integration tripwire: registers ONE symbol via two
  independent consumers (widget-style `register()` + a `StockSource` construction), counts
  `fetch_quote` calls per symbol across one live `update()` cycle, asserts the count is
  exactly one — see "Phase 4: the shared `QuoteCache`" above.
- `test_trend_color.py` — `StocksTrendColor`: up/down/flat color selection off a seeded quote,
  `green_up` swap, `up`/`down`/`flat` overrides, no-data-never-raises, missing/empty/FX
  `symbol` raises, bad `[r,g,b]` raises, construction registers the symbol with the cache,
  `per_char`/`frame_invariant` flags.
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

Register the class in `register()` in `__init__.py` (`api.widget` for a Container/widget,
`api.source` for a `PolledDataSource`, `api.color_provider` for a `ColorProviderBase`); it
becomes `stocks.<name>` either way. Import any core dependency from `led_ticker.plugin` only,
and keep the import-purity test green. A new source or color provider that also needs live
prices should read `_cache.get_cache()` exactly like `StockSource`/`StocksTrendColor` do —
never open its own `FinnhubClient`, and never call `ensure_started()` from a color provider
(see "Phase 4: the shared `QuoteCache`" above and the `StocksTrendColor` invariant). A new
layout goes in `layouts/`, registered in `LAYOUTS`
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
