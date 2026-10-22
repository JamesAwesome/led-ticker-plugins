# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-hockey**, a plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker) in the first-party pack.

`README.md` is the source of truth for the user-facing surface (options, modes, layouts,
cadence). This file keeps the **load-bearing invariants** a contributor must respect, plus
navigation aids. When the two disagree about *how a feature works*, the README wins; this
file is the source of truth for *how to keep it working*.

## Overview

One widget, `hockey.scores`, contributed via the `led_ticker.plugins` entry point
(namespace `hockey`, see `register()` in `__init__.py`): live NHL games from the public,
unofficial web API (`https://api-web.nhle.com`, **no key**), one story per game, modes
`teams` / `league` / `live`, `layout = "auto"` (default) / `"scoreboard"` / `"ticker"`.
`auto` resolves to `scoreboard` on all three signs. Scale 1 renders through the bitmap
classes in `_scoreboard.py`; scale>1 dispatches through `HockeyGameCard` (`_card.py`) to
the physical renderers in `layouts/`. Example teams everywhere are `PHI` and `NYI`.

## Commands

```bash
uv sync --extra dev                                        # repo root
uv run pytest plugins/hockey --cov=plugins/hockey/src      # suite (asyncio_mode = "auto")
uv run ruff check plugins/hockey && uv run ruff format --check plugins/hockey
uv run pyright plugins/hockey/src
```

Python **3.14+** only (no `from __future__ import annotations`). `led-ticker-core >= 4.30`.

## Invariants

**Import purity** — import `led_ticker` ONLY from `led_ticker.plugin`. AST tripwire:
`tests/test_import_purity.py`.

**The source never raises** (`_source.py`) — every network and parse error becomes
`stale` + backoff (2x interval, doubling, capped at 4 h); a bad payload keeps the last
good games. A game that drops out of the feed keeps its last state: NEVER infer a final
from a game disappearing. `polled_at` is wall-clock epoch seconds.

**One shared source per session** — `shared_source(session)`; every widget's `want()`
merges into it, and cadence is the source's (15 s live / 300 s pregame / 3600 s idle,
`MIN_INTERVAL` 10 s; season schedule at most every 6 h). The landing "situation" call is
gated to live games that some consumer displays (`note_displayed`, per consumer, so
shared widgets do not multiply requests).

**First-sight goal baseline lives in the source; celebrated state lives on the widget/card**
— `NHLSource.goals_after_baseline(game_id)` is NON-consuming: the first sight of a game
records a baseline and returns nothing older. Each `HockeyScoreMonitor` keeps its own
`_celebrated` map with a per-widget first-sight baseline, so a hot reload with a surviving
shared source is silent and every widget celebrates a goal exactly once. Do not move
consumption into the source.

**Cards are persistent** — one `HockeyGameCard` per game id (or `next:TEAM`), kept in
`_cards` across polls; `_rebuild` reassigns `game` / `stale` in place. Never rebuild cards
per poll: celebration state, frame counters and the legacy story cache live on them.

**`reset_frame` consumption** (`_card.py`) — the celebration plays from a snapshot
(`_playing`) taken at visit-entry `reset_frame()`. A goal is consumed only once it was
actually DRAWN on a live (unpaused, `_frame_count > 0`) frame (`_shown`), so stale frame
counts or transition compositing never eat an unseen celebration. Goals queued mid-visit
wait for the next turn. Non-tracked goals highlight the score instead; empty `teams` means
no celebrations.

**`hold_time` property** — `HockeyGameCard.hold_time` = `base_hold` + 4 s (80 frames x
50 ms) per queued goal. Core reads it as `max(section_hold, getattr(story, "hold_time",
0.0))` in led-ticker `ticker.py` (`_show_one`, around line 762 at time of writing). Keep
it a property reading `_playing` (fall back to `pending`); if core changes that line the
celebration is cut short.

**`segments()` in `layouts/crawl.py` is the single wording source for the ticker** — the
hi-res crawl paints it and the legacy ticker message joins the same list, so the two
paths cannot drift.

**Layout invariant (CONTRIBUTING.md)** — measured widths (`_paint.text_width`), >= 6 px
(`_MIN_GAP`) between texts sharing a vertical band, row-uniform name sizes, ellipsis at the
floor. **Tripwire:** `tests/test_layout_scoreboard.py::test_worst_case_keeps_min_clearance`
(longest abbreviations, double-digit scores, `SOG 99`, `PP` + `EN`, `FINAL/SO`) on both
physical signs. Any geometry/ladder change must pass it.

**Hi-res text is never pixel-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and colors.

**Palette is one hue per field** (`_palette.py`) — white score/clock, amber period/PP/date,
cyan SOG, dim labels, green final winner, gray loser. Black is invisible on the panels, so
team chips are lifted for LED brightness.

## Known gaps

- The landing `situation` field shapes (power play, empty net) come from community docs and
  are unverified against a live game; capture a real payload as a fixture when one is on.
- The scale-1 `ticker` layout's clock text updates per poll; boards and hi-res tick per second.

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring.
- `test_models.py` / `test_teams.py` — parsing (incl. garbage rows), team table and codes.
- `test_source.py` — cadence, gate, shared source, baseline, backoff, never raising.
  Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, selection per mode, demo, stale, persistent cards.
- `test_celebration.py` — timeline phases and renderers.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver; scale dispatch; consumption.
- `test_layout_scoreboard.py` / `test_layout_crawl.py` / `test_scoreboard.py` — physical and
  bitmap renderers, the clearance tripwire, ticker wording.
- `test_examples.py` — example configs validate, use `PHI`/`NYI`, and the README documents
  every option.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
