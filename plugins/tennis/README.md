# led-ticker-tennis

Live tennis scores — ATP, WTA, Challenger, ITF and juniors — for [led-ticker](https://github.com/JamesAwesome/led-ticker). One `tennis.scores` widget cycles through every match in play (two players, sets, games, the point in progress, who is serving, break points) and falls back to the upcoming fixtures when nothing is on court.

> **Disclosure:** this plugin is maintained by the vendor of its data source, the [Live Tennis API](https://livetennisapi.com). It uses the API's **free tier** (no card; 100 requests/day), and the plugin enforces a poll cadence that stays inside that quota.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install (`led-ticker-core >= 4.16`).
- A Live Tennis API key — free at <https://livetennisapi.com/subscribe/free>. Put it in the environment as `LIVETENNIS_API_KEY` (recommended) or in the widget config as `api_key`.
- Internet access on the Pi.

Without a key the widget does not crash or fetch anything: it shows `Tennis: set LIVETENNIS_API_KEY (free key: …)` on the panel until one is configured.

## Install

This plugin auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add the package to your `config/requirements-plugins.txt`, pass the key through, and rebuild:

```text
led-ticker-tennis
```

```yaml
# compose override — hand the key to the container
services:
  led-ticker:
    environment:
      LIVETENNIS_API_KEY: "ltapi_..."
```

```bash
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-tennis
export LIVETENNIS_API_KEY=ltapi_...
```

Once installed, the `tennis.scores` widget is available automatically.

## Widget: `tennis.scores`

Add a `[[playlist.section.widget]]` block inside a playlist section of your `config/config.toml`:

```toml
[[playlist.section.widget]]
type = "tennis.scores"
tours = ["atp", "wta"]          # optional — omit for every tour
timezone = "America/New_York"   # for fixture start times
```

**No field is required** (the key comes from `LIVETENNIS_API_KEY`). Everything below is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key` | string | `""` | Live Tennis API key. The environment variable `LIVETENNIS_API_KEY` takes precedence. Keep credentials out of `config.toml`. |
| `tours` | list of strings | `[]` (all) | Any of `"atp"`, `"wta"`, `"challenger"`, `"itf"`, `"juniors"`. Filtered client-side, so it never costs extra requests. |
| `draw` | string | `"all"` | `"all"`, `"singles"` or `"doubles"`. Doubles teams show as `CASH/GLASSPOOL`. |
| `max_matches` | int | `8` | Cap on matches per rotation (main tours first, then earliest start). |
| `layout` | string | `"auto"` | `"auto"`, `"ticker"` or `"scoreboard"` — see below. |
| `show_ranking` | bool | `false` | Append the official singles ranking after each name on the ticker layouts, e.g. `LEHECKA (21)`. |
| `timezone` | string | `"America/New_York"` | IANA timezone for fixture start times (`Today 3:00 PM`). |
| `update_interval` | int | `900` | Seconds between API polls. **Floored at 900** (15 min) whatever you set — see [Free-tier cadence](#free-tier-cadence). |
| `padding` | int | `6` | Horizontal padding (logical px) after each story when scrolling. |
| `demo` | bool | `false` | Render four fixture matches (break point, tiebreak, retirement, upcoming) with no key and no network — for docs and hardware checks. |
| `bg_color` | RGB list | none | Background fill. Scale-1 only — the scale>1 physical renderers paint their own palette. |
| `font_color` | RGB list / string / table | unset | Override all text color. Scale-1 only. |
| `font` | string | `"6x12"` | Font for the scale-1 ticker line. |
| `small_font` | string | `"5x8"` | Font for the scale-1 two-band scoreboard. |

### Layouts

- **`layout = "auto"` (default)** — `ticker` on a scale-1 sign (smallsign), `scoreboard` on scale>1 signs (bigsign, longboi).
- **`layout = "ticker"`** — one scrolling line per match in tennis notation, the serving player marked with `*`:
  `LEHECKA* v FILS 4-6 3-4 (15-40) BP · SET 2 · R16 CINCINNATI OPEN`. Finished: `PAUL v VALLEJO 6-2 3-1 · RET · R32 …` (winner green). Upcoming: `ALCARAZ v SINNER · Tmrw 3:00 PM · QF …`. Scale-1 renders it as a BDF `SegmentMessage`; scale>1 as a hi-res Inter crawl with the same words.
- **`layout = "scoreboard"`** — a held two-row board, player 1 over player 2:
  - a yellow **serve dot** left of the server's name;
  - **longboi (512 px)**: one column per set with that set's games, then the current-game **points** (`15` / `40` / `AD`; tiebreak points as plain numbers);
  - **bigsign (256 px)**: the compact form — **sets won**, **current-set games**, points;
  - a red **`BP`** badge on the receiver's row at break point (never during a tiebreak);
  - a right-hand status column: `SET 2` / `SUSP` (green) or `FINAL` / `RET` / `W/O` / `DEF` / `ABD` / `CANC`, then the round (or `TB` during a tiebreak), then the tournament. Upcoming matches show `Today` / `3:00 PM` instead.
  - On a scale-1 sign the same content renders as two 8-row BDF bands (`LEHECKA*  4 3 15   S2` over `FILS  6 4 40 BP  R16`).

Names are surnames (upper-case), shrink-to-fit on the physical board and truncated only when even the smallest size collides; both rows always share one name size. Nothing on the board is user-tunable (fixed Inter text and palette, like the other physical renderers in this repo).

### How tennis is modelled (for the non-tennis reader)

A match is best-of-3 (or 5) **sets**; a set is first to 6 **games** (by two, or a **tiebreak** at 6-6); a game is scored in **points** `0 → 15 → 30 → 40 → game`, with `AD` (advantage) after deuce (40-40). One player **serves** an entire game and is expected to win it, so a **break point** — the receiver one point from winning the server's game — is the moment that matters: receiver at `AD`, or receiver at `40` while the server is at `0`, `15` or `30`. Tiebreak points are counted `1, 2, 3…` and have no break points. Matches end normally (`FINAL`), or early by retirement (`RET`), walkover (`W/O`), default (`DEF`) or abandonment; `SUSP` is a live match paused for rain/darkness.

### Free-tier cadence

The free tier allows 100 requests per day. All tennis widgets in one process share a source for each API key.
Every request waits at least 900 seconds after the previous request. This allows at most 96 requests per day during continuous operation.
The smallest configured interval wins, with a 900-second floor. Listings and result lookups use the same request slots.
There is no extra startup request. An empty live listing sends the next poll to the upcoming listing.

When a displayed match disappears, its last score stays visible with a `STALE` label.
The source queues a free `GET /matches/{matchId}` lookup, alternating result lookups with live polls.
A completed response supplies the final score, outcome and winner. Finished matches take priority for two intervals before leaving the rotation.

A successful lookup is cached and never repeated during that process lifetime.
Missing detail responses show the last score as stale. A match that still reports live is never labelled final.
Network failures retry after backoff. No winner is guessed from an unfinished score.

The shared cache is local to one process. Separate processes and restarts do not share its request budget.
For three signs sharing a key, set every sign's interval to at least 2700 seconds. That totals 96 requests per day during continuous operation.
Other clients share the same quota. Frequent restarts add requests, so leave headroom in the interval.

A failed request keeps the cached score and marks it `STALE` on the panel.
Backoff doubles from twice the interval, up to four hours. Authentication failures wait at least an hour, or longer when the interval requires it.
At the default interval, result lookups can extend the live listing cadence to 30 minutes.
This plugin keeps the same minimum interval for paid keys.

### Sign checks

The examples directory has separate demo and live configs for smallsign, bigsign and longboi.
Use `config.tennis-demo.<sign>.toml` without a key, or `config.tennis-live.<sign>.toml` with `LIVETENNIS_API_KEY` in the environment.
Validate the chosen file with `led-ticker validate <path>` before starting the sign.
Check that `BP`, round labels and tournament names have separated letters. Check every score column stays inside the panel.

## Data

Live Tennis API, base URL `https://api.livetennisapi.com/api/public/v1`, header `X-API-Key`. Score arrays are player-major (`games = [[6, 3], [4, 4]]` reads 6-4, 3-4). Docs: <https://docs.livetennisapi.com>. Not affiliated with the ATP, WTA or ITF.

## Development

```bash
uv sync --extra dev                                   # from the repo root
uv run pytest plugins/tennis --cov=plugins/tennis/src # tests
uv run ruff check plugins/tennis && uv run pyright plugins/tennis/src
```

`tests/test_layout_scoreboard.py` is the pixel-separation regression test for the physical board (CONTRIBUTING.md layout invariant): it spies on every hi-res `hires()` call on worst-case data and asserts a >= 6 px measured clearance between neighbours on both scale>1 geometries.

## License

MIT — see [LICENSE](LICENSE).
