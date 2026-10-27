# led-ticker-football

Live NFL scores for [led-ticker](https://github.com/JamesAwesome/led-ticker). One `football.scores` widget shows a held scoreboard per game: score, quarter and clock, who has the ball, down and distance with the ball spot, timeouts remaining, the red zone lit in red, finals and the next scheduled game (with a `BYE WEEK` label when your team is off). When a team you follow scores, the card plays a touchdown / field goal / safety celebration on its next turn in the rotation.

> **Disclosure:** the data comes from ESPN's public site API (`https://site.api.espn.com`, with `https://site.web.api.espn.com` as a fallback host). That feed is **unofficial and undocumented**. It needs no key and no account, but ESPN can change its shape or block clients at any time. The plugin parses it defensively: a bad or missing payload keeps the last good scores on the panel with a `STALE` label instead of crashing. This plugin is not affiliated with or endorsed by ESPN or the NFL.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install (`led-ticker-core >= 4.30`).
- Internet access on the Pi.
- No API key.

## Install

This plugin auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add the package to your `config/requirements-plugins.txt` and rebuild:

```text
led-ticker-football
```

```bash
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-football
```

Once installed, the `football.scores` widget is available automatically.

## Reading the board (if you don't follow football)

- **Quarter and clock** — four 15-minute quarters (`Q1`–`Q4`), `HALF` at halftime, `END Q3` between quarters, `OT` for overtime. The clock stops after most plays, so it moves in fits and starts.
- **Possession** — the team with the ball has a marker beside its score (a small triangle on the big panels, a dot on the smallsign).
- **Down & distance** — `3RD & 4` means the offense is on its third of four tries and still needs 4 yards. `1ST & GOAL`: within 10 yards of scoring. The **spot** (`PHI 38`) is where the ball is: on PHI's half of the field, 38 yards from PHI's goal line.
- **Red zone** — inside the opponent's 20-yard line. The down & distance and the possession marker turn red.
- **Timeouts** — three pips per team: lit while a timeout is left, dim once used.
- **Scores** — a touchdown is 6 (then +1 for the kick or +2 for a conversion), a field goal 3, a safety 2.

## Widget: `football.scores`

Add a `[[playlist.section.widget]]` block inside a playlist section of your `config/config.toml`:

```toml
[[playlist.section.widget]]
type = "football.scores"
teams = ["PHI", "NYG"]
timezone = "America/New_York"   # for kickoff times and the day boundary
```

`teams` is required (and must be non-empty) in the default `teams` mode. Everything else is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | string | `"teams"` | `"teams"`, `"league"` or `"live"` — see [Modes](#modes). |
| `teams` | list of strings | `[]` | ESPN team codes, case-insensitive (`["PHI", "NYG"]`; note `WSH`, `LAR`, `JAX`, `LV`, `LAC`). Unknown codes are rejected by `led-ticker validate` with a close-match hint. In `league` / `live` modes it sets priority and which teams celebrate. |
| `max_games` | int | `8` | Cap on games per rotation in `league` / `live` modes. |
| `final_hold_hours` | int | `24` | How long a final stays in the rotation, measured from kickoff + 3 h 30 min (the feed carries no end time). A team plays once a week, so Sunday's result stays up through Monday by default; lower it to see the next game sooner. |
| `timezone` | string | `"America/New_York"` | IANA timezone for kickoff times (`TODAY`, `TONIGHT`, dates) and the day boundary. |
| `layout` | string | `"auto"` | `"auto"`, `"scoreboard"` or `"ticker"` — see [Layouts](#layouts). |
| `update_interval` | int | `15` | How often, in seconds, this widget refreshes its cards and asks the shared source to poll. **Floored at 10** (ESPN caches for 10 s). While a game is live the source polls at most every 15 s, or at the lowest `update_interval` below that among the widgets sharing it. A value below 15 therefore speeds up live polling. A value above 15 slows this widget: its cards refresh only every `update_interval` seconds, and if no other widget polls more often, so does the source. Quieter periods poll more slowly regardless — see [Polling cadence](#polling-cadence). |
| `hold_time` | float | `0.0` | Minimum per-card hold in seconds (a number ≥ 0). The engine uses the larger of this and the section's `hold_time`. While a celebration is pending the card asks for 4 s per score **plus** the larger of this and 4 s for the board afterwards. |
| `padding` | int | `6` | Horizontal padding (logical px) after the line in the hi-res `layout = "ticker"` crawl (bigsign / longboi); it also counts toward whether the line fits and holds instead of scrolling. The scale-1 ticker, the held scoreboards and the celebration ignore it. A number >= 0 (a float is truncated to an int). |
| `demo` | bool | `false` | Render fixture games (a live 4th quarter with a touchdown celebration, halftime, an OT final, a next game, a bye week) with `PHI` and `NYG`, no network — for docs, gifs and hardware checks. The live game's touchdown celebrates on its first turn and again every third turn after (in `ticker` / `one_at_a_time` sections, about 12 s after each celebration ends) (set `teams = ["PHI"]` or similar: untracked scores only highlight the score). |
| `bg_color` | RGB list | none | Background fill behind the board, the ticker line and the scoring celebration, at every scale. |
| `font_color` | RGB list / string / table | unset | Override all text color. Scale-1 `layout = "ticker"` only. The smallsign board, the scoring celebration and the hi-res renderers paint their own palette. |
| `font` | string | core default | Font for the scale-1 ticker line. |
| `small_font` | string | `"5x8"` | Font for the scale-1 two-band scoreboard. |

### Modes

Football's unit is the **week**: every team plays once between Thursday and Monday, and ESPN's scoreboard returns the whole week in one payload.

- **`teams` (default)** — only games involving your `teams`, per team in config order: its live game; else a final still inside `final_hold_hours`; else its game later this week; else its next scheduled game from the team's schedule (also how a bye week shows: the next game, labelled `BYE WEEK`). Two tracked teams playing each other are one card, not two.
- **`league`** — every NFL game this week: your teams first, then other live games, then finals inside the hold, then upcoming games by kickoff (games with a `TBD` kickoff sort last). Capped by `max_games`.
- **`live`** — only games in progress, your teams first. Capped by `max_games`. With nothing live the widget has no stories, so the rotation skips it.

**Offseason:** when a tracked team has nothing scheduled at all, it contributes no story. A section holding only this widget in `teams` mode goes dark then; put something else in the section if that matters.

### Layouts

`layout = "auto"` resolves to `scoreboard` on all three reference signs.

- **Smallsign (160×16):** two 8-row bands, away on top. Each band: a 3-px brand chip, the abbreviation, the score, the possession dot, three timeout pips, and the down & distance on the band of the team with the ball (`3RD & 4`, cyan; red in the red zone). The quarter is right-aligned in the top band, the clock in the bottom band. The ball spot is omitted at this size (the `ticker` layout carries it).
- **Bigsign (256×64):** two held rows, one per team, with a dotted divider. Each row: chip, abbreviation, a large white score, the possession triangle and the timeout pips. The right status column shows the quarter (amber), the clock (white) and `3RD & 4 · PHI 38` (cyan, red in the red zone; the spot is dropped first when the column is narrow).
- **Longboi (512×64):** a full scoreboard. The away team fills the left third (chip, large abbreviation, pips beneath, huge score), the home team mirrors it on the right, and the centre holds the quarter, a large clock and the down & distance line. The possession triangle sits between the possessing team's score and the centre.
- **`ticker`:** one scrolling line per game using the same wording as the boards: `PHI 20 · NYG 17 · Q4 2:13 · NYG BALL 2ND & 7 · PHI 24 · TOL 1-2`.

Halftime, the end of a quarter and a delay show `HALF` / `END Q3` / `DELAY` with no clock and no situation. A final shows `FINAL` (plus `OT`) with the winner's score green. A next game shows the day (`TONIGHT`, `SUN NOV 1`, amber), the kickoff (`TBD` when the league hasn't set it) and the venue (dim), with the teams drawn per sign. Smallsign shows `PHI @ NYG` (or `VS` at a neutral site) in team colors, no chips and no records, with ` BYE` after it in a bye week. Bigsign shows the away chip, `PHI 5-2 @ NYG 4-3` (the records drop first when the line is too wide) and a small `NEXT GAME` / `BYE WEEK` / `PPD` label. Longboi shows both chips and abbreviations on their sides with the records, the team nicknames and that label, and no `@`. Nothing on the physical boards is user-tunable (fixed palette).

### Scoring celebration

When a team in `teams` scores, that game's card plays a ~4 second celebration **the next time its turn comes around** — in a slideshow it never interrupts other content (scroll-mode sections are below). Three quick flashes of the panel in the scoring team's color with `TOUCHDOWN` / `FIELD GOAL` / `SAFETY` knocked out, then the new score with the scoring team's number pulsing, the play (`JALEN HURTS 12 YD RUSH`), `+PAT` / `+2PT` once the try is in, and the quarter and clock. Then the normal board for the rest of the hold.

- A section's hold is **extended automatically** while a celebration is pending: the card asks for 4 s per queued score plus the larger of the widget's `hold_time` and 4 s for the board that follows.
- **The extra point folds in.** A touchdown's kick or two-point conversion never celebrates on its own: it updates the queued celebration's score and `+PAT` / `+2PT` label.
- Several scores between turns celebrate in order, up to 3 per turn; older ones are dropped.
- A score celebrates once per widget: replays on later rotations do not happen, and a celebration is only consumed once it actually reached the panel.
- In `mode = "ticker"` and `mode = "one_at_a_time"` sections, the celebration starts on the next frame the card is drawn and takes over the whole panel for its 4 s; the scroll pauses underneath and resumes where it left off, so nothing is skipped. On the bigsign and longboi the held scoreboard scrolls through such a section like a wide card. Known limit: a score that lands during the last card's end-of-scroll hold in a `ticker` section is cut to the remainder of the section's `hold_time` (default 3 s); set the section's `hold_time` to 7 or more if that matters.
- **First sight is a silent baseline.** Points already on the board when the widget first sees a game (boot, restart, hot reload, a game found mid-drive) do not celebrate.
- In `league` / `live` modes, scores by teams you do not track do not flash; the score is highlighted briefly and fades back to white. With an empty `teams` list nothing celebrates.
- A **score correction** (ESPN occasionally revises a score downward) quietly fixes the board and drops any queued celebration for it.

Scores are detected from the change in each team's total between polls; the scoreboard feed carries no play list. The play text comes from the feed's `lastPlay` when it is the scoring play, so a celebration can occasionally show the score with no play text.

### Polling cadence

All `football.scores` widgets in one process share a single source, so several widgets (or signs' worth of sections) do not multiply requests to ESPN.

- **Every 15 s** while any relevant game is live — faster if a widget sets a lower `update_interval` (floor 10 s), slower if every widget sharing the source sets a higher one (each widget polls only on its own `update_interval`).
- **Every minute** in the half hour around a relevant kickoff.
- **Every 5 minutes** when a relevant game is scheduled later today.
- **About hourly** otherwise (the rest of the week, the offseason).
- A tracked team's schedule (for the next game and the bye week) is fetched at most every 6 hours, and only when the team has no game left in the current week's payload.

**The clock does not tick between polls.** A football clock stops after most plays and the feed carries no "running" flag, so the board shows the clock exactly as last polled (hockey's locally ticking clock would be wrong more often than right here).

A failed request tries the fallback host, then keeps the last good games and marks every card `STALE` beside the state, never in place of it. Backoff starts at twice the interval and doubles, capped at four hours. A game that disappears from the feed keeps its last state — a final is never inferred from a game vanishing.

### Sign checks

The examples directory has separate demo and live configs for smallsign, bigsign and longboi:

- `config.football-demo.<sign>.toml` — fixture games, no network.
- `config.football-live.<sign>.toml` — live ESPN data for `PHI` and `NYG`.

Validate the chosen file with `led-ticker validate <path>` before starting the sign. Every file carries a `[web]` block (the webui sidecar restart-loops without one), and the longboi files carry the FM6126A panel tuning (`gpio_slowdown = 5`, `pwm_bits = 7`, `limit_refresh_rate_hz = 100`) — without it that panel flickers, which is the panel, not the widget. Check that the score, clock, possession marker and timeout pips have separated letters and every column stays inside the panel.

## Known limitations

- **Unofficial feed.** Undocumented and subject to change; see the disclosure above. ESPN has intermittently returned 403s to non-browser clients; the mirror host is tried automatically.
- **The live `situation` shape is hand-written.** No game was live when the plugin was built, so the possession / down & distance / timeouts parsing follows the community-documented shape and a captured preseason payload. If a field is absent or shaped differently the board simply omits it and everything else keeps working.
- **Scores can collapse.** Polls are 10–15 s apart, so a touchdown and its extra point usually arrive together (`+PAT` from the start). Two scores inside one poll (a touchdown and a field goal, say) celebrate once.
- **The sign runs ahead of your TV.** The feed is near real-time, broadcasts are delayed, so a score can appear on the panel before you see it on screen. There is no spoiler delay.
- NFL only.

## Data

ESPN site API, base URL `https://site.api.espn.com/apis/site/v2/sports/football/nfl` (mirror `https://site.web.api.espn.com`), no key. Endpoints: `/scoreboard` (the current week) and `/teams/{ABBR}/schedule` (next game, bye week). Community references: the [akeaswaran ESPN API gist](https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b), [pseudo-r/Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API).

## Development

```bash
uv sync --extra dev                                        # from the repo root
uv run pytest plugins/football --cov=plugins/football/src  # tests
uv run ruff check plugins/football && uv run pyright plugins/football/src
```
