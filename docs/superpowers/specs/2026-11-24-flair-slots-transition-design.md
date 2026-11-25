# flair.slots transition — design

**Date:** 2026-11-24
**Status:** approved in chat by James 2026-11-24 ("start together stop in sequence, approved")
**Issue:** none yet
**Inspiration:** a mechanical slot machine's reels, one per character.

## Intent

A sibling of `flair.splitflap` with a different motion. Same job: the
outgoing message becomes the incoming one in place, every character
passing through a few in-between characters before landing. Where
splitflap's characters are flaps falling over a hinge, slots' characters
are **reels**: each one scrolls vertically through its in-between
characters, slows down, overshoots the landing by a hair and settles back
with a thunk, and the reels stop one after another left to right the way a
slot machine's do.

James asked for it as "a flair plugin called slot machine or slots that
makes letters spin into place like a slot machine; functions similar to
the splitflap but with the animation variation."

## Decided by James

- **The classic reel**, not the Vegas blur: each reel spins at a readable
  pace, decelerates over its last couple of characters, overshoots the
  landing by about a row and settles back. (Rejected: a dim smear that only
  resolves into characters as it slows.)
- **Build it on an extracted shared skeleton (approach B below)**, as two
  PRs: a behaviour-free refactor of splitflap first, then the effect.
- **Reels start together and stop in sequence** (not splitflap's
  staggered starts); see "Timeline".

## Claude's calls (stated to James, not objected to)

- **Register as `flair.slots.<order>`** with splitflap's four stop orders:
  `forward` (reels stop left → right, the classic), `reverse`,
  `alternating` (forward, reverse, … one per firing) and `random` (a fresh
  random stop order each firing — randomises the *settle order*, not the
  variant, exactly as `flair.splitflap.random` does).
- **Reels spin downward** (symbols travel down the window, the next one
  entering from the top), the way most machines read.
- **Knobs:** `spins` (in-between characters the first reel passes,
  default 3; the same role as splitflap's `flips`) and `stagger` (share
  of the run spent stopping reels one after another, default 0.5). Nothing else:
  no direction, bounce or speed knob until a visual gate asks for one.
- **Reuse splitflap's board layer verbatim.** Pairing by position, band
  correspondence, the in-between pool, strips for images, `static` cells —
  all come from `splitflap_board.build_board` unchanged. Slots is a new
  painter and a new per-reel timeline, nothing more.

## Resolved with James

- **Start together, stop in sequence** (chosen) vs staggered starts with
  equal spins (splitflap's ripple turned vertical). The first is what
  makes the effect read as a slot machine; its cost is that later reels
  pass more symbols (cycling the in-betweens) and a high `stagger` makes
  the last reel spin a long time at the same speed.

## Approaches considered

- **A. Share the data, write the firing loop fresh.** New `slots.py` +
  `slots_paint.py` importing `build_board`, `DeckSnapshotMixin` and the
  `_variants` wrappers, with its own `frame_at`. No risk to splitflap, but
  the ~40-line firing skeleton (refire detection, snap, board build,
  per-call `unwrap_to_real`) would exist twice and drift.
- **B. Extract the skeleton first, then subclass.** *(chosen)* A
  behaviour-free precursor PR pulls splitflap's `frame_at` / `_plan` /
  `_ripple` into a `_board_transition.py` base with two hooks; splitflap
  becomes a thin subclass pinned by its existing tests; slots is a second
  subclass plus its own painter. One more PR, but the one-owner rule
  already applied to `DeckSnapshotMixin` extends to the firing loop.
- **C. Copy splitflap's three files and edit.** Dropped: the flair
  CLAUDE.md forbids forking shared pieces, and it would duplicate every
  board tripwire.

## Goals

- Reads unmistakably as slot-machine reels on the bigsign (256×64,
  scale 4) for text; graceful and still recognisable for every widget type
  the snapshot transitions handle (two_row, gif/image/still, bordered,
  background effects, bg-coloured sections, letterboxed sections).
- Same conventions as the other flair snapshot transitions: snapshot once
  per firing, pure function of `t`, `SNAP_THRESHOLD` snap to the real
  incoming draw, `scale_switch_at = 1.0`.
- Splitflap byte-identical after the refactor PR; its tests pass with a
  single patch-target edit (see PR 1).
- No new core seams; core floor stays at the pack's current `>= 4.35`.

## Non-goals

- Live per-character spinning inside a widget (score/clock digits).
- Real alphabet or symbol strips (in-betweens are borrowed on-screen
  characters, as in splitflap).
- Reel frames, tiles, a payline, sound, a "jackpot" flourish when the last
  reel lands.
- A horizontal or random-direction spin.

## Anti-goals (a failure even if it technically works)

- Reads as a vertical wipe, a push-up transition, or flicker rather than
  reels turning.
- Reels landing dead with no deceleration or settle — that is a wipe with
  extra steps.
- A visible brightness pop on a reel's first or last frame.
- Any blank panel mid-transition, or a "border on black" flash at the
  snap.
- The border ring spinning with the text (it stays put, as in splitflap).
- Any change in splitflap's rendered output from the refactor PR.

---

## PR 1 — refactor: `_board_transition.py`

Behaviour-free. Extract from `splitflap.py` into a new private module:

- `BoardTransition(DeckSnapshotMixin)` holding what is effect-agnostic
  today: `min_frames = 36`, `scale_switch_at = 1.0`, `_order`, the
  `_board` / `_starts` / `_last_t` / `_rng` state, `frame_at` exactly as
  splitflap has it (refire on `t == 0.0 or t < _last_t`, snap at
  `SNAP_THRESHOLD`, lazy `build_board`, `real` re-derived every call,
  `s = min(t / SNAP_THRESHOLD / LAND, 1)`), and `_ripple` (via
  `flap_start`).
- Moved with it: `ORDERS`, `LAND`, `MAX_STAGGER`, `flap_start`, and the
  two coercers under effect-neutral names (`coerce_steps(value, name,
  cap)`, `coerce_stagger`); each effect keeps its own cap (`MAX_FLIPS =
  12` stays in `splitflap.py`, slots gets `MAX_SPINS = 6`) and the error
  text keeps the caller's knob name, so `flips must be an int in [0, 12]`
  is unchanged.
- Two hooks a subclass fills: `_paint(self, real, board, s)` and the
  constructor (which sets `self.steps` — the in-between count handed to
  `build_board` — and `self.stagger`, then calls the base init). The
  per-reel schedule is a third hook, `_schedule(board) -> list[float]`,
  whose base implementation is today's `_ripple` (start times via
  `flap_start`); slots overrides it to return stop times (see PR 2) and
  overrides `min_frames`. Keeping the schedule a hook is what lets PR 1
  carry splitflap's schedule unchanged while slots supplies its own.
- Known test coupling, verified: `test_snap_draws_incoming` monkeypatches
  `led_ticker_flair.flair.splitflap.snap_reset`; once `frame_at` lives
  in the base that patch no longer intercepts. Re-point that one test at
  `_board_transition.snap_reset` in PR 1 (the only patch target in the
  splitflap tests; `_board` / `_rng` are read as attributes and keep
  working).
- `splitflap.py` keeps its public surface: `SplitFlap`, `SplitFlapReverse`,
  `SplitFlapRandom`, `SplitFlapAlternating`, `LAND`, `flap_start`,
  `ORDERS`, `MAX_FLIPS` re-exported so `tests/test_flair_splitflap_*.py`
  import unchanged (one patch-target edit, above). `SplitFlap.flips` stays as the attribute name tests
  and configs see (alias of `steps`, or the subclass sets both — builder's
  call).
- Tripwire: a test asserting `SplitFlap` and (later) `Slots` subclass
  `BoardTransition` and that neither module defines its own `frame_at`
  (AST or `"frame_at" not in cls.__dict__`), so the skeleton can't be
  re-forked quietly.
- CLAUDE.md: the splitflap invariants section gains one bullet naming
  `_board_transition.py` as the ONE firing loop for board-style
  transitions.

## PR 2 — the effect

### Snapshots, cells, pairing

Identical to splitflap: `DeckSnapshotMixin` snapshots both widgets once
per firing; `build_board(out_plan, in_plan, spins, rng)` gives bands
(`BandGeom.lo/hinge/hi`, inclusive lit-row extent per band pair), reels
(`Flap.seq` = outgoing, in-betweens…, incoming; `static`; `centre_x`) and
the two border rings. The hinge is unused by slots.

### One reel

The **window** for a reel is its band pair's lit extent, rows
`[lo, hi]`, height `P = hi − lo + 1`. Every write is clipped to the
window (and to the panel); nothing paints outside it, so two_row bands
stay separate and the ring is never touched.

The reel's **strip** is `seq` stacked vertically at a fixed **pitch**
`pitch = P + gap`, `gap = max(1, round(P / 4))` (a dark gap between
symbols is what makes a stack of glyphs read as a reel rather than a
scrolling column; builder tunes at the visual gate). With the reel
displaced by `d` real rows, the `j`-th symbol on the strip (`j = 0` the
outgoing glyph, `j = k` the incoming one) is its cell's own rows shifted
by `−j·pitch + d` — cells keep their own `y` values and are never
re-anchored to the band top, so a short glyph stays where the font put
it. At `d = 0` the outgoing glyph sits in place; as `d` grows the strip
moves **down** and the next symbol enters from the top; at `d = k·pitch`
the incoming glyph sits in place. Each glyph is drawn at its own cell's `slot` (the board already
centres in-betweens on the incoming cell).

### Timeline

Per firing, `s = min(t / SNAP_THRESHOLD / LAND, 1)` as today, so every
reel has landed by `s = 1` and holds until the snap (splitflap's
`test_all_landed_before_snap` shape).

**Start together, stop in sequence (James's call).**
A slot machine's reels all start on the pull and stop one after another;
splitflap's ripple staggers the *starts*. The reel order (`forward` /
`reverse` / `random`) is the order the reels **stop**. With
`frac` = the reel's rank position from `flap_start` (0 first, 1 last):

- every reel starts at `s = 0`;
- reel stop time `stop = (1 − stagger) + stagger · frac`, so the first
  reel stops at `1 − stagger` and the last at `1`;
- all reels cruise at the **same speed**, so a reel that spins longer
  passes more symbols: glyph advances `k = round(K₀ · stop / (1 − stagger))`
  where `K₀ = spins + 1` is the first reel's count. Its strip is
  `seq[0]`, then the in-betweens cycled (`seq[1:-1]` repeated in order,
  so a reel with 2 in-betweens and `k = 7` shows a, b, a, b, a, b, new;
  with no in-betweens at all, the pool was empty, and the strip
  alternates outgoing / blank), then `seq[-1]` landing at `k` pitches.
  The board layer is untouched: cycling is the painter's view of `seq`.
- Local progress `u = s / stop`, clamped to `[0, 1]`; total displacement
  `D = k · pitch`.

Displacement `d(u)` in real rows uses a **trapezoid** speed profile:
ease-in over `u ∈ [0, U_IN]` (`U_IN = 0.15`), cruise to
`CRUISE_END = 0.45`, ease-out over `u ∈ [0.45, 0.9]` (so the last couple
of symbols are the slow ones), then **settle** over `u ∈ [SETTLE_START,
1]` with `SETTLE_START = 0.9`: `d = D + B · sin(π · v)`, `v` the settle
fraction —
overshoot by `B` rows past the landing and return.
`B = min(gap, max(1, round(pitch / 8)))` real rows (one row on a
smallsign, about one logical row on the bigsign). **Nothing peeks in
above the dipped glyph** (Claude's call from the builder check): the
strip has no symbol past the incoming one, so the top `B` rows of the
window show the panel background while the glyph sinks, its bottom `B`
rows clipped by the window, then it rises home. The cap `B ≤ gap` keeps
that true even if a later change puts a symbol after the incoming one. Ease-in means speed is zero on the first frame, which is what
keeps the first frame's shade at 1.0 without a ramp hack (see Shading).

**Pace at the floor.** The displacement per frame is what decides
whether this reads as reels or as strobe; it is a function of `pitch`,
`k` and the frame budget, not of any knob directly. Worked at the
default 20 fps, `spins = 3`, `stagger = 0.5`, first reel (`k = 4`):

| | pitch (real rows) | frames for the whole pre-snap run | cruise speed |
| --- | --- | --- | --- |
| bigsign, `min_frames = 36` | ≈ 35 | ≈ 31 (× 0.5 for the first reel ≈ 15) | ≈ 13 rows/frame ≈ 3.3 logical rows — over a third of a symbol per frame; strobes |
| bigsign, `min_frames = 60` (3 s) | ≈ 35 | ≈ 51 (× 0.5 ≈ 26) | ≈ 8 rows/frame ≈ 2 logical rows; readable |
| smallsign, 60 | ≈ 9 | ≈ 26 | ≈ 2 rows/frame; readable |

So slots sets **`min_frames = 60`** at the default knobs (unlike
splitflap's 36) and caps **`spins` at 6**: at the cap the first reel
shows 7 symbols in 26 frames (≈ 3.7 frames each), already the edge of
readable. The builder re-derives these at the visual gate; the table is
the reasoning to check, not a promise.

**Resolution (2026-11-24): the floor is per instance.** Cruise speed
scales with `(spins + 1) / (1 − stagger)` (`stagger` multiplies every
reel's symbol count through `reel_advances`), so a fixed 60 lets the
knobs strobe. Each instance sets
`min_frames = pace_floor(spins, stagger) = max(60, ceil(60 · (spins+1)/4 ·
0.5/(1 − stagger)))`, so the reels never spin faster than at the default
knobs over 60 frames. The runner lifts a shorter `duration` to it:

| `spins` | `stagger` | frames | seconds |
| --- | --- | --- | --- |
| 3 | 0.5 | 60 | 3 |
| 0 | 0.5 | 60 | 3 |
| 0 | 0.9 | 75 | 3.75 |
| 6 | 0.5 | 105 | 5.25 |
| 3 | 0.8 | 150 | 7.5 |
| 3 | 0.9 | 300 | 15 |
| 6 | 0.9 | 525 | 26 |

Chosen over documenting a duration rule or decoupling `k` from
`stagger`. `.alternating` inherits it through `Cycling`.

**Static** reels paint `seq[0]` every frame. `u ≥ 1` paints `seq[-1]`.
A non-static reel always has `k ≥ 1`, so `spins = 0` is "one turn" (old
scrolls out, new scrolls in, settle), not a cut.

### Reel window

A reel is a **window** that glides, by travel progress `g = glide(u)`
(the fraction of the strip travel covered, 1 from `SETTLE_START` on),
from the outgoing glyph's column `(x0, w0)` to the incoming glyph's
`(x1, w1)`: the centre and the width interpolate linearly (`reel_window`),
rounded so `g = 0` gives exactly `(x0, w0)` and `g = 1` exactly
`(x1, w1)`. Every strip symbol is painted **centred in the window and
clipped to its columns** (and, as before, to the band's rows and the
panel). A blank end takes the other end's column.

Why (bigsign observation, 2026-11-25): the board gives the outgoing
cell its own slot but centres the in-betweens and the incoming cell on
the incoming column, with borrowed in-betweens up to 1.5x the wider
end. For splitflap's quick flips that is fine; for a continuously
visible reel it read as two letters side by side and as borrowed glyphs
spilling over the neighbouring reels. The board is untouched; the fix is
slots-only. Frame 0 (window = the outgoing cell's own column) and the
landing (window = the incoming cell's) stay pixel-exact with
`paint_cell`.

### Shading

The moving strip is darkened in proportion to speed so motion reads as
spin, not as a glitch: shade `= 1 − (1 − SPIN_SHADE) · speed_norm`, where
`speed_norm = |d′(u)| / cruise speed`. With the trapezoid profile this is
0 on the first frame (plain glyph), 1 during the cruise (dimmest),
falling back to 0 through the ease-out, and 0 across the settle, so the
first and last frames are the plain glyph and brightness never jumps
between frames (anti-goal). `SPIN_SHADE ≈ 0.6`, tuned at the visual gate.
Static reels are never dimmed.

### Rings

Outgoing ring + `under_out` before `s = 0.5`, incoming after — the same
`first_half` switch as splitflap, painted after the reels.

### Knobs and validation

- `spins`: int in `[0, 6]`, default `3` (cap reasoned under "Pace at
  the floor"; splitflap keeps 12). bool rejected. Error text
  `spins must be an int in [0, 6]; got …`.
- `stagger`: float in `[0.0, 0.9]`, default `0.5`, same coercer as
  splitflap.
- `min_frames`: class base `60` (overrides the base's 36), raised per
  instance by `pace_floor(spins, stagger)` (see "Pace at the floor").
  README documents the minimum-duration rule and table.

### Registration and surfaces

- `flair/__init__.py`: `api.transition("slots.forward")(Slots)`, `.reverse`,
  `.alternating` (`Cycling([Slots, SlotsReverse])`), `.random`
  (`SlotsRandom`, settle-order random, same shape as `SplitFlapRandom`).
- `flair/__init__.py` module docstring, `CLAUDE.md` head paragraph and
  namespace bullet, and a new `## flair.slots transition invariants`
  section (board reuse, window clipping, timeline, shade, tripwires).
- README: a `## Slot-machine transition` section after split-flap, same
  shape (intro, core floor, variants table, config, knobs table, notes:
  backgrounds / cross-scale / letterbox). pyproject `description` gains
  "slots".
- Core docs site (separate repo, separate PR, after the plugin release):
  a `### flair.slots` entry on `transitions/sprite.mdx` (after
  `flair.splitflap`, with a pinned demo GIF), the one-line catalogue on
  `transitions/index.mdx`, the page `description` on `sprite.mdx`, and
  the family list on `plugins/available.mdx`.
- Smoke configs: `examples/config.slots-smoke.bigsign.toml` and
  `.smallsign.toml`, cloned from the splitflap ones with the type swapped
  and a `spins = 0` / `stagger` knob section.

## Edge cases

- Empty outgoing (boot / wake): every reel spins in from blank.
- Both empty: nothing paints until the snap.
- Identical messages: every reel `static`; a hold, then the snap.
- Letterboxed sections: windows come from lit rows only, so letterbox
  bands stay bg; a border in the letterbox is the ring, held static.
- Image / gif / background-effect content arrives as strips from the
  board; each strip is a reel. A full-panel picture becomes a row of
  narrow reels spinning the picture's own strips — the same "graceful,
  recognisable" bar as splitflap, judged at the visual gate.
- Two_row ↔ single-row: the padded empty band's reels spin to / from
  blank in place (board behaviour, unchanged).
- Refire rule for `.alternating` / `.random`: `t == 0 or t < last_t`.

## Tests

- `tests/test_flair_board_transition.py` (PR 1): the subclass / no-own-
  `frame_at` tripwire; `flap_start` and coercer tests move here from the
  splitflap transition tests only if they were testing base behaviour
  (builder's call; existing splitflap tests must stay green either way).
- `tests/test_flair_slots_paint.py`: window clipping (no write outside
  `[lo, hi]` or the panel), strip geometry at `d = 0` and `d = D`
  (outgoing / incoming glyph pixel-exact in place), a mid-travel frame
  shows parts of two adjacent glyphs separated by a dark gap, shade is
  1.0 at `d = 0` and at landing and `< 1` mid-travel.
- `tests/test_flair_slots_transition.py`, mirroring the splitflap one:
  all landed before the snap; forward settles left first / reverse right
  first; random order differs between firings with a seeded RNG;
  alternating cycles; `spins` / `stagger` validation; the overshoot frame
  really dips (incoming glyph's rows shifted down by `B` at the settle
  midpoint); all reels start moving on the first frame after `s = 0`
  and the first-ranked reel is the first to land; a long-spinning reel
  cycles its in-betweens; shade is 1.0 on the first and last frames and
  never jumps by more than the per-frame cruise ramp; `TestRealCoreWidgets` against real `message` / `two_row` /
  `image` widgets through a `ScaledCanvas`.
- Registry test: the four `flair.slots.*` names resolve through
  `flair.register(api)` (same shape as `test_registration_four_types`;
  `tests/test_smoke.py` pins only the sprite families, so it is
  untouched).

## Visual gate (before PR 2 is opened)

Render bigsign and smallsign GIFs of the smoke config covering text→text
(different lengths), two_row, gif in and out, bordered message,
bg-coloured sections, letterbox, each variant, `spins = 0`, and a
`stagger = 0.8` section. Tune `gap`, `B`, `SPIN_SHADE`, `U_T` there.
James decides on the smallsign and on whether the default `stagger`
should be higher than 0.5 to exaggerate the left-to-right stop.

## Left to the builder

- Module layout (expect `_board_transition.py`, `slots.py`,
  `slots_paint.py`), whether `BoardTransition` stores `steps` or the
  subclass passes it, exact constants, test fixture duplication (this
  repo's per-file convention).
