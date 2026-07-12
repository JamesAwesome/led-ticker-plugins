# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-flight**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install,
layouts, data source). This file keeps the **load-bearing invariants** a contributor must
respect.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `flight.overhead` — a planes-overhead ADS-B tracker backed by `OverheadWidget`
  (`src/led_ticker_flight/widget.py`). It polls [adsb.lol](https://adsb.lol/)'s
  `/v2/point/{lat}/{lon}/{radius}` endpoint (no API key) and renders the tracked aircraft
  in one of three layouts, chosen by `resolve_layout(name, scale, phys_w)` from the widget's
  `layout` field and the canvas's scale/physical width.

The entry-point name `flight` is the plugin namespace, so the config `type` is
`flight.overhead`. `register()` in `__init__.py` calls `api.widget("overhead")(OverheadWidget)`.

## Load-bearing invariants

- **The design handoff is normative.** `design/README.md` (plus `app.js`, `led-engine.js`,
  and `Flight Tracker LED Layouts.html`, all committed verbatim in `design/`) is the visual
  spec for this widget — semantic palette, airline color table, and every layout number
  (font sizes, gaps, dwell times, scroll speed). Copy those values as-is; do not "improve"
  or re-derive them. There are deliberately **no font/color config knobs** — the handoff
  pins the look, so the only widget-level config is data/behavior (location, radius, layout
  choice, aircraft cap, poll interval, demo mode).

- **Deliberate divergences from the handoff.** The handoff is normative (previous bullet),
  but a few call sites intentionally depart from it — each documented at its call site and
  in `README.md`'s divergences list. Notably: the prototype's blinking live-refresh pulse dot
  (`live` color, top-right corner, ~10 s duty cycle) is dropped entirely — no other led-ticker
  widget carries an unexplained status indicator, and poll health/staleness is already visible
  in the web UI's Status tab. `palette.LIVE` stays defined (the palette module is a verbatim
  port of the handoff's color table) but has no consumer in this package. Also: `hero`/
  `dashboard` fade the whole card through black between rotating flights (below) — a
  hardware-review addition with no handoff counterpart.

- **Fade-through-black between rotating flights (`hero`/`dashboard` only).** Guarded by
  `len(flights) >= 2` — a single held flight is never dimmed, and the empty state never
  fades. Both `render_hero` and `render_dashboard` compute `pos = clock_ms % DWELL_MS` then
  `b = max(0.0, min(1.0, pos / FADE_MS, (DWELL_MS - pos) / FADE_MS))` (`paint.FADE_MS = 200.0`):
  a 200ms ramp up from black at the start of each dwell window and a 200ms ramp down to black
  at its end (0.4s total near/at black per rotation, `b == 0.0` exactly at the dwell boundary).
  `b` is threaded through every paint call for the card: `draw_fin(..., bright=b)`, every
  `hires(..., bright=b)` call, `level_bar(..., bright=b)`, and `paging_dots(..., bright=b)` —
  miss one and that element pops to full brightness through the fade, which is the kind of
  thing only a hardware/GIF check catches (see `feedback_visual_validation_gifs` in led-ticker
  core memory). `ticker_layout.render_ticker` intentionally has no fade — a continuous crawl
  has no dwell boundaries to fade across.

- **The `js_round` rule.** All handoff geometry was authored against JavaScript's
  `Math.round` (half-up). Python's built-in `round()` is banker's-rounding (round-half-to-even)
  and will silently disagree with the handoff on `.5` boundaries. Every formula translated
  from the handoff must go through `fins.js_round(v) = math.floor(v + 0.5)` instead of bare
  `round()`. Used throughout `fins.py` (tail-fin geometry) and the hero/dashboard layouts.

- **Never exact-pin hi-res font pixel output in tests.** Freetype rasterization differs
  between macOS and Linux, so a test asserting an exact pixel coordinate or count for hi-res
  text is a platform-fragile trap (bitten the `flair.lottery` widget once already — see
  led-ticker core memory). Assert "some pixels of color C exist in region R" for hi-res text.
  BDF glyphs and procedural bitmaps (fins, arrows, dots) render pixel-exact and may be pinned
  freely.

- **All animation is a pure function of `clock_ms`.** Every layout renderer
  (`render_ticker`/`render_hero`/`render_dashboard`) takes `clock_ms: float` and derives all
  motion/rotation from it — scroll offset, dwell-rotation index, idle radar sweep — with no
  hidden internal counters. `OverheadWidget.draw()` is the only place `clock_ms` is produced:
  `clock_ms = self._clock_ticks * ENGINE_TICK_MS`. `_clock_ticks` is a widget-owned counter
  (NOT `FrameAwareBase._frame_count`) advanced by an `advance_frame()` override that calls
  `super().advance_frame(visit_id=visit_id)` and then increments `_clock_ticks` (skipped while
  `_frame_paused`, mirroring the base's own pause gate). `reset_frame()` is NOT overridden —
  core's `ticker._show_one` calls it at every section visit and it zeroes `_frame_count`
  unconditionally, but `_clock_ticks` is untouched by it, so the rotation clock (and hence the
  hero/dashboard dwell index) survives a section re-entry instead of snapping back to flight 0
  mid-dwell. This keeps rendering deterministic and makes every layout trivially testable by
  calling it twice with different `clock_ms` values and diffing the canvas.
  **Settle hook:** `frames_to_transition_ready()` (core's settle-to-rest seam, #305/#343)
  returns the ticks to the next dwell boundary — `dwell_ticks - (_clock_ticks % dwell_ticks)`,
  0 when already on one — whenever the last-drawn layout is `hero`/`dashboard` with 2+
  flights; otherwise it defers to `super()`. The layout comes from `_last_layout` (stashed by
  `draw()`, default `"ticker"`) because the hook runs canvas-less at the hold->transition
  handoff. The ENGINE applies its own 1s budget (`0 < extra <= MAX_SETTLE_TICKS = 20`,
  all-or-nothing) — the widget must NOT clamp to 20 itself, and must NEVER raise (any
  exception -> 0, per the base contract). Effect: the section transition lands exactly on the
  fade's black frame whenever the hold ends within 1s of a dwell boundary; combined with a
  `hold_time` that's a multiple of the dwell, the section cut is always invisible instead of
  chopping the last flight mid-display.

- **Layout dispatch is a pure function too.** `resolve_layout(name, scale, phys_w) -> str`
  has no widget-instance state — `OverheadWidget.draw()` calls it fresh every tick with the
  live canvas's `safe_scale(canvas)` and `unwrap_to_real(canvas).width`, so a hot-reloaded
  `layout` config change or a canvas swap always resolves correctly without special-casing.
  `"auto"` semantics: scale 1 -> `ticker`; scale > 1 and physical width < 400 -> `hero`;
  scale > 1 and physical width >= 400 -> `dashboard`. An explicit `"hero"`/`"dashboard"` on a
  scale-1 sign is coerced to `"ticker"` (hi-res drawing is impossible there) rather than
  raising — the same fallback `validate_config_warnings` surfaces as an advisory warning at
  `led-ticker validate` time.

- **`start()` receives the engine's SHARED aiohttp session.** Core's `_build_widget` calls
  `cls.start(session=session, **widget_cfg)`; the `session` attrs field stores it and
  `update()` polls through it — never close or reconfigure it, and apply the 8s budget as a
  per-request `ClientTimeout` passed to `fetch_overhead` (not a session-level timeout, which
  would mutate shared state). When `session is None` (direct construction, tests), `update()`
  opens a short-lived session per poll instead.

- **Demo mode bypasses the network entirely.** `demo = true` seeds `_flights` from
  `data.SAMPLE_AIRCRAFT` (sliced to `max_aircraft`) in `__attrs_post_init__` and `start()`
  never calls `update()` or spawns the background poll task — so `demo = true` widgets have
  zero network dependency, useful for previewing layouts offline.

- **`bg_color` is DECLARED ONLY — never `Fill()` it in `draw()`.** A section-level
  `bg_color` is injected into every widget's config by core (pre-coerced to a
  `graphics.Color`); `OverheadWidget` declares the `bg_color` attrs field purely so the
  build doesn't fail with "unknown field: 'bg_color'" — the same pattern as core's
  `weather`/`crypto` widgets. The ENGINE paints it (a `Clear()`/`Fill(bg_color)` reset
  before each tick, plus the transition's `outgoing_bg_color`/`incoming_bg_color`
  kwargs), not the widget. During a push-transition, outgoing and incoming widgets are
  drawn onto the SAME canvas in one pass; if `draw()` called `canvas.Fill(...)` itself,
  it would erase whatever the other side of the transition already painted. `draw()`
  must stay paint-only against whatever the canvas already holds.

- **Public surface only.** `widget.py` (and every module under `src/led_ticker_flight/`)
  imports ONLY from `led_ticker.plugin` (plus stdlib + `aiohttp` + `attrs`). Never reach
  into `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py` (AST scan).

- **No `from __future__ import annotations`** (Python 3.14 / PEP 649 rule, same as core).

## Commands

`led-ticker-core` resolves from PyPI (`>=4.8`); no sibling checkout or `[tool.uv.sources]`.
Tests obtain canvases via `HeadlessCanvas`/`ScaledCanvas` from `led_ticker.plugin` — no
rgbmatrix stub on the path. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/flight
uv run ruff check plugins/flight
uv run ruff format --check plugins/flight
uv run pyright plugins/flight/src
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_flight/
  __init__.py          # register(api) -> api.widget("overhead")(OverheadWidget)
  widget.py             # OverheadWidget (FrameAwareBase) + resolve_layout + validation
  adsb.py               # adsb.lol client + haversine/bearing/compass8 + parse_point_response
  data.py               # Aircraft model, vr_state/fmt_alt formatting, SAMPLE_AIRCRAFT demo feed
  palette.py            # semantic color palette + airline tail-fin color table
  fins.py               # js_round + airline tail-fin silhouette geometry/paint
  glyphs.py             # BDF-space procedural glyphs (arrows, degree sign, dot); the
                        #   "dot" glyph serves paging dots — the ticker's own
                        #   field-separator pixel is painted directly in
                        #   ticker_layout.py's _draw_row, not through this table
  paint.py              # shared paint helpers: dim, empty/idle state, paging dots,
                        #   hi-res physical-canvas wrap (phys_wrap/hires/px), level_bar
                        #   (procedural level-flight indicator, shared by hero + dashboard)
  ticker_layout.py       # render_ticker  — smallsign: single-line BDF crawl
  hero_layout.py         # render_hero    — bigsign: hi-res single-flight hero
  dashboard_layout.py    # render_dashboard — longboi: hi-res multi-column dashboard
tests/
  test_widget.py          # OverheadWidget behavior + resolve_layout
  test_validate.py         # validate_config / validate_config_warnings
  test_adsb.py             # geo math + payload parsing
  test_data.py              # Aircraft formatting helpers
  test_palette.py / test_fins.py / test_glyphs.py / test_paint.py
  test_ticker_layout.py / test_hero_layout.py / test_dashboard_layout.py
  test_import_purity.py    # AST: only led_ticker.plugin imports
  test_smoke.py             # entry-point registers flight.overhead
  conftest.py                # smallsign/bigsign/longboi canvas fixtures
```
