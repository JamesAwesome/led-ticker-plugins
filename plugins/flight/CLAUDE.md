# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-flight**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` (expanded once the widget lands) is the source of truth for the user-facing
surface. This file keeps the **load-bearing invariants** a contributor must respect. This is
a stub — it grows alongside the implementation tasks.

## Load-bearing invariants

- **The design handoff is normative.** `design/README.md` (plus `app.js`, `led-engine.js`,
  and `Flight Tracker LED Layouts.html`, all committed verbatim in `design/`) is the visual
  spec for this widget — semantic palette, airline color table, and every layout number.
  Copy those values as-is; do not "improve" or re-derive them.

- **The `js_round` rule.** All handoff geometry was authored against JavaScript's
  `Math.round` (half-up). Python's built-in `round()` is banker's-rounding (round-half-to-even)
  and will silently disagree with the handoff on `.5` boundaries. Every formula translated
  from the handoff must go through `js_round(v) = math.floor(v + 0.5)` instead of bare
  `round()`.

- **Never exact-pin hi-res font pixel output in tests.** Freetype rasterization differs
  between macOS and Linux, so a test asserting an exact pixel coordinate or count for hi-res
  text is a platform-fragile trap (bitten the `flair.lottery` widget once already — see
  led-ticker core memory). Assert "some pixels of color C exist in region R" for hi-res text.
  BDF glyphs and procedural bitmaps (fins, arrows, dots) render pixel-exact and may be pinned
  freely.
