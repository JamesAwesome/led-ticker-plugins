# baseball.promotions widget — design

**Date:** 2026-06-10
**Status:** Approved
**Scope note:** This spec covers the promotions widget only. A Statcast widget
(Baseball Savant data) and an attendance/ballpark-conditions widget (live-feed
`gameData.gameInfo` / `gameData.weather`) were discussed and deliberately
deferred; they use different data sources and get their own specs later.

## Purpose

Show a team's upcoming home-game promotions (giveaways, theme nights — e.g. the
Blue Jays' "Loonie Dogs Night") on the ticker. Data comes from the MLB StatsAPI
schedule endpoint's `promotions` hydration — the same free, keyless API the
scores and standings widgets already poll:

```
GET {MLB_API}/schedule?teamId={id}&startDate={start}&endDate={end}&sportId=1&hydrate=game(promotions)
```

Each promotion entry carries `name` ("Loonie Dogs Night presented by
Schneiders"), `description`, `offerType`, sponsor, and image URLs. The widget
uses only `name`.

## User-facing surface

**Widget type:** `baseball.promotions`
**Class:** `MLBPromotionsMonitor` in `src/led_ticker_baseball/promotions.py`
**Registration:** `api.widget("promotions")(MLBPromotionsMonitor)` in
`register()` (`__init__.py`).

### Config

```toml
[[playlist.section.widget]]
type = "baseball.promotions"
team = "TOR"                         # required — team abbreviation
highlight = ["Loonie Dogs"]          # optional — callout color + sort first
filter = ["bobblehead", "giveaway"]  # optional — if non-empty, ONLY matches shown
limit = 3                            # optional — max promo lines; 0/omitted = all
lookahead_days = 14                  # optional — window to find the next home game
update_interval = 21600              # optional — seconds between refreshes (6 h)
# standard knobs: title, timezone, padding, hold_time, bg_color, font_color, font
```

- `highlight` and `filter` are case-insensitive substring matches against the
  cleaned promotion name. They compose: `filter` decides what is shown,
  `highlight` decides what stands out.
- `update_interval` defaults to 6 hours: promotions barely change intra-day,
  but the "Today" label must roll over within a few hours of midnight, so the
  daily interval the standings widget uses is too coarse.
- `timezone` defaults to `"America/New_York"` (consistent with siblings) and
  governs what "today" means and how dates render.

### Display behavior

- **Title** (`feed_title`): team name in team color + `" Promos"` (white).
  A configured `title` string overrides it (rendered like the standings title).
- **Today is a home game with (post-filter) promotions:** one story per promo:
  `Today · Loonie Dogs Night` — date label in grey (`make_color(150, 150, 150)`,
  the series-record grey), separator `·`, name in white. Highlighted promos
  render the name in amber (`make_color(255, 200, 60)`, the postponed-tag
  callout color) and sort before the rest; non-highlighted promos keep feed
  order.
- **Otherwise:** the earliest future home game inside `lookahead_days` that has
  (post-filter) promotions, same line format with the date as the label:
  `Jun 22 · Retro Domer Hat Giveaway`. The date prefix is per-line because
  ticker stories scroll independently; each line must stay self-contained.
- **Name cleaning:** strip sponsor tails (`presented by …`, `pres. by …`,
  case-insensitive) before display, matching, and dedup.
- **Dedup (per game):** after cleaning and casefolding, drop exact duplicates;
  when one cleaned name is a prefix of another (the feed lists both
  "Dylan Cease Bobblehead Giveaway Night" and "Dylan Cease Bobblehead
  Giveaway"), keep the shorter.
- **`limit`:** applied after filtering, highlighting, and sorting — the
  highlighted promos can never be the ones truncated.

### Empty states

| Condition | Display |
| --- | --- |
| Home games in window, none with matching promos | `Next home game: Jun 22` (earliest home game in window; `Home game today` when that game is today) |
| Games in window but none at home (road trip longer than `lookahead_days`) | 30-day probe (`gameType=R`): first home game → `Next home game: <date>`, else `No home games soon` |
| No games at all in window (offseason) | Same 30-day probe: first home game → `Next home game: <date>`, else first game of any kind → `Opens <date>` (season opens on the road), else `Opens soon` — same UX shape as the standings widget |
| API/parse failure | `No Data` — same pattern as the standings widget |

The road-trip and offseason rows share one fallback probe; whether the main
window had any games at all (home or away) decides between the
`No home games soon` and `Opens …` texts.

All empty/error states keep the normal `feed_title` so the section stays
labeled.

## Internals

### Architecture

`MLBPromotionsMonitor` mirrors `MLBStandingsMonitor`'s shape:

- attrs class: `session`, config fields, `_team_id`/`_tz` init=False fields,
  `feed_title` / `feed_stories`.
- `start()` classmethod: resolve team ID, run first `update()`, then
  `spawn_tracked(run_monitor_loop(widget, update_interval))`.
- Every core import comes from `led_ticker.plugin` (import-purity contract).
  Needed symbols (`TickerMessage`, `SegmentMessage`, `colors`, `make_color`,
  `run_monitor_loop`, `spawn_tracked`, `Color`, `ColorProvider`, `Font`,
  `FONT_DEFAULT`) are all on the public surface already.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).

### Shared helper (targeted refactor)

New in `teams.py`:

```python
async def resolve_team_id(session: aiohttp.ClientSession, abbr: str) -> int | None
```

Fetches `{MLB_API}/teams?sportId=1`, returns the ID whose `abbreviation`
matches, `None` on miss or request failure. The promotions widget calls it, and
`MLBScoreMonitor._resolve_team_id` becomes a thin wrapper over it (third copy
avoided). `standings.py` builds a full abbr→id *map* — a different shape — and
is intentionally untouched.

### update() data flow

1. Single schedule request for `[today, today + lookahead_days]` with
   `hydrate=game(promotions)`.
2. Parse into per-game records (date in local tz, cleaned + deduped promo
   names) for **home games only**: `teams.home.team.id == team_id`. Away-game
   promotions in the response are ignored.
3. Apply `filter`; pick the target game (today if it has matches, else the
   earliest future game with matches); flag `highlight` matches; sort
   highlighted-first; truncate to `limit`.
4. Build `feed_title` + one `SegmentMessage` story per promo; fall back to the
   empty states above when steps 2–3 produce nothing.

### validate_config

Classmethod with the same contract as `MLBScoreMonitor.validate_config`
(pre-coercion, returns `list[str]`, never raises):

- `limit` present but not a non-negative int → message.
- `filter` / `highlight` present but not a list of strings → message (catches
  the easy TOML mistake `highlight = "Loonie Dogs"`).

### Error handling

Any request/parse exception on the main schedule fetch → log via
`logger.exception`, set the "No Data" error state, return. Identical pattern
to the standings widget. A failed fallback probe degrades silently (debug log
only) to `No home games soon` / `Opens soon` per the empty-state table.

## Docs

- **README.md** (source of truth for the user-facing surface): new
  `baseball.promotions` section — config table, line format, empty-state
  behavior.
- **CLAUDE.md**: add `promotions.py` to the package-layout file map; add the
  widget to the overview list and the `register()` snippet.

## Testing

New `tests/test_promotions.py` (pattern: existing widget tests, stubbed
session/responses, `asyncio_mode = "auto"`):

- **Cleaning/dedup:** sponsor-tail stripping; exact-dup collapse; prefix-dup
  keeps the shorter name.
- **Selection:** today-with-promos chosen over future games; future game chosen
  when today has none; away games ignored; `filter` inclusion; `highlight`
  ordering + amber color; `limit` truncation after highlight sort.
- **Empty states:** promo-free homestand → "Next home game" line; empty
  schedule → opening-day probe (both `Opens <date>` and `Opens soon` arms);
  API error → "No Data".
- **validate_config:** bad `limit`, string-instead-of-list `filter`/`highlight`.
- **teams.py helper:** `resolve_team_id` hit/miss/failure; scores widget still
  resolves through the wrapper.

Existing guards that must stay green: `test_import_purity.py` (auto-covers the
new module), `test_smoke.py` (updated to assert `baseball.promotions`
registers), `ruff check src tests`.
