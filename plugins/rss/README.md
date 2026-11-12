# led-ticker-rss

An RSS/Atom headline **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker). It contributes a single `rss.feed` widget that polls a feed URL and scrolls each story headline across the panel as its own ticker message.

This package split out of `led-ticker-feeds` (its `feeds.rss` widget); the type is now `rss.feed`.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- Internet access on the Pi (the widget fetches the feed URL).

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`), then rebuild:

```text
led-ticker-rss
```

```bash
# in your led-ticker checkout
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-rss
```

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Configuration

```toml
[[sections]]
[[sections.widgets]]
type = "rss.feed"
url = "https://feeds.bbci.co.uk/news/rss.xml"
```

The widget is a Container: it pulls the feed in the background and expands each story into its own scrolling `TickerMessage`, so live updates surface within one display cycle.

### Options

| Field | Default | Meaning |
|---|---|---|
| `feed_url` | required | RSS/Atom URL to poll. |
| `update_interval` | `1800` | Seconds between polls. |
| `max_stories` | `5` | How many items to show per pass. |
| `font_color` | legacy 3-color cycle | Any core color provider; applied to every story. |
| `bg_color` | none | Background color for every story. |
| `font` | core default | Font name for every story. |
| `description` | `"off"` | `"append"` folds each item's description onto its headline (below). |
| `description_skip` | `[]` | Regexes; description paragraphs matching any (case-insensitive search) are dropped. |
| `description_max_chars` | `200` | Cap on the folded description text (characters, word boundary + `…`). `0` = no cap. |

### Showing an item's description / notes

By default each story is the item's `<title>` only. Set `description = "append"` and the
item's description is flattened to plain-text paragraphs (block tags split, inline tags
drop, `<img>` has no text, `<script>`/`<style>` contents drop, entities unescape) and the
survivors are appended to the headline with ` · ` separators:

```toml
[[playlist.section.widget]]
type = "rss.feed"
feed_url = "https://example.com/feed.xml"
description = "append"
description_skip = ["^Posted by", "^Read more"]
```

Filters run before the join, so the result stays a one-line headline:

- A paragraph that restates the title is dropped: its alphanumeric content equals the
  title's, or is a substring of it at least 8 characters long (feeds that repeat the
  headline's date or subject in the body). Short notes that merely share a word with the
  title are kept.
- Any paragraph matching a `description_skip` regex is dropped.
- The folded text (not the title) is capped at `description_max_chars`, cut at a word
  boundary with `…`.

Which field: feedparser's `summary`, i.e. RSS `<description>` / Atom `<summary>`; when an
item has neither, feedparser falls back to `content:encoded` / Atom `<content>` (the full
body), which is what the cap is for. Items whose description has nothing left render
exactly as before. An item with no `<title>` shows its folded description alone; with
`description = "off"` a title-less item is skipped. `description_skip` without
`description = "append"` is reported as a warning by `led-ticker validate`.

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/rss
uv run ruff check plugins/rss
```
