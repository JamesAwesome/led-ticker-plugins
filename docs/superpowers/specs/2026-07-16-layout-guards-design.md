# Layout collision guards: core primitives + fleet sweep — Design

**Date:** 2026-07-16
**Status:** approved. **Provenance note:** backfilled AFTER plan approval (the design was settled in conversation + a PM persona review, and went straight to plans at James's direction; this document records it in the standard spec location for the paper trail). The implementation plans are normative where they differ: core `docs/superpowers/plans/2026-07-16-hires-text-fit-api.md` (led-ticker repo) and `docs/superpowers/plans/2026-07-16-layout-guards-sweep.md` (this repo).

## Problem

Plugin layouts that paint hi-res text at fixed or computed positions were tuned for short data (≤5-char equity symbols) and carry **no collision guard**. Multi-asset data exposed the class on hardware three times in one release cycle (stocks #54): a wide price landed on the symbol's last letter (card), a 7-char pair nearly reached the fixed price block (dashboard hero), and the watch column's symbol touched its right-aligned percent. A fourth instance was found unshipped in flight's dashboard columns. Two aggravators make this class vicious:

1. **Dev metrics lie.** freetype advances differ macOS vs the Pi's Linux by ±px — a 3px "clearance" on a dev render is an overlap on the panel. Near-misses cannot be eyeballed; they must be measured.
2. **Measurement can drift from the paint.** Hand-rolled width math (or a different glyph-resolution path than the renderer's — the U+2212 class) produces clearances that aren't real.

## Decision history

- A PM persona review recommended: fix flight by copy-paste, encode the rule as prose, and extract a shared utility only at rule-of-three ("extract after two consumers, not one").
- **James overrode the extraction timing (2026-07-16): extract up front.** Rationale: two real consumers already exist (stocks shipped; flight surveyed needing the same shapes), and the requirement that **third-party plugins** be able to use it settles the location by itself — external plugins may import only `led_ticker.plugin`, so availability means the public core surface. The PM's other guardrails were kept (below).

## Design

### 1. Core public primitives (mechanism only)

Two functions in `drawing.py`, exported via `led_ticker.plugin.__all__` (a permanent contract; the api-reference drift test guards it):

- `hires_text_width(text, size, *, font="Inter-Bold", threshold=None) -> int` — physical advance width measured with `HiresFont.resolve_glyph` (the ASCII-fallback mechanism from the U+2212 fix), so collision math cannot drift from the paint on any platform. `threshold` forwards to `resolve_font` for font-cache sharing. BDF-alias edge (size ignored, logical px) documented explicitly.
- `fit_text_size(text, sizes, max_width, *, font=, threshold=) -> int` — the generic shrink-to-fit ladder: sizes tried in order, the last entry is the floor (returned even unfit), empty raises `ValueError`.

**Ladder VALUES never enter core.** Which sizes, which floors, which gaps — per-layout design decisions that stay in each plugin. Centralize the mechanism, never the values.

### 2. The convention (the durable asset)

CONTRIBUTING.md invariant, pointed to from per-plugin CLAUDE.mds: positioned hi-res text with variable-length data must (a) measure via `hires_text_width`, (b) shrink-to-fit via `fit_text_size` with a plugin-owned ladder, (c) ship an invariant-based pixel-separation regression test (never exact-pin sizes/widths — freetype macOS≠Linux), (d) **never ship <6px measured clearance**. Exempt: scrolling layouts (motion is the overflow mechanism) and fixed-vocabulary text.

### 3. The sweep (fix what's measured, not what's imagined)

Survey-first: an instrumented harness (spy on the plugin's `hires()`; record field extents; report inter-field gaps <6px and right-edge clipping; exclude by-construction composed pairs) renders each layout with a worst-case fixture. Only measured collisions get guards; safe surfaces get the survey recorded, not a refactor.

Scope: **flight** (survey found ONE genuine target: dashboard metric-column values, 3px at a column boundary, DIST overflowing its budget; hero flows with 31px slack — safe; ticker scrolls — exempt) · **stocks** (migrate its local `text_width` onto the core API; ladders unchanged) · **baseball** (audited already-safe: `_fit_team_name` fallback + measured-and-centered zones + fixed vocabulary; dated comment) · **crypto/pool/weather/calendar/rss/storefront/flair** (documented checked-no-retrofit: core-widget riders / scrolling / non-text).

### 4. Sequencing (the cross-repo version trap)

Nothing in the plugins calls the new API until the core release carrying it exists: core PR → core release vNext → gated sweep tasks (flight guards, stocks migration) pin `led-ticker-core>=<vNext>`. Ungated tasks (survey, baseball audit, convention) proceed immediately.

## Explicitly rejected (kept from the PM review)

- A shared monorepo util package (couples independently-versioned plugins; a shared-code bug becomes a coordinated multi-plugin release).
- Promoting ladders/layout helpers into core (freezes per-plugin design freedom; bloats a one-way-door API).
- Retrofitting core-widget-riding or scrolling plugins (core owns their overflow math).
- A layout DSL / responsive-layout engine; a shared pixel-test harness (the convention scales better than a code dependency for a solo maintainer).

## Testing

Core: TDD (7 tests: monotonicity, U+2212≡hyphen width, threshold pass-through, fit keeps/steps/floors/raises) + the api-reference drift test as the export's RED step. Plugins: per-surface failing pixel-separation test before each guard; the survey harness re-run as the fix's proof; full per-plugin CI gate (pytest + ruff check/format + pyright, CI-pinned versions).

## Releases

Core vNext (carries the API) → flight-v0.2.0 (floor bump + guards) → stocks-v0.6.2 (floor bump + migration; may ride the next feature release). James approves releases.
