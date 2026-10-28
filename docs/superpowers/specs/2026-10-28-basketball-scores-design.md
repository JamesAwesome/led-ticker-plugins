# Basketball scores widget: design

**Date:** 2026-10-28
**Status:** brainstormed with James (short session: logos on the big panels, nothing annoying, bundle the logos); builder-checked; ready for planning
**Package:** `plugins/basketball/` → `led-ticker-basketball`, namespace `basketball`, widget `basketball.scores`, emoji `:basketball.ball:`
**Template:** `plugins/football/` (`football.scores`), itself a file-for-file sibling of `plugins/hockey/`. Every invariant in `plugins/football/CLAUDE.md` and `plugins/hockey/CLAUDE.md` is inherited unless this document says otherwise. **Where this document is silent, do what football does.**

## Basketball in one page (for a reader who doesn't follow the sport)

- **The game.** Two teams, four **quarters** of 12 minutes (`Q1`–`Q4`), a **halftime** after Q2, and 5-minute **overtime** periods (`OT`, `2OT`, …) until someone leads. Points come constantly: a basket is 2, from behind the arc 3, a free throw 1. A final score is typically 100–130 per side, so **three-digit scores are the normal case**, not the worst case.
- **The clock.** Runs during play, stops on every whistle (fouls, out of bounds, timeouts, free throws). The last two minutes of a close game take ten real minutes and are the whole reason anyone looks up at a scoreboard.
- **The season.** 30 teams, 82 games each, October to April, then playoffs into June. A team plays **three or four times a week**, games are nightly, mostly tipping off 7:00–10:30 PM Eastern. West-coast games end after midnight Eastern. The unit of the schedule is the **day**, like hockey, not the week like football.
- **Team codes.** ESPN's spellings throughout: `PHI` (Philadelphia 76ers), `NY` (New York Knicks — not `NYK`), `GS` (Golden State), `SA` (San Antonio), `NO` (New Orleans), `UTAH`, `WSH`, `BKN`, `OKC`, `PHX`, `CHA`.

The example teams in docs, demo data and example configs are the **Philadelphia 76ers (`PHI`)** and the **New York Knicks (`NY`)**, Atlantic Division rivals who play each other four times a season. Nicknames for the celebration are `76ERS` and `KNICKS`.

## Intent

Live NBA scores on the sign, built on the football/hockey machinery (shared ESPN source, persistent cards, modes, layouts, stale handling), but **visually its own thing**. Hockey and football share one skeleton: a coloured chip bar, the abbreviation, the score, two stacked team rows, a dotted divider, a status column on the right, and a full-panel flash on every score. Basketball breaks from that in four ways James asked for or agreed to:

1. **Team logos on bigsign and longboi** (the one thing James named). Not on smallsign — 16 rows is too few.
2. **A horizontal arena-scoreboard layout** on the big panels: logo and big score on each edge, the game state in the centre. Smallsign is a single 16-row band, not two 8-row bands.
3. **Nothing interrupts mid-game.** No per-basket flash (the NBA scores every 20 seconds). The only full-panel takeover is a tracked team's **win** at the final buzzer, once per game. Score changes pulse in place; a close finish turns the clock red.
4. **A points-leader line** (`EMBIID 31 PTS`) as the basketball-specific detail, in place of football's possession / down-and-distance.

## Prior art (quick, 2026-10-28)

The same open-source scoreboards as football (robbydyer/sports, tronbyt, HomeCourt, MMM-*) all have an NBA mode fed by the same ESPN endpoint. Every one of them shows logos — the hardware projects downsample ESPN's 500-px PNGs at runtime — and every one of them puts the teams side by side with the clock in the middle. None of them designs for a 16-row strip or a 512-wide panel, none handles the final-buzzer moment, and none shows the leaders. This plugin **bundles** pre-sized logo sprites instead of fetching at runtime (James's call, 2026-10-28): no network on the render path, demo and tests work offline, and the docs GIFs are rendered from the same assets a sign shows.

## Goals

1. Live score, quarter and clock, `HALF` / `END Q3` / `OT` / `2OT` / `DELAY`, per-team points leader; the clock in red in a close finish.
2. **Team logos** on bigsign and longboi, bundled in the package as pre-sized sprites, with a colour-chip fallback for an unknown team or a missing asset.
3. A **final-buzzer win celebration** for a tracked team, played when the card's turn comes around, once per game per widget.
4. Finals `FINAL` / `FINAL/OT` with the winner highlighted, held for `final_hold_hours`; next-game cards.
5. Modes `teams` / `league` / `live`; layouts `auto` / `scoreboard` / `ticker`.
6. A `:basketball.ball:` emoji (8×8 low-res plus a 32×32 hi-res) so messages can reference the plugin.
7. Works on all three reference signs under the layout invariant.
8. Shipped end to end: PyPI release, docs-site page with demo GIFs on all three signs, catalog entries.

## Non-goals

- Per-basket celebrations, scoring-run detection (`10-0 RUN`), lead-change alerts. James: "I don't want it to be annoying." A run detector also needs a judgment call about when a run starts; declined.
- A **loss** takeover. A tracked team's loss settles onto the final board (winner green, loser gray) with no flash. *My call from "cool"; flip to "both outcomes" is a one-line change in the celebration trigger.*
- Standings, play-by-play, box scores, odds, win probability, injuries. (The leader line is the one stat that ships.)
- Logos on smallsign. Agreed with James.
- Fetching logos at runtime. James chose to bundle them; a sign never makes an outbound image request.
- A locally ticking clock. The NBA clock stops on every whistle; show `displayClock` as polled (football's rule, not hockey's).
- WNBA / college basketball. The ESPN path differs only by league slug; a `league` knob is a possible later addition, not now.
- A spoiler / hide-score mode.

## Anti-goals

- A crash or frozen panel because the unofficial feed changed shape, returned 403, or a logo PNG failed to download or decode. Every failure degrades: stale games marked `STALE`, a missing logo replaced by the chip.
- Logo decoding on the render path. Sprites are decoded once per `(team, size)` on first use and cached; a missing or corrupt asset degrades to the chip, never raises.
- Overlapping or clipped text on any sign, including with two three-digit scores and `2OT`.
- Inferring a final from a game vanishing from the feed.
- Celebrating a win that was already final when the widget first saw the game (boot, reload, restart).
- Shipping with the ≥ 6 px clearance rule violated anywhere.

## Data source

ESPN's unofficial site API, exactly as football (`HOSTS` with the `site.web.api` mirror, descriptive User-Agent, `REQUEST_TIMEOUT`, gzip, never raises).

| Endpoint | Use |
|---|---|
| `GET /apis/site/v2/sports/basketball/nba/scoreboard` | **Today's games** (ESPN's day boundary, Eastern). Also fetched with `?dates=YYYYMMDD` for **yesterday** when a cached live game is missing from today's payload (a West-coast game that ran past midnight) — port hockey's `_yesterday_ids` handling, not football's week model. |
| `GET /apis/site/v2/sports/basketball/nba/teams/{ABBR}/schedule` | Per tracked team, the next `pre` game when the team has nothing today. Fetched at most every `SCHEDULE_INTERVAL` (6 h), football's rules (`SCHEDULE_TIMEOUT` 5 s, `SCHEDULE_RETRY`, held finals still fetch). |

**Not used:** `summary?event=` (play-by-play). Not needed: there is no per-score detection.

### Scoreboard field map

The NBA payload has the NFL shape. Per event `e`, `c = e.competitions[0]`:

- `e.id`, `e.date` (ISO Z), `e.shortName` (`"NY @ PHI"`), `e.season.type`.
- `e.status`: `period` (0 pre, 1–4, 5+ OT), `displayClock` (`"2:13"`, `"0.0"` at a buzzer), `type.name` (`STATUS_SCHEDULED`, `STATUS_IN_PROGRESS`, `STATUS_HALFTIME`, `STATUS_END_PERIOD`, `STATUS_DELAYED`, `STATUS_POSTPONED`, `STATUS_CANCELED`, `STATUS_FINAL`), `type.state` (`pre`/`in`/`post`), `type.detail` / `shortDetail` (`"Final/OT"`).
- `c.competitors[]`: `homeAway`, `score` (string), `winner`, `records[]{type:"total", summary:"5-2"}`, `linescores[]{value}` (one per period played), `team{id, abbreviation, location, name, color, alternateColor, logo}`, and `leaders[]`: entries named `pointsLeader`, `reboundsLeader`, `assistsLeader`, `rating`, each with `leaders[0].athlete{shortName, displayName}` and `leaders[0].displayValue` (`"31"` for points; the `rating` entry's value reads `"31 PTS, 10 REB, 5 AST"`). The leader line uses **`pointsLeader`** only.
- `c.venue.fullName`, `c.broadcasts[]{names[]}`, `c.neutralSite`.
- **`c.situation` is not expected** on the NBA scoreboard (no possession, no timeouts, no team fouls in this endpoint). Read it with `.get` anyway; nothing in the design depends on it.

**The field map above is from community documentation and the NFL twin; it must be confirmed against a captured payload before the model is finalised** (the first plan task). The live-event fixture must be a real capture, not hand-written, if any game is in progress during the build; the 2026–27 season is under way, so one will be.

Quirks to encode: `displayClock` can be `"0.0"` at an end-of-period buzzer (show `END Q3`, no clock); `STATUS_DELAYED` has `state == "in"` (key on the name); a score can go down (a correction — the board just follows); `team.abbreviation` for the Knicks is `NY`.

### Polling cadence (one shared source per session)

Hockey's day model: **15 s** while any relevant game is live (`MIN_INTERVAL` 10 s, `update_interval` below 15 speeds it up); **60 s** within 30 min of a relevant tip-off; **5 min** when a relevant game is later today; **hourly** otherwise. Schedule fetch at most every 6 h. Backoff 2×, doubling, capped 4 h. `LIVE_GRACE` 30 min for a live game missing from one payload, with yesterday's slate fetched as hockey does. `run_monitor_loop(..., splay=False)`.

### Logos

- `teams.py` carries the 30-team table (`abbrev`, `espn_id`, `city`, `nickname`, lifted `primary`/`secondary`) exactly as football's.
- **Assets:** `src/led_ticker_basketball/assets/logos/{ABBREV}.png`, one 64×64 RGBA PNG per team (30 files, a few KB each), produced by a checked-in reproducer `plugins/basketball/tools/fetch_logos.py` that downloads ESPN's 500-px PNGs (`https://a.espncdn.com/i/teamlogos/nba/500/{abbrev.lower()}.png`, the same slugs as the team table) and LANCZOS-downsamples them to 64×64 with the aspect preserved and centred on a transparent square. The script is run by a human with network (James, once per logo refresh); CI never runs it. A `MANIFEST.txt` beside the assets lists the source URL and fetch date per file so a refresh is reviewable. The wheel must include the `assets/` tree (`[tool.hatch.build.targets.wheel]` already packages the whole package dir; `test_smoke` asserts all 30 assets load via `importlib.resources`).
- A `_logos.py` module owns one process-wide cache: `sprite(abbrev, size) -> LogoSprite | None`, `functools.cache`'d on `(abbrev, size)`. First call decodes the bundled PNG with Pillow (already a core dependency), downsamples 64 → `size` with LANCZOS, alpha-composites over black, and keeps the pixels with alpha ≥ 128 as `LogoSprite(pixels: tuple[(x, y, r, g, b), ...], size)`. An unknown abbreviation, a missing file or a decode error returns `None` (logged once at DEBUG) and the renderer paints the chip. Pixels whose brightest channel is below a floor (**builder's call, ~40**) are dropped rather than painted: near-black is invisible on the panel and reads as a hole either way, so treat it as transparent. Pre-converted once; painting is a `SetPixel` loop on the unwrapped real canvas at physical coordinates (through `_paint.ShiftedReal` so a scrolling card clips at the edges).
- **Logo size per sign:** bigsign **36 px**, longboi **48 px** *(my call; the builder may tune ±8 px against the clearance test, and should look at both example teams rendered at the chosen size before settling — the Knicks logo is a word on a ball and is the hard case)*.
- **Demo mode and tests are fully offline**, logos included. Tripwires: `test_all_team_logos_decode` (every table entry has an asset that decodes at both sign sizes with ≥ 1 lit pixel inside bounds), `test_missing_logo_falls_back_to_chip`, `test_logo_pixels_respect_floor_and_alpha` (on a synthetic PNG).
- Config knob `logos` (bool, default `true`) turns logos off (chips everywhere), for users who prefer the siblings' look.

## Model

`GameInfo` (frozen dataclass): `game_id`, `state` (`future`/`live`/`final`), `status` (ESPN name), `away`, `home`, `away_score`, `home_score`, `period`, `clock`, `start_utc`, `time_tbd`, `venue`, `broadcast`, `away_record`, `home_record`, `final_ot: bool`, `neutral_site`, `away_leader: Leader | None`, `home_leader: Leader | None`, `away_linescores: tuple[int, ...]`, `home_linescores: tuple[int, ...]`, `polled_at`.

`Leader`: `name: str` (ESPN `shortName`, e.g. `J. EMBIID` → the renderer upper-cases and strips the initial when space is short: `EMBIID`), `points: int`.

Status lines (`status_lines(game, now, tz) -> (line1, line2)`): live `("Q3", "9:11")`; halftime `("HALF", "")`; end of period `("END Q3", "")`; OT `("OT", "4:02")`, `("2OT", …)`; delayed `("DELAY", "")`; final `("FINAL", "OT" | "")`; future `(day_label, tipoff)` with hockey's `TODAY` / `TONIGHT` / `SAT NOV 1` and `7:30 PM` or `TBD`; postponed `("PPD", "")`.

**Clutch** (`is_clutch(game) -> bool`): live, `period >= 4`, clock ≤ 2:00, `|away_score - home_score| <= 5`. *My call on the thresholds.* Drives the red clock only; nothing else changes.

**Score change pulse** (`_card.py`): when a poll changes a team's score, the card records `(team, frame)`; for the next **1.5 s** (30 frames) that team's score digits render in the team's primary colour fading to white (football's `highlight` fade, applied to every score change rather than only to untracked teams). No takeover, no sound, no hold extension.

## Celebration: the final buzzer

Trigger (in the source, shared by all widgets, baseline semantics as football's `plays_after_baseline`): a game the source has seen **live** moves to `final` with `winner` set. The source records one `FinalEvent(game_id, winner, loser, away_score, home_score, final_ot, winner_leader)` per game; a game first seen as `final` records nothing. Each widget keeps its own `_celebrated: set[game_id]` and queues a celebration only when the winner is in its `teams`.

Timeline: hockey/football's plumbing in `_celebration.py` / `_card.py` unchanged in shape — `CELEBRATION_SECONDS` 4 s (80 frames), consumed only once drawn on a live frame, `hold_time` property extends the hold, scroll-mode self-start, demo re-arm every third visit. The content differs:

- **Flash** (frames 0–29): three fills of the panel in the winner's primary colour with `76ERS WIN` knocked out (nickname + ` WIN`; `fit_text` to the panel, falling back to `PHI WIN`; smallsign uses the bitmap font).
- **Detail** (frames 30–79): the final score with the winner's number pulsing in team colour, `FINAL` (`FINAL/OT`), and the winner's points leader (`EMBIID 31 PTS`). Logos on the big panels where they fit.
- Max 1 queued per card (a game ends once). Non-tracked finals: nothing (the board just shows the final).

## Modes

| `mode` | Shows |
|---|---|
| `teams` (default) | Per tracked team in config order: its live game; else a final inside `final_hold_hours`; else its game later today; else its next game from the schedule endpoint. Two tracked teams playing each other are one card. |
| `league` | Every game today: tracked first, then live, then finals inside the hold, then upcoming by tip-off. Capped by `max_games`. |
| `live` | Games in progress, tracked first. Empty when nothing is live, so the rotation skips the widget. |

`final_hold_hours` **defaults to 6** (hockey's: teams play most days). `GAME_LENGTH` for the hold math is **2 h 30 min** from tip-off. Offseason: a tracked team with nothing scheduled contributes no story.

## Config surface

| Option | Default | Notes |
|---|---|---|
| `mode` | `"teams"` | `teams` / `league` / `live` |
| `teams` | `[]` | ESPN abbreviations, case-insensitive; required non-empty in `teams` mode; `difflib` hint on typos; `NYK` → `Did you mean 'NY'?` is the one people will hit. |
| `layout` | `"auto"` | `auto` / `scoreboard` / `ticker`; `auto` → `scoreboard` on every sign. |
| `logos` | `true` | Paint the bundled team logos on bigsign/longboi. `false` → colour chips. Ignored on smallsign. |
| `max_games` | `8` | `league` / `live` cap. |
| `final_hold_hours` | `6` | see Modes. |
| `timezone` | `"America/New_York"` | tip-off times, the day boundary. |
| `update_interval` | `15` | live cadence, floored at 10. |
| `hold_time`, `padding`, `demo`, `bg_color`, `font_color`, `font` | as football | |
| `small_font` | — | **Not accepted** (rejected as an unknown key). The smallsign board is one 16-row band drawn in `font` (default `FONT_DEFAULT`, 6×12), not football's two 8-row bands in 5×8. *Reviewer question, my call:* a 5×8 row in a 16-row band leaves half the strip dark; 6×12 uses the height, and at 6 px/char the worst case `[chip] PHI 148 · Q4 2:13 · 148 NY [chip]` is ~156 px of 160, which is exactly why the centre shrinks to the clock alone before anything ellipsizes. The smallsign celebration detail is therefore one row too. |

`_LIST_FIELD_HINTS` declared for `layout` and `mode` as the sibling packs do. `validate_config` rejects unknown keys the same way.

## Look

Palette (`_palette.py`, one hue per field): `WHITE` score/clock, `AMBER` period/date/tip-off, `CYAN` the leader line, `RED (230, 40, 40)` the clutch clock, `DIM` labels/dividers/records, `GREEN` final winner, `LOSER` gray. **Basketball orange `(255, 120, 30)`** is reserved for the emoji and the per-period linescore strip on longboi, so it reads as the sport's accent without fighting the team colours. Team chips: the 30-team table lifted so every colour has a channel ≥ 90 (near-black primaries — `BKN`, `SA` — use the lifted secondary as the chip's main colour, football's rule).

### Per sign (live)

- **Smallsign (160×16, ONE band):** `[chip] PHI 98 · Q4 2:13 · 101 NY [chip]` in the bitmap font: away chip (3 px) and abbreviation in the away primary, away score white, the centre `Q4 2:13` (amber period, white clock, red clock when clutch) centred, then the home score white and the home abbreviation in the home primary, home chip at the right edge. Halftime/end of period: the centre reads `HALF` / `END Q3`. Final: `FINAL` (`FINAL/OT` if it fits, else `F/OT`), winner's score green, loser's gray. Scores are three digits in the worst case; the centre shrinks to the clock alone before anything ellipsizes. No leader line at this size (the ticker layout carries it). Columns are measured and pushed, as `HockeyBandBoard`.
- **Bigsign (256×64):** horizontal. Away logo at the left edge (vertically centred), away score (large white, ~26–30 px) right of it; home score and home logo mirrored on the right. Centre column, centred on x = 128: period (amber) over the clock (white / red when clutch), with the abbreviations in team colour small under each score when the logo is a chip. Under the centre, the away and home **leader lines** (`EMBIID 31`, cyan, small), one on each side of the centre line. The abbreviation is *not* drawn next to a real logo — the logo is the identity.
- **Longboi (512×64):** the same arrangement with room to breathe: 48-px logos, 46-px scores, the abbreviation (team colour) and record (dim) under each score, the centre column with period, a large clock, and beneath it the **linescore strip**: `Q1 Q2 Q3 Q4` headers dim and the two teams' per-period points in orange, right-aligned columns, `OT` columns appended as played. Leader lines `EMBIID 31 PTS` / `BRUNSON 28 PTS` in cyan on their team's side.

### Other states

- **Halftime / end of period / delay:** the live board with `HALF` / `END Q3` / `DELAY` and no clock.
- **Final:** the board with `FINAL` and `OT` beneath when `final_ot`; winner green, loser gray; leaders stay.
- **Next game:** logos (chips on smallsign), `PHI @ NY` / `PHI VS NY` at a neutral site, records dim, day label amber, tip-off white (`TBD` dim), venue dim, a small `NEXT GAME` label (`PPD` when postponed). Longboi adds nicknames.
- **Ticker:** one line per game from a single `segments()` source shared by the scale-1 `SegmentMessage` and the hi-res crawl: `PHI 98 · NY 101 · Q4 2:13 · EMBIID 31 · BRUNSON 28`; future: `PHI @ NY · SAT NOV 1 7:30 PM · ESPN · MADISON SQUARE GARDEN`; final: `… · FINAL/OT`.

### Emoji

`emoji.py`: `BALL` (8×8 `PixelData`: orange ball, seams in a lifted dark brown `(110, 50, 20)`, never black) and `BALL_HIRES` (32×32 `HiResEmoji`, generated by a circle-plus-seams function in the module, as baseball's `_generate_baseball_hires`). Registered in `register()` as `api.emoji("ball", BALL)` + `api.hires_emoji("ball", BALL_HIRES)` → `:basketball.ball:`. (Core's standard pack already resolves `:basketball:` at hi-res only; the plugin's slug adds the low-res pair so it renders on smallsign too.)

## Demo data (`demo = true`, game data network-free)

Four PHI/NY cards: (1) **live** Q4 2:13, PHI 98 at NY 101 — clutch, red clock — leaders `J. EMBIID 31` / `J. BRUNSON 28`, linescores `24 26 25 23` / `28 24 27 22`, with a queued **final-buzzer win for PHI** (112–108) that celebrates on the first turn and re-arms every third visit, so the GIF shows the takeover without waiting for a game to end; (2) **halftime** PHI 54 NY 51; (3) **OT final** NY 118 PHI 115, leaders shown; (4) **next game** tomorrow 7:30 PM at Madison Square Garden, records `5-2` / `4-3`, broadcast ESPN. Logos come from the bundled assets, so the demo is fully offline.

*Note on (1):* the demo's "live card that then wins" differs from the siblings' "live card with a queued play": the demo celebration must be queued with the demo's final snapshot while the card itself keeps showing the live state, exactly as football's demo keeps showing `20–17` with a queued touchdown. Builder: reuse `demo_plays` → `demo_final`.

## Constraints

- Everything in `plugins/football/CLAUDE.md`, `plugins/hockey/CLAUDE.md` and `CONTRIBUTING.md`: import only `led_ticker.plugin`; no `from __future__ import annotations`; Python 3.14; `led-ticker-core >= 4.31` (the Pillow 13 floor every hi-res member moved to in #121); ruff, pyright, coverage ≥ 90; the layout invariant (measured widths, ≥ 6 px, row-uniform ladders, ellipsis at the floor) with a worst-case clearance tripwire on both physical signs — **two three-digit scores (`148`), `UTAH`/`WSH` abbreviations, `2OT 0:00.0`, `FINAL/OT`, the longest leader name the table can produce (`ANTETOKOUNMPO 50 PTS`), six linescore columns, `STALE`, and a logo in place** — and the smallsign twin.
- Hi-res text never pixel-pinned in tests. Logo sprites are tested for footprint (size, bounds, alpha/floor filtering) with a synthetic PNG and for decodability across the bundled set, never for the artwork's content.
- The fetcher never raises; never infer a final from a vanished game; first sight is a silent baseline (no win celebration for a game first seen final).
- Logo decoding happens once per `(team, size)`, off the poll path, and never raises; the render loop only ever replays cached pixels.
- Package shape mirrors football file for file, plus `_logos.py`, `emoji.py`, `assets/logos/` (+ `MANIFEST.txt`) and `tools/fetch_logos.py`: `scores.py`, `_source.py`, `_models.py`, `_card.py`, `_celebration.py`, `_scoreboard.py`, `layouts/{__init__,scoreboard,crawl}.py`, `_palette.py`, `_paint.py`, `teams.py`, `README.md`, `CLAUDE.md`, `Makefile`, `LICENSE`, `examples/config.basketball-{demo,live}.{smallsign,bigsign,longboi}.toml`.
- Monorepo wiring in the same PR: root `README.md` plugin row, `RELEASING.md` publishable list, `scripts/check_release.py` `PUBLISHABLE_PLUGINS` (+ `tests/test_check_release.py`).
- **Core-repo wiring** (a second PR, in `led-ticker`): `src/led_ticker/plugins_catalog.json` entry (PyPI + git source at `basketball-v0.1.0`) and `tests/test_plugins/test_catalog.py`; docs site `widgets/basketball.mdx` written per `docs/DOCS-STYLE.md` with the football page as the model (lead, DemoGif per sign, unofficial-feed Aside, "reading the board" for non-fans, OptionsTable, modes, layouts, celebration, polling, limitations, Related), `docs/content-source/widgets/basketball.md` options table, `plugins/available.mdx` section + `<PluginCatalog name="basketball" />`, `widgets/index.mdx` catalog row and live-data list, `astro.config.mjs` sidebar entry, `docs/site/demos-pinned/basketball-scoreboard-{smallsign,bigsign,longboi}.toml` (+ rendered GIFs under `public/demos-pinned/`; bigsign renders use the rows=64/cols=256/chain=1 geometry, plugin renders go through `uv run --project ../led-ticker-plugins`), `tests/test_docs_basketball_demo_drift.py` pinning the longboi snippet, and the `check-llms.mjs` budget if the page pushes it.
- **Release:** `basketball` must be added to the PyPI pending Trusted Publisher list before the first Release (core runbook §A.2 — James does this); then `scripts/cut_release.py basketball minor --notes …` per `RELEASING.md`; the `release` environment approval is James's click. The catalog's git `ref` and the docs' install line are written against `basketball-v0.1.0`.
- Fixtures: real trimmed events from a captured 2026-10-28/29 payload (a scheduled game, a live game if one is on, a final, an OT final if available), a trimmed `teams/PHI/schedule` fixture, a synthetic 64×64 RGBA PNG for the logo decode tests. No network in CI, and `tools/fetch_logos.py` is never invoked by tests or CI.

## Left to the builder

- Exact pixel geometry, ladders, logo sizes (within ±8 px of the spec), score sizes and the linescore column widths per sign, within the arrangement above and the football geometry constants.
- The near-black floor for logo pixels, and whether to apply a mild brightness lift to logo pixels below ~90 so navy/forest logos read on the panel (the chips are lifted; logos may want the same). Either belongs in `_logos.py` at decode time, not in the fetch script, so a tuning change needs no asset refresh.
- Whether the bigsign has room for the leader lines under the centre column at the chosen logo/score sizes; if not, the leaders drop to longboi-and-ticker only and the bigsign shows the record instead. The clearance test decides.
- Whether the smallsign centre reads `Q4 2:13` or just `2:13` with the period dropped first, when two three-digit scores push the columns; measure.
- Whether `FINAL/OT` fits the smallsign centre or shortens to `F/OT`.
- The exact shape of the leader name when space is short (`J. EMBIID` → `EMBIID` → ellipsis).
- The 32×32 hi-res ball's seam geometry.
