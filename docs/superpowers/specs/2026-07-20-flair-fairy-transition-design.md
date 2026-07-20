# flair.fairy transition — design

**Date:** 2026-07-20
**Status:** approved (brainstorm with James)
**Inspiration:** Tinkerbell — a fairy crosses the sign trailing pixie dust,
leaves a line, and the line opens to reveal the next card.

## What it does

Three registered variants following the sprite-family convention:
`flair.fairy.forward` (flies left→right), `flair.fairy.reverse` (right→left),
`flair.fairy.alternating` (direction flips on every firing). Two phases:

- **Flight (t 0 → 0.5):** the outgoing widget draws normally every frame. A
  white-hot dot with a small gold halo crosses the panel along a
  nearly-straight path, scattering gold pixie-dust sparks behind it and
  settling a thin gold line at its path. Cutover is 0.5 (vs lightning's
  0.45) — the flight is the star.
- **Open (t 0.5 → 0.95):** the outgoing cuts out. Each frame:
  `snap_reset(canvas, incoming_bg_color)` + full `incoming.draw`, blackout of
  everything OUTSIDE the gap `path(x) − d(t) < y < path(x) + d(t)`, then the
  two edges drawn as thin gold lines decorated with TWINKLING SPARKS (fairy's
  signature vs lightning's solid glow). `d(t)` smoothsteps from 0 at cutover
  to `d_need` (max column distance to a panel edge + edge allowance) at 90%
  of the peel (`_OPEN_END = 0.9`), guaranteeing deterministic full reveal
  just below SNAP.
- **Snap (t ≥ SNAP_THRESHOLD 0.95):** standard `snap_reset` + incoming.

Same write-only-canvas constraint as lightning/poker: the reveal is against
black outside the gap; the incoming is genuinely visible inside from the
first sliver (and `bg_color` sections show their background there).

## Path

Nearly straight (James's pick over swoop/flutter): per firing, a baseline y
in the center third of the panel, a small overall drift (a few logical px
end-to-end), and a ±1–2 logical px sine wobble. Flattened to one y per REAL
column at plan time (single-valued — the reveal machinery requires it).
`seed = None` (default) replans a fresh path per firing via the `t < last_t`
refire detect; `seed = <int>` pins it. **Alternating** flips a direction flag
on every replan; forward/reverse pin it. Direction affects the head's travel
and which side the trail falls on; the settled line and the open phase are
direction-agnostic.

## Sparks (perf contract built in)

NO particle state. Every spark is a pure function of `(column, k, t)`:

- Columns within the trail length (~30% of panel width) behind the head
  spawn 1–3 sparks each; positions come from a deterministic per-firing hash
  (spark_seed mixed with column and k), scattered ±4 logical px vertically
  around the path.
- Brightness = falloff by distance-behind-head × a twinkle factor keyed on
  quantized t (same no-wall-clock trick as lightning's flicker).
- Palette: gold core `(255, 215, 120)`, cream highlight `(255, 240, 200)`,
  deep amber `(230, 170, 60)`; the `color` knob re-tints the dust (all three
  derived from it); the head stays white-hot `(255, 255, 255)`.
- Spark size: 1 px at scale 1; brighter sparks render as 4-point plus-stars
  (center + 4 neighbors) at scale > 1.
- Settled line thickness `max(1, scale // 2)`, dimmer gold than the sparks.

Per-frame cost is uniform by construction (hash + paint, no state, blackout
complement shrinks as the gap opens). Same committed `TestPerfUniformity`
work-count tripwires as lightning (per-frame SetPixel ≤ 1.5× panel px, first
firing AND refire), plus the sweep/refire/fresh-process benchmark gates in
the PR body.

## Knobs

- `seed` (int, optional) — pins path + spark field; default None.
- `color` ([r, g, b] 0–255, optional) — pixie-dust tint; default gold.

Direction is NOT a knob — it lives in the three registered variants.

## Registration

`Fairy` class in `plugins/flair/src/led_ticker_flair/flair/fairy.py`;
`register(api)` registers `api.transition("fairy.forward")(...)`,
`("fairy.reverse")`, `("fairy.alternating")` — config types
`flair.fairy.forward` etc. (Planning step verifies the two-dot type resolves
through the registry + `_build_trans_obj`'s plugin path; the sprite families
prove the `.forward/.reverse/.alternating` UX at namespace level.) The three
variants share one class parameterized by direction mode — likely
`functools.partial`-style factory or thin subclasses; implementer's choice,
provided each registered TYPE constructs independently with its own state.
`min_frames = 24`.

## Code shape

Self-contained `fairy.py`: the ~25-line gap/blackout open-phase core is
DUPLICATED from lightning, not extracted — rule of three (core factored
`draw_text_run` at the third consumer); coupling shipped lightning's render
loop to a new sibling adds churn risk for little gain. Revisit extraction if
a third line-reveal transition appears.

## Tests (mirroring lightning's suite)

- Path plan: determinism per seed, covers every column, y confined to the
  center third ± wobble slack, near-straightness (max deviation from the
  chord bounded), single-valued by construction.
- Knob validation: bad `seed`/`color` raise ValueError naming the field.
- Endpoints: t=0 outgoing only + no paint; snap = incoming over bg; no
  outgoing draw after cutover; flight frame paints sparks + white head over
  outgoing.
- Full reveal just below SNAP: deterministic, 8 seeds × both geometries
  (160×16 scale 1, 256×64 scale 4), incoming fills (7,7,7), zero black px.
- Refire: seedless replans (new path object); seeded keeps plan;
  **alternating flips direction on each refire** (forward/reverse don't).
- Physical resolution: through a ScaledCanvas the trail/line lands on the
  real canvas at real-pixel thickness, not block-expanded.
- Registration: all three `fairy.*` variants present and distinct-instance
  constructible.
- Perf uniformity: the two work-count tripwires.

## Performance verification (mandatory — lightning-convention gates)

1. Frame-time sweep on bigsign dims, fresh instance + seedless refire:
   worst ≤ 5× avg, no cutover outlier; numbers in the PR body.
2. Fresh-process construction (~0) + first-ever frame (ms-class; no warm,
   no caches).
3. The committed `TestPerfUniformity` tripwires above.

## Visual gate

Bigsign + smallsign GIFs (all three variants at least once; alternating
shown across two firings) — HARD STOP for James before the PR. Expected
tuning surface: spark density, twinkle rate, trail length, halo size.

## Deliverables

- `fairy.py` + registration + tests.
- Bigsign smoke config `plugins/flair/examples/config.fairy-smoke.bigsign.toml`
  (sections: forward / reverse / alternating / seeded / tinted / bg-hold /
  perf-feel — trimmed to the poker/lightning smoke shape).
- flair README entry + committed demo GIF. Docs-site catalog entry follows
  in the next docs sweep (with lightning's).
- Release after merge word: `cut_release.py flair minor` → flair-v0.12.0.
