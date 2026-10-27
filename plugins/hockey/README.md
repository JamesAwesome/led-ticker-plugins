# led-ticker-hockey

Live NHL scores for [led-ticker](https://github.com/JamesAwesome/led-ticker). One `hockey.scores` widget shows a held scoreboard per game: score, period, clock, shots on goal, power play (team and time left), empty net, finals and the next scheduled game. When a team you follow scores, the card plays a goal celebration on its next turn in the rotation.

> **Disclosure:** the data comes from the NHL's public web API (`https://api-web.nhle.com`). That feed is **unofficial and undocumented**. It needs no key and no account, but the NHL can change its shape at any time. The plugin parses it defensively: a bad or missing payload keeps the last good scores on the panel with a `STALE` label instead of crashing. This plugin is not affiliated with or endorsed by the NHL.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install (`led-ticker-core >= 4.30`).
- Internet access on the Pi.
- No API key.

## Install

This plugin auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add the package to your `config/requirements-plugins.txt` and rebuild:

```text
led-ticker-hockey
```

```bash
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-hockey
```

Once installed, the `hockey.scores` widget is available automatically.

## Widget: `hockey.scores`

Add a `[[playlist.section.widget]]` block inside a playlist section of your `config/config.toml`:

```toml
[[playlist.section.widget]]
type = "hockey.scores"
teams = ["PHI", "NYI"]
timezone = "America/New_York"   # for start times and the day boundary
```

`teams` is required (and must be non-empty) in the default `teams` mode. Everything else is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | string | `"teams"` | `"teams"`, `"league"` or `"live"` — see [Modes](#modes). |
| `teams` | list of strings | `[]` | NHL three-letter codes, case-insensitive (`["PHI", "NYI"]`). Unknown codes are rejected by `led-ticker validate` with a close-match hint. In `league` / `live` modes it sets priority and which teams celebrate. |
| `max_games` | int | `8` | Cap on games per rotation in `league` / `live` modes. |
| `final_hold_hours` | int | `6` | How long a final stays in the rotation, measured from the game's start time + 2 h 30 min (the feed carries no end time). |
| `timezone` | string | `"America/New_York"` | IANA timezone for start times (`TODAY`, `TONIGHT`, dates) and the day boundary. |
| `layout` | string | `"auto"` | `"auto"`, `"scoreboard"` or `"ticker"` — see [Layouts](#layouts). |
| `update_interval` | int | `15` | How often, in seconds, this widget refreshes its cards and asks the shared source to poll. **Floored at 10.** While a game is live the source polls at most every 15 s, or at the lowest `update_interval` below that among the widgets sharing it. A value below 15 therefore speeds up live polling. A value above 15 slows this widget: its cards refresh only every `update_interval` seconds, and if no other widget polls more often, so does the source. Quieter periods poll more slowly regardless — see [Polling cadence](#polling-cadence). |
| `hold_time` | float | `0.0` | Minimum per-card hold in seconds (a number ≥ 0). The engine uses the larger of this and the section's `hold_time`. While a celebration is pending the card asks for 4 s per goal **plus** the larger of this and 4 s for the board afterwards. |
| `padding` | int | `6` | Horizontal padding (logical px) after the line in the hi-res `layout = "ticker"` crawl (bigsign / longboi); it also counts toward whether the line fits and holds instead of scrolling. The scale-1 ticker, the held scoreboards and the celebration ignore it. A number >= 0 (a float is truncated to an int). |
| `demo` | bool | `false` | Render fixture games (a live power play, a goal celebration, an intermission, an OT final, a next game) with `PHI` and `NYI`, no network — for docs, gifs and hardware checks. The live game's goal celebrates on its first turn and again every third turn after (in `ticker` / `one_at_a_time` sections, about 12 s after each celebration ends) (set `teams = ["PHI"]` or similar: untracked goals only highlight the score). |
| `bg_color` | RGB list | none | Background fill at every scale (core paints it under every renderer, including the goal celebration). |
| `font_color` | RGB list / string / table | unset | Override all text color. Scale-1 `layout = "ticker"` only. The smallsign board, the goal celebration and the hi-res renderers paint their own palette. |
| `font` | string | core default | Font for the scale-1 ticker line. |
| `small_font` | string | `"5x8"` | Font for the scale-1 two-band scoreboard. |

### Modes

- **`teams` (default)** — only games involving your `teams`, per team in config order: its live game; else a final still inside `final_hold_hours`; else a game later today; else its next scheduled game (also how a game that starts after local midnight shows before puck drop). Two tracked teams playing each other are one card, not two.
- **`league`** — every NHL game today: your teams first, then other live games, then finals inside the hold, then games later today by start time. Capped by `max_games`.
- **`live`** — only games in progress, your teams first. Capped by `max_games`. With nothing live the widget has no stories, so the rotation skips it.

**Offseason:** when a tracked team has nothing scheduled this week or month, the plugin looks up the full season schedule (at most every 6 hours) for its next game, such as the season opener. If nothing is scheduled at all, that team contributes no card — so a section holding **only** a `teams`-mode widget can go dark in the offseason. Put the widget in a section with other content, or accept the dark panel (core idles it blank and keeps swapping).

### Layouts

- **`layout = "auto"` (default)** — `scoreboard` on **all three** signs (smallsign, bigsign, longboi). A held board reads better than a crawl on a 16-row strip, so `auto` never picks `ticker`.
- **`layout = "scoreboard"`** — a held board per game:
  - **smallsign (160×16, bitmap font):** two 8-row bands, away on top. Each band has a brand chip, the abbreviation, the score and `SOG nn` (`STALE` replaces the `SOG` label when the data is stale); `PP m:ss` or `EN` sits on that team's band during play (not in intermission); the period is right-aligned in the top band and the clock in the bottom band. Columns move right as needed so 2-digit scores and shot counts never touch.
  - **bigsign (256×64):** two rows with a dotted divider — chip, abbreviation, large score, `SOG nn` (cyan) — and an amber **PP** badge on the power-play team's row. The right column shows the period (amber), the clock (white) and `PP m:ss`.
  - **longboi (512×64):** a full scoreboard. The away team fills the left third (chip, large abbreviation, `SOG`, huge score), the home team mirrors it on the right, and the centre holds the period, a large clock and the **PP** badge with `TEAM m:ss` beneath. Next-game cards add the team nicknames.
  - **Intermission:** the clock reads `2ND INT` with the countdown. **Empty net:** `EN` marks the team that pulled its goalie. **Final:** `FINAL`, `FINAL/OT` or `FINAL/SO`, the winner's score green and the loser's dimmed. **Next game:** the day and date (amber), the time (white) and the arena (dim), with the teams drawn per sign. Smallsign shows `PHI @ NYI` in team colors and no chips. Bigsign shows the away chip, `PHI @ NYI` and a `NEXT GAME` label. Longboi shows both chips and abbreviations on their sides, with the team nicknames and no `@`.
- **`layout = "ticker"`** — one scrolling line per game, using the same wording as the boards (`STALE` follows the period/clock when the data is stale). Scale-1 renders it as a bitmap `SegmentMessage`; scale>1 as a hi-res crawl.

Team abbreviations shrink to fit on the physical boards (both rows always share one size) and are ellipsized only when even the smallest size would collide. The physical boards use a fixed palette; only `bg_color` (the fill behind it) is configurable.

### Goal celebration

When a team in `teams` scores, that game's card plays a ~4 second celebration **the next time its turn comes around** — in a slideshow it never interrupts other content (scroll-mode sections are below). Three quick flashes of the panel in the scoring team's color with `GOAL` knocked out, then the new score with the scorer's number pulsing, the scorer and season goal count (`KONECNY (5)`), the assists, and the period and time. Then the normal board for the rest of the hold.

- A section's hold is **extended automatically** while a celebration is pending: the card asks for 4 s per queued goal plus the larger of the widget's `hold_time` and 4 s for the board that follows (the engine still uses the section's `hold_time` if that is longer). The celebration never eats the board's own time, so you do not need to raise `hold_time` for it.
- Several goals scored between turns celebrate in order, up to 3 per turn; older ones are dropped.
- A goal celebrates once per widget: replays on later rotations do not happen, and a celebration is only consumed once it actually reached the panel.
- **Scoring changes do not replay.** When the NHL corrects a goal (a new scorer or assist), the feed re-issues it; a goal at the same score as one already celebrated or queued replaces it — a queued celebration shows the corrected scorer — and never celebrates twice.
- During a transition into or out of the card, the board is shown; the celebration plays only once the card is on screen.
- In `mode = "ticker"` and `mode = "one_at_a_time"` sections, the celebration starts on the next frame the card is drawn and takes over the whole panel for its 4 s; the card's own scroll pauses underneath and resumes where it left off, so none of its board is skipped. On the bigsign and longboi the scoreboard scrolls through such a section like a wide card. Celebration and demo timing in these sections count scroll ticks (`scroll_step_ms`, default 50 ms), so the 4 s and 12 s figures scale with it. Known limit: only a goal that lands while the LAST card of a `ticker` section is already in the section's end-of-scroll hold is cut, to whatever is left of the section `hold_time` (default 3 s); the rest plays on the card's next pass (unless a section transition enters with that card first, which drops it). A longer `hold_time` makes this rarer but cannot rule it out.
- **First sight is a silent baseline.** Goals already in the feed when the widget first sees a game (boot, restart, hot reload, a game found mid-period) do not celebrate.
- In `league` / `live` modes, goals by teams you do not track do not flash; the score is highlighted briefly and fades back to white. With an empty `teams` list nothing celebrates.
- An overturned goal quietly corrects the score and drops any queued celebration for it.

### Polling cadence

All `hockey.scores` widgets in one process share a single source, so several widgets (or signs' worth of sections) do not multiply requests to the NHL.

- **Every 15 s** while any relevant game is live — faster if a widget sets a lower `update_interval` (floor 10 s), slower if every widget sharing the source sets a higher one (each widget polls only on its own `update_interval`).
- **Every 5 minutes** when relevant games are scheduled today but not started.
- **About hourly** otherwise.
- The season schedule (offseason next-game lookup) is fetched at most every 6 hours.
- The live "situation" lookup (power play, empty net) is made only for live games that are on screen.

Clocks (game clock, power-play time, intermission countdown) tick locally between polls: the board interpolates from the last poll's timestamp while the clock is running, and clamps at `0:00`.

A failed request keeps the last good games and marks every card `STALE` beside the state, never in place of it. Backoff starts at twice the interval and doubles, capped at four hours. A game that disappears from the feed keeps its last state — a final is never inferred from a game vanishing.

### Sign checks

The examples directory has separate demo and live configs for smallsign, bigsign and longboi:

- `config.hockey-demo.<sign>.toml` — fixture games, no network.
- `config.hockey-live.<sign>.toml` — live NHL data for `PHI` and `NYI`.

Validate the chosen file with `led-ticker validate <path>` before starting the sign. Every file carries a `[web]` block (the webui sidecar restart-loops without one), and the longboi files carry the FM6126A panel tuning (`gpio_slowdown = 5`, `pwm_bits = 7`, `limit_refresh_rate_hz = 100`) — without it that panel flickers, which is the panel, not the widget. Check that the score, clock and `PP` badge have separated letters and every column stays inside the panel.

## Known limitations

- **Unofficial feed.** Undocumented and subject to change; see the disclosure above.
- **Live situation fields are unverified.** The power-play and empty-net parsing follows community documentation of the game `landing` endpoint's `situation` data; it has not yet been checked against a live game. If those fields are absent or shaped differently, the board simply omits `PP` / `EN` and everything else keeps working.
- **Scale-1 clock updates per poll.** On a smallsign using `layout = "ticker"` the clock text refreshes with each poll rather than every second (the scoreboards, including the smallsign bands, and the hi-res crawl tick every second).
- **The sign runs ahead of your TV.** The feed is near real-time, broadcasts are delayed, so a goal can appear on the panel before you see it on screen. There is no spoiler delay.
- NHL only.

## Data

NHL web API, base URL `https://api-web.nhle.com`, no key. Community reference: <https://github.com/Zmalski/NHL-API-Reference>.

## Development

```bash
uv sync --extra dev                                    # from the repo root
uv run pytest plugins/hockey --cov=plugins/hockey/src  # tests
uv run ruff check plugins/hockey && uv run pyright plugins/hockey/src
```
