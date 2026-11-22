# Antagonist loop — flair `feat/flair-display-fonts`

Roadmap item 3 (text styling, font route), plugin half of led-ticker #551 /
v4.35.0. Rules: fresh reviewer per cycle, full diff each cycle, cap 5, exit
when only LOW/DOCS remain (folded, then ship). Plan:
`docs/superpowers/plans/2026-11-22-flair-display-fonts.md`; spec in the core
repo `docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md`.

## Cycle 1 (the executing-plans final review, fresh opus)

VERDICT: 0 HIGH, 0 MEDIUM, 3 LOW, 4 DOCS. All folded in `4e53f1b`:

- DOCS→treated as a defect: "HELLO 123" at Bungee Outline 48 (266 real px) and "Fresh Donuts" at Londrina Shadow 52 (260 px) overflowed the 256-px panel and scrolled with the first letter cut. FOLDED: 44 / 48 (same fix applied to the live moonbunny demo).
- DOCS: GIF ended before the scrolling line played. FOLDED: `--duration 52`, upscale 2 (1.27 MB).
- LOW: Londrina Shadow at 56 clips g/p/q descenders at row 64. FOLDED: range 44-54.
- LOW: the user-stem collision test was vacuous (`default_threshold` of an unregistered name is always 128). FOLDED: stages `<tmp>/fonts/BungeeShade-Regular.ttf` via `_configure_user_font_dir`, asserts 128 vs 45 and the plugin path unchanged.
- LOW: `loaded` fixture asserted every workspace plugin loads. FOLDED: only flair must not be in `failed`.
- DOCS: README old-core note (an older core IMAGE refuses this flair at install; the warning path covers forced/local/rolled-back installs) and `two_row` "cannot" → "default two_row band". FOLDED.
- Verified clean: plugin root resolution (entry point and local dir), wheel + sdist carry fonts/licences/SOURCES, validate on the example has zero warnings, three mutations killed (threshold 128 → 5 tests; dropped `return` → 5; `flair/fonts/` path → 7), eleven test doubles additive.

## Cycle 2 (fresh opus; rotated lenses: scaled end-to-end draw, real run loop, plugin state across reloads, config surfaces, docs drift)

VERDICT: 0 HIGH, 0 MEDIUM, 1 LOW, 1 DOCS → loop exits. Folded in the next commit:

- DOCS: the cycle-1 fold put the Londrina note INSIDE the Fonts table, so the fourth row rendered as literal pipe text. FOLDED: note moved below the table; `test_readme_fonts_table_is_one_contiguous_block` (RED→GREEN) pins it.
- LOW: Bungee Shade at 56 clips accented capitals (É/Å lose the accent, Ç the cedilla). FOLDED: range 40-54, note names the cause.
- Measured (default 45 vs explicit 128, scale 4, 256×64): dangling ends 12/48 Bungee Shade, 19/25 Bungee Outline (lit 1611 vs 25), 1/86 Londrina Shadow, 2/128 Londrina Outline. Widgets 1-4 fit the panel (cursor 64 logical); only the scrolling line is wider.
- Real `app.run` headless pass, 80 s, random between-sections pool: no traceback, no breaker trips, all five sections cycle.
- Config surfaces: section title, `two_row` top (22 px on the 50/50 split), `countdown`, `clock`, image overlay right-aligned and scroll_over all validate, build, draw, and render pixel-identical to an explicit 45.
- Ledger correction: cycle 1's "validate misses a two_row hi-res top_font overflow" is wrong on core 4.35.0; validate does report it.
- Out of scope, pre-existing core: `load_plugins` does not clear `load_hires_font`'s cache (only `reset_plugins` does), so reset → lookup → load caches a `None` miss; only test harnesses hit it. HeadlessBackend ignores `pixel_mapper_config` (known render-demo limitation).

## Exit

0H/0M/3L/4D → 0H/0M/1L/1D. Two cycles. Next: draft PR, CI, James's merge call,
`flair-v0.25.0` tag on his go, then the moonbunny demo swapped to `flair.*`
names with the new pin.
