# flair.lightning transition — design

**Date:** 2026-07-19
**Status:** approved (brainstorm with James)
**Name decision:** `flair.lightning` (over `unzip`, `zigzag`, `crack`) — with the
electric-flicker bolt and strike-then-split behavior, the config line
`transition = "flair.lightning"` tells a reader exactly what they'll see.

## What it does

A lightning bolt zigzags across the screen over the outgoing widget, then the
crack it leaves pulls apart, revealing the incoming widget underneath.

Two phases (poker's proven phase shape):

- **Strike (t 0 → 0.45):** the outgoing widget draws normally every frame. A
  zigzag bolt draws itself left→right on top: a bright white "head" cluster
  advancing along the bolt path, leaving a dimmer electric blue-white trail
  with per-frame brightness flicker. At the end of the phase the bolt spans
  the full width.
- **Peel (t 0.45 → 0.95):** the outgoing cuts out at the strike's completion.
  Each frame: `snap_reset(canvas, incoming_bg_color)` + `incoming.draw` (full),
  then blackout of every pixel OUTSIDE the opened gap, then the two crack
  edges drawn as glowing zigzag lines. The gap is the bolt polyline duplicated
  at ±d(t): both edges move apart vertically until the gap covers the panel.
- **Snap (t ≥ SNAP_THRESHOLD 0.95):** standard — `snap_reset` with
  `incoming_bg_color` + `incoming.draw`.

Reveal-black-then-open was considered and rejected: James picked
"strike + peel" so the incoming is genuinely visible inside the gap as it
opens (the canvas is write-only — no GetPixel — so "outgoing halves slide
apart carrying their content" is infeasible; this is the honest best shape).

## Geometry

- The bolt is a seeded random-walk polyline in LOGICAL panel space: a vertex
  every ~6–10 logical px with alternating slope sign (true zigzag), y
  confined to the center third of the panel height. Piecewise-linear
  `crack(x)` between vertices gives a y for every column.
- Planned ONCE per firing. `seed = None` (default) replans a fresh bolt on
  every firing, detected via `t < last_t` — exactly poker's refire pattern.
  `seed = <int>` pins the bolt for tests/demos.
- Gap membership is a pure function: column x is revealed at
  `crack(x) − d(t) < y < crack(x) + d(t)`, with d(t) eased from 0 at cutover
  to ≥ panel height just below SNAP (guaranteeing full reveal — assertable
  deterministically, no accumulation).

## Rendering

- **Physical resolution:** bolt, crack edges, and blackouts paint to
  `unwrap_to_real(canvas)` (poker/dissolve pattern) so the bolt is a crisp
  ~2px line on the bigsign (thickness `max(1, scale // 2)`) and identical
  logic serves scale 1.
- **Colors:** head is white-hot (255, 255, 255); trail defaults to electric
  blue-white (~(150, 190, 255)) modulated by a per-frame deterministic
  flicker (rng seeded per firing — no wall-clock, no global random). The
  `color = [r, g, b]` knob replaces the trail tint; head stays white.
- **bg color:** peel frames and the snap both pass `incoming_bg_color`
  through `snap_reset`, matching the transition-wide symmetric-bg contract.

## Performance (designed-in, lessons from the poker perf arc)

Everything is a pure per-frame function — **no caches, no memos, no warm
threads, no accumulated state** beyond the per-firing polyline (a few dozen
vertices). The peel blackout iterates only the complement of the gap, which
SHRINKS as the gap opens; peak cost is one panel-scale SetPixel pass per
frame (~16K real px on bigsign), the same order fireworks already proved fine
on hardware. Uniform frame times by construction.

## Knobs

- `seed` (int, optional) — pins the bolt shape; default None = fresh bolt
  every firing.
- `color` ([r, g, b], optional) — trail tint; default electric blue-white.

Nothing else: segment pitch, amplitude band, head size, and thickness derive
from panel geometry. Unknown keys are rejected by the generic plugin
transition build path (clean ValueError).

## Class shape

`Lightning` in `plugins/flair/src/led_ticker_flair/flair/lightning.py`,
registered as `api.transition("lightning")` in the flair `register(api)`
(namespaced type `flair.lightning`). `min_frames = 24` (poker precedent).
Signature: `frame_at(t, canvas, outgoing, incoming, **kwargs)` honoring
`outgoing_scroll_pos` (strike phase) and `incoming_bg_color` (peel + snap).

## Tests (mirroring poker's suite shape)

- Knob validation: bad `seed`/`color` types raise ValueError naming the field.
- Endpoints: t=0 draws outgoing only, nothing painted by the effect; snap
  draws incoming over `incoming_bg_color`.
- No outgoing paint after cutover (t=0.6 → `outgoing.draw` not called).
- **Full reveal by snap, deterministic:** at t just below SNAP_THRESHOLD,
  every panel pixel satisfies the gap predicate on both geometries
  (160×16 scale 1; 256×64 scale 4) across a seed range — pure-function
  check, no frame sweep needed.
- Per-seed determinism: same seed → identical polyline.
- Refire replans: seed=None, t regressing → new polyline object.
- Physical resolution: through a ScaledCanvas, effect pixels land on the
  real canvas (wrapper's SetPixel not used for bolt/blackout).
- Registration: `flair.lightning` appears in the plugin's transition
  registrations.

## Performance verification (mandatory, lessons from the poker arc)

The poker CPU spin shipped because nothing measured frame times before
hardware. Lightning does not merge without:

1. **Frame-time sweep (dev benchmark, reported in the PR body):** simulate a
   full firing at engine-like 0.02 t-steps on bigsign dims (256×64, scale 4,
   fresh instance), report avg / worst frame ms and the worst frame's t.
   Gate: worst ≤ ~5× avg and no single-frame outlier at the cutover or
   anywhere else (poker's bug signature was 34ms vs 2.6ms avg at t=0.46).
   Repeat for a REFIRE (second firing, seed=None) — poker's root cause only
   showed on re-fires.
2. **First-ever firing in a fresh process:** time construction (must be ~0,
   nothing heavy in `__init__`) and the first frame (must be ms-class —
   lightning has no warm by design; this check proves no hidden import-time
   or first-touch cost crept in).
3. **CI-safe uniformity tripwire (committed test):** wall-clock asserts are
   flaky, so the committed guard counts WORK, not time: sweep a firing on a
   stub canvas recording SetPixel calls per frame; assert the worst frame's
   count ≤ ~1.5× the panel pixel count and (excluding the cutover frame's
   legitimate step) within a small factor of the median. A poker-style
   deferred-backlog bug fails this deterministically in CI.

## Visual gate

Before the implementation is finalized: render smallsign + bigsign smoke
GIFs of the prototype for James's review (the poker "hearts look like
shields" gate caught a real problem). Iterate on bolt jaggedness / flicker /
open easing there, not in the spec.

## Deliverables

- `lightning.py` + registration + tests in the flair package.
- Bigsign smoke-test config in `plugins/flair/examples/` (per stickers/poker
  convention).
- flair README transition entry. Docs-site catalog entry follows in the
  usual docs sweep, not this PR.
