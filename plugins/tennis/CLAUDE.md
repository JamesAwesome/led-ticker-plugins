# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-tennis**, a plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker) in the first-party pack.

`README.md` is the source of truth for the user-facing surface (options, layouts, the
free-tier cadence). This file keeps the **load-bearing invariants** a contributor must
respect, plus navigation aids. When the two disagree about *how a feature works*, the
README wins; this file is the source of truth for *how to keep it working*.

## Overview

One widget, `tennis.scores`, contributed via the `led_ticker.plugins` entry point
(namespace `tennis`, see `register()` in `__init__.py`): live tennis matches from the
[Live Tennis API](https://livetennisapi.com) free tier, one story per live match
(upcoming fixtures when nothing is live), `layout = "auto"` (default) / `"ticker"` /
`"scoreboard"`. Scale 1 renders through the legacy text-glyph classes (`_scoreboard.py`);
scale>1 dispatches through `TennisMatchCard` (`_card.py`) to the physical renderers in
`layouts/`. **Vendor-maintained**: the data source's vendor maintains this pack.

## Commands

```bash
uv sync --extra dev                                        # repo root
uv run pytest plugins/tennis --cov=plugins/tennis/src      # suite (asyncio_mode = "auto")
uv run ruff check plugins/tennis && uv run ruff format --check plugins/tennis
uv run pyright plugins/tennis/src
```

Python **3.14+** only. `led-ticker-core >= 4.16` (`hires_text_width` / `fit_text_size`).

## Package layout

```
src/led_ticker_tennis/
  __init__.py       # register(api) — the only place names are registered
  scores.py         # tennis.scores widget (TennisScoreMonitor): config, start(), update(),
                    #   validate_config, _LIST_FIELD_HINTS; builds TennisMatchCard stories
  _source.py        # LiveTennisSource — the fetcher: cadence floor, one request per tick,
                    #   backoff, last-good-payload cache, key resolution. Never raises.
  _models.py        # MatchInfo + pure helpers (surname, format_points, is_break_point,
                    #   status_label, format_start_time, parse_match, build_demo_matches)
  _card.py          # TennisMatchCard — the scale-dispatching story (baseball MLBGameCard shape)
  _scoreboard.py    # legacy scale-1: TennisScoreboardMessage (two bands) + _build_match_message
  _hires_line.py    # HiresLine — status line, hi-res at scale>1 / TickerMessage at scale 1
  _palette.py       # semantic colors; one hue per data field
  _paint.py         # physical paint helpers; measurement via core hires_text_width/fit_text_size
  layouts/          # resolve_layout + scoreboard.py (held physical board) + crawl.py (hi-res crawl)
```

## Load-bearing invariants

**Import only the public surface** — every `led_ticker` import comes from
`led_ticker.plugin` (`tests/test_import_purity.py` AST-walks the sources). Intra-package
imports are fine.

**Python 3.14 / PEP 649** — no `from __future__ import annotations`.

**Request pacing** (`_source.py`): all widgets with the same API key share
one source in the process. Its lock and 900-second floor cover listings and
result lookups. One poll makes at most one request, including startup.
Only displayed matches enter the result queue. Detail lookups alternate with
live polls and completed results remain visible for two intervals.
A looked-up match is not looked up again for four intervals (`_resolved`
expires). A 404/410 lookup is an answer, not a failure: it never calls
`_fail()`, so it leaves `snap.stale` and backoff alone. Live matches sort
ahead of finished ones. `_SHARED_SOURCES` is capped at eight keys, since core
has no per-widget teardown hook. Separate processes and restarts do not share
this cache. The README describes their quota cost.

**Failure handling**: failed requests retain cached data and mark it stale.
Backoff starts at twice the interval and doubles, capped at four hours.
Rejected keys wait at least an hour. Stale scores carry a visible `STALE`
label beside the state (`SET 2`), never in place of it.
Never infer a final result or winner from a match disappearing.

**Break point rule** (`_models.is_break_point`): receiver at AD, or receiver at 40 while
the server is at 0/15/30; never in a tiebreak; False on any null (server, either point).
The truth table in `tests/test_models.py` is the contract; the physical board's `BP`
badge, the crawl's `BP` segment and the legacy board's `BP` cell all call this one
function.

**Score arrays are player-major on the wire** (`games = [[6, 3], [4, 4]]` = 6-4, 3-4).
`parse_match` re-shapes them into per-set pairs; renderers walk `MatchInfo.games` only.

**`segments()` in `layouts/crawl.py` is the single wording source for the ticker** —
the hi-res crawl paints it and the legacy `_build_match_message` joins the same list
with spaces (the `*` serve marker hugs its name), so the two paths cannot drift.

**Layout invariant (CONTRIBUTING.md) on the physical board** (`layouts/scoreboard.py`):
numeric columns are laid out right-to-left from `num_r` using MEASURED widths
(`_paint.text_width` == core `hires_text_width`) `_COL_GAP` apart, so the block is
collision-free by construction and the name budget is the measured remainder; names
shrink through the plugin-owned ladder (`_Geom.name_sizes`, ROW-UNIFORM — both rows
share one size via `fit_size` == core `fit_text_size`) and ellipsize at the floor; status
lines are ladder-fitted + ellipsized to `status_budget`. The floor is `_MIN_GAP = 6`, no
documented exception. Two geometries: `_LONG` (>= 400px: every set's games + points) and
`_BIG` (< 400px: sets won + current-set games + points). **Tripwire:**
`tests/test_layout_scoreboard.py::test_worst_case_keeps_min_clearance` spies on `hires()`
and asserts every pair of texts sharing a vertical band keeps >= 6px between ADVANCE
extents (never exact freetype pins); any geometry/ladder change must pass it on both
signs. The serve pip is fixed geometry — `test_serve_pip_clears_the_name_on_both_geometries`
pins `name_x - (dot_cx + dot_r) >= 6`.

**`TennisMatchCard` held-cursor contract** (`_card.py`): held layouts return
`cursor = canvas.width` (the WRAPPER's logical width) so the engine's `cursor_pos >
canvas.width` check takes the hold branch; the crawl treats `cursor_pos` as logical,
paints at `cursor * scale`, ceil-divides its physical run back to logical and the card
adds `self.padding`. Scale<=1 delegates to the cached legacy story; frame hooks forward
to it. Same shape as baseball's `MLBGameCard` — read that CLAUDE.md before changing this.

**Hires text is never exact-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and set-identity, never pixel coordinates of glyphs.

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring.
- `test_models.py` — surname/points/break-point truth table/status labels/start-time
  formatting/`parse_match` on API-shaped rows (incl. sparse and garbage rows).
- `test_source.py` — cadence floor, gate, one request per tick, boot double-fetch,
  alternation, backoff ladder + cap, `Retry-After`, key rejection, malformed bodies,
  exceptions never escaping. Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, no-key/env-key/config-key `start()` wiring, demo,
  story building, filters, upcoming fallback, stale snapshot, rejected key.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver table; scale dispatch.
- `test_layout_scoreboard.py` — the pixel-separation regression + per-state renders.
- `test_layout_crawl.py` / `test_scoreboard.py` / `test_hires_line.py` — crawl cursor
  contract and wording; legacy board/ticker; the status line.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
