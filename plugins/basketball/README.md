# led-ticker-basketball

Live NBA scores for [led-ticker](https://github.com/JamesAwesome/led-ticker). One `basketball.scores` widget shows a held scoreboard per game: both teams' logos and big scores at the edges, the period and clock in the middle (red in a close finish), each side's points leader, finals and the next scheduled game. When a team you follow wins, the card plays a win celebration at the final buzzer on its next turn in the rotation. The team logos are bundled, so a sign never fetches an image.

> **Disclosure:** the data comes from ESPN's public site API (`https://site.api.espn.com`, with `https://site.web.api.espn.com` as a fallback host). That feed is **unofficial and undocumented**. It needs no key and no account, but ESPN can change its shape or block clients at any time. The plugin parses it defensively: a bad or missing payload keeps the last good scores on the panel with a `STALE` label instead of crashing. This plugin is not affiliated with or endorsed by ESPN or the NBA. Team logos are the teams' marks, bundled for display on your own sign.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install (`led-ticker-core >= 4.31`).
- Internet access on the Pi (for the scores; the logos are already in the package).
- No API key.

## Install

This plugin auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add the package to your `config/requirements-plugins.txt` and rebuild:

```text
led-ticker-basketball
```

```bash
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-basketball
```

Once installed, the `basketball.scores` widget (and the `:basketball.ball:` emoji, plus a logo emoji for every team) is available automatically.

### Team logo emoji

Every bundled logo is also an inline emoji, named after the team code in lower case: `:basketball.phi:`, `:basketball.bos:`, and so on. Use them in any text, such as a message, a section title or a two-row card:

```toml
[[playlist.section.widget]]
type = "message"
text = ":basketball.phi: PHILLY :basketball.phi:"
font = "Inter-Bold"
font_size = 28
```

On the bigsign and longboi a logo emoji is 32 px tall, cropped to the mark and up to 64 px wide, so a wordmark keeps its shape. On the smallsign it is an 8×8 sprite, which is a splash of team colour rather than a readable logo.

## Reading the board (if you don't follow basketball)

- **Quarters and overtime** — four 12-minute quarters (`Q1`–`Q4`), `HALF` at halftime, `END Q3` between quarters. A tie after Q4 goes to 5-minute overtime periods (`OT`, `2OT`, …) until someone leads.
- **The clock** — runs during play and stops on every whistle. Under a minute it shows tenths (`45.3`).
- **Clutch time** — the 4th quarter or overtime, two minutes or less left, and the score within 5 points. The clock turns **red**. That is the only thing red on the board.
- **Scores** — a basket is 2 points, 3 from behind the arc, 1 for a free throw. Three-digit scores (`112`) are the normal case, not the exception.
- **Points leader** — the player with the most points so far in the game for each team (`EMBIID 31`). Before tip-off nobody has any, so the leader lines are blank (the scoreboard feed's pregame leaders are season averages and are deliberately not shown).
- **Linescore** — points per quarter, `24-28 · 26-24 · …`, one number per period played. Longboi only, in orange.
- **Records** — a team's season record, wins-losses (`5-2`).

## Widget: `basketball.scores`

Add a `[[playlist.section.widget]]` block inside a playlist section of your `config/config.toml`:

```toml
[[playlist.section.widget]]
type = "basketball.scores"
teams = ["PHI", "NY"]
timezone = "America/New_York"   # for tip-off times and the day boundary
```

`teams` is required (and must be non-empty) in the default `teams` mode. Everything else is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | string | `"teams"` | `"teams"`, `"league"` or `"live"` — see [Modes](#modes). |
| `teams` | list of strings | `[]` | ESPN team codes, case-insensitive (`["PHI", "NY"]`; note the Knicks are `NY`, not `NYK`, and `GS`, `SA`, `NO`, `UTAH`, `WSH`, `BKN`, `PHX`). Unknown codes are rejected by `led-ticker validate` with a close-match hint (`NYK` suggests `NY`). In `league` / `live` modes it sets priority and which teams celebrate. |
| `max_games` | int | `8` | Cap on games per rotation in `league` / `live` modes. |
| `final_hold_hours` | int | `6` | How long a final stays in the rotation, measured from tip-off + 2 h 30 min (the feed carries no end time). Teams play most nights, so the default clears a result soon enough for the next game to show; raise it to keep last night's result up through the morning. |
| `timezone` | string | `"America/New_York"` | IANA timezone for tip-off times (`TODAY`, `TONIGHT`, dates) and the day boundary. |
| `layout` | string | `"auto"` | `"auto"`, `"scoreboard"` or `"ticker"` — see [Layouts](#layouts). |
| `logos` | bool | `true` | Paint the bundled team logos on the bigsign and longboi. `false` paints two-tone colour chips with the abbreviation instead. Ignored on the smallsign, which never shows logos. |
| `update_interval` | int | `15` | How often, in seconds, this widget refreshes its cards and asks the shared source to poll. **Floored at 10** (ESPN caches for 10 s). While a game is live the source polls at most every 15 s, or at the lowest `update_interval` below that among the widgets sharing it. A value below 15 therefore speeds up live polling; a value above 15 slows this widget (and, if no other widget polls more often, the source). Quieter periods poll more slowly regardless — see [Polling cadence](#polling-cadence). |
| `hold_time` | float | `0.0` | Minimum per-card hold in seconds (a number ≥ 0). The engine uses the larger of this and the section's `hold_time`. While a celebration is pending the card asks for 4 s for it **plus** the larger of this and 4 s for the board afterwards. |
| `padding` | int | `6` | Horizontal padding (logical px) after the line in the hi-res `layout = "ticker"` crawl (bigsign / longboi); it also counts toward whether the line fits and holds instead of scrolling. The scale-1 ticker, the held scoreboards and the celebration ignore it. A number >= 0 (a float is truncated to an int). |
| `demo` | bool | `false` | Render fixture games (a live clutch-time 4th quarter with a win celebration, halftime, an OT final, a next game) with `PHI` and `NY`, no network — for docs, gifs and hardware checks. The live card's win celebrates on its first turn and again every third turn after (in `ticker` / `one_at_a_time` sections, about 12 s after each celebration ends). Set `teams = ["PHI"]` or similar: an untracked winner does not celebrate. |
| `bg_color` | RGB list | none | Background fill behind the board, the ticker line and the celebration, at every scale. |
| `font_color` | RGB list / string / table | unset | Override all text color. Scale-1 `layout = "ticker"` only. The boards, the celebration and the hi-res renderers paint their own palette. |
| `font` | string | core default | Font for the smallsign board and the scale-1 ticker line. |

`small_font` is **not accepted** (`led-ticker validate` rejects it), unlike the football and hockey widgets. Those draw two 8-row bands in a small 5×8 font; the basketball smallsign board is one 16-row band, so it uses `font` (6×12 by default) to fill the height. Use `font` to change it.

### Modes

Basketball's unit is the **day**: ESPN's scoreboard returns today's games (the day rolls over on the Eastern clock), and a team plays three or four times a week.

- **`teams` (default)** — only games involving your `teams`, per team in config order: its live game; else a final still inside `final_hold_hours`; else its game later today; else its next scheduled game from the team's schedule. Two tracked teams playing each other are one card, not two.
- **`league`** — every game today: your teams first, then other live games, then finals inside the hold, then upcoming games by tip-off (games with a `TBD` time sort last). Capped by `max_games`.
- **`live`** — only games in progress, your teams first. Capped by `max_games`. With nothing live the widget has no stories, so the rotation skips it.

**Offseason:** when a tracked team has nothing scheduled at all, it contributes no story. A section holding only this widget in `teams` mode goes dark then; put something else in the section if that matters.

### Layouts

`layout = "auto"` resolves to `scoreboard` on all three reference signs.

- **Smallsign (160×16):** one 16-row band, `PHI 98  Q4 1:48  101 NY`: a thin team-colour chip at each end, the abbreviation in team colour, the score in white, and the period (amber) and clock (white, **red** in clutch time) centred between them. No logos at this size and no leader line (the `ticker` layout carries it). When two three-digit scores and long abbreviations crowd the centre it shrinks rather than collide: the period drops first (the clock alone), then `FINAL/OT` becomes `F/OT`, then it ellipsizes. `STALE` joins the centre when it fits and replaces it otherwise. On a next-game card the basketball (`:basketball.ball:`) sits in front of `NY @ PHI` so the card reads as basketball at a glance next to other sports, but only when the card still fits exactly as it would without it: the ball is always the first thing to go, before `STALE`, the weekday, AM/PM or the date.
- **Bigsign (256×64):** a horizontal arena board. A 36 px logo at each edge, a large white score beside each, and the period over the clock in the centre. Each side's points leader (`EMBIID 31`, cyan) runs along the bottom; where the name cannot fit at a readable size the line is dropped instead of shrunk.
- **Longboi (512×64):** the same arrangement with room to spare: 48 px logos, larger scores, and under each score a side line with the abbreviation, record and full leader (`PHI 5-2 · J. EMBIID 31 PTS`). The centre holds the period and a large clock, and below the scores runs the **orange per-quarter linescore strip** (`24-28 · 26-24 · …`, an `OT` column added as played). The strip spans the width of the two scores, so double overtime still fits; it shrinks to 8 px and is dropped rather than cut, and on an overtime final the `OT` label under `FINAL` takes its row.
- **`ticker`:** one scrolling line per game using the same wording as the boards: `PHI 98 · NY 101 · Q4 1:48 · J. EMBIID 31 · J. BRUNSON 28`. A final reads `PHI 115 · NY 118 · FINAL/OT` (no leaders); a future game reads `PHI 5-2 @ NY 4-3 · SAT NOV 1 7:30 PM · ESPN · <venue>`.

With `logos = false`, or for a team with no bundled logo, the bigsign and longboi paint a two-tone team chip and the abbreviation in the logo's place. Smallsign always uses chips.

Halftime, the end of a quarter and a delay show `HALF` / `END Q3` / `DELAY` with no clock. A final shows `FINAL` (plus `OT` beneath), the winner's score green and the loser's gray. A next game shows the day (`TONIGHT`, `SAT NOV 1`, amber), the tip-off (`TBD` when the league hasn't set it), both records and the venue, with the teams drawn per sign and a small `NEXT GAME` (or `PPD` when postponed) label. Nothing on the physical boards is user-tunable (fixed palette).

**Score changes** never interrupt anything: the changed team's score pulses in its team colour for about 1.5 s and fades back to white.

### Win celebration

When a team in `teams` **wins** at the final buzzer, that game's card plays a ~4 second celebration **the next time its turn comes around** — in a slideshow it never interrupts other content (scroll-mode sections are below). A few quick flashes of the panel in the winner's colour with `76ERS WIN` knocked out (`PHI WIN` when the nickname will not fit), then the detail: the final score with the winner's number pulsing, `FINAL` (`FINAL/OT`), the winner's points leader and the winner's logo. Then the normal board for the rest of the hold.

- Only **wins** celebrate. A tracked team's loss settles onto the final board (winner green, loser gray) with no flash, and there is nothing per basket: no per-score flashes, run alerts or lead-change alerts.
- **Once per game per widget.** A celebration is only consumed once it actually reached the panel.
- A section's hold is **extended automatically** while a celebration is pending: 4 s for the celebration plus the larger of the widget's `hold_time` and 4 s for the board that follows.
- **First sight is a silent baseline.** A game that is already final when the widget first sees it (boot, restart, hot reload) does not celebrate; only a game this widget watched go from live to final does.
- In `league` / `live` modes, wins by teams you do not track do not celebrate; the board just shows the final. With an empty `teams` list nothing celebrates.
- In `mode = "ticker"` and `mode = "one_at_a_time"` sections, the celebration starts on the next frame the card is drawn and takes over the whole panel for its 4 s; the card itself resumes where its takeover began, while anything to its left keeps scrolling underneath, so up to about 80 px of a neighbour can pass unseen behind a celebration. On the bigsign and longboi the held scoreboard scrolls through such a section like a wide card. Known limit: a win that lands while the last card of a `ticker` section sits in its end-of-scroll hold is cut to the remainder of that hold (the section's `hold_time`, default 3 s) and resumes on the next pass.

### Polling cadence

All `basketball.scores` widgets in one process share a single source, so several widgets do not multiply requests to ESPN.

- **Every 15 s** while any relevant game is live — faster if a widget sets a lower `update_interval` (floor 10 s), slower if every widget sharing the source sets a higher one.
- **Every minute** in the half hour around a relevant tip-off.
- **Every 5 minutes** when a relevant game is scheduled later today.
- **About hourly** otherwise.
- A tracked team's schedule (for the next game) is fetched at most every 6 hours, and only when the team has no game left in today's payload.
- **Late games:** when a game the source saw live drops out of today's payload (a West-coast game that ran past midnight Eastern), yesterday's slate is fetched too so the game keeps its real state. A live game missing from a single payload is kept live for up to 30 minutes.

**The clock does not tick between polls.** A basketball clock stops on every whistle and the feed carries no "running" flag, so the board shows the clock exactly as last polled.

A failed request tries the fallback host, then keeps the last good games and marks every card `STALE`: beside the status on the bigsign and longboi; on the smallsign it joins the centre when it fits and replaces the status otherwise. Backoff starts at twice the interval and doubles, capped at four hours. A game that disappears from the feed keeps its last state — a final is never inferred from a game vanishing.

### Sign checks

The examples directory has separate demo and live configs for smallsign, bigsign and longboi:

- `config.basketball-demo.<sign>.toml` — fixture games, no network.
- `config.basketball-live.<sign>.toml` — live ESPN data for `PHI` and `NY`.

Validate the chosen file with `led-ticker validate <path>` before starting the sign. Every file carries a `[web]` block (the webui sidecar restart-loops without one), and the longboi files carry the FM6126A panel tuning (`gpio_slowdown = 5`, `pwm_bits = 7`, `limit_refresh_rate_hz = 100`) — without it that panel flickers, which is the panel, not the widget. On the bigsign and longboi check the logos, the score, the clock and the leader lines; on the smallsign check the chips, the score, the clock and the red clutch clock. Every column should stay inside the panel with separated letters.

## Known limitations

- **Unofficial feed.** Undocumented and subject to change; see the disclosure above. ESPN has intermittently returned 403s to non-browser clients; the mirror host is tried automatically.
- **The live and final fixtures are hand-written.** No NBA game was captured live while the plugin was built, so the `leaders`, `linescores` and in-game clock parsing follow the community-documented shape and a captured scheduled-game payload (the hand-written fixtures are flagged `_handwritten` pending a real capture). If a field is absent or shaped differently the board simply omits it and everything else keeps working.
- **The sign runs ahead of your TV.** The feed is near real-time, broadcasts are delayed, so a score can appear on the panel before you see it on screen. There is no spoiler delay.
- **Logos at 36 px lose fine detail.** The bigsign logos are 36 px, and thin lettering (the Knicks' wordmark especially) reads as a blob. The longboi's 48 px logos hold up better. Near-black pixels are dropped as invisible on the panel.
- **Logo emoji on the smallsign are colour splashes.** At 8×8 a logo keeps its colours and rough shape, not its detail. A mostly-navy or mostly-black mark (the Capitals) is dim on any sign.
- **Smallsign dark team colours read dim.** A very dark primary (`UTAH` purple, for one) is lifted but still reads dimmer than the others at 3 px chip width.
- **Bigsign chip fallback with two 3-digit scores** (`logos = false`, or a missing logo) drops the abbreviation to keep clear of the score.
- NBA only.

## Data

ESPN site API, base URL `https://site.api.espn.com/apis/site/v2/sports/basketball/nba` (mirror `https://site.web.api.espn.com`), no key. Endpoints: `/scoreboard` (today's games, and yesterday's with `?dates=YYYYMMDD` when a live game vanishes from today's) and `/teams/{ABBR}/schedule` (next game). Quirks the parser handles: the scoreboard's team records are `records[].summary` while the schedule's are `record[].displayValue`; the Knicks are `NY`; `displayClock` reads tenths under a minute (`45.3`) and `0.0` at a buzzer; the scoreboard's pregame `leaders` are season averages (`pointsPerGame`) and are ignored, while the in-game `points` leader is shown. Community references: the [akeaswaran ESPN API gist](https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b), [pseudo-r/Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API).

**Logos** are 64×64 PNGs for all 30 teams under `src/led_ticker_basketball/assets/logos/`, listed in `MANIFEST.txt` with their source URL and fetch date. They are refreshed by a person running `tools/fetch_logos.py` (never by CI or a sign); the plugin decodes each once per size and replays cached pixels.

## Development

```bash
uv sync --extra dev                                            # from the repo root
uv run pytest plugins/basketball --cov=plugins/basketball/src  # tests
uv run ruff check plugins/basketball && uv run pyright plugins/basketball/src
```
