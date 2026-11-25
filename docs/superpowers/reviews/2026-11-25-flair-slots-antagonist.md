# Antagonistic review ledger — flair.slots (PR #154, stacked on #153)

Branch `feat/flair-slots`, base `5069766585181abd99ad36c850b25e8df49da62b` (origin/main). Protocol: fresh adversarial
reviewer per cycle (mechanism-first: state → trigger → observable failure; no padding),
lens rotated per cycle, one fix subagent per cycle, then the next cycle. Cap 5 cycles.
Exit: a cycle with no HIGH/MEDIUM in-scope findings — remaining LOW/DOCS are folded in.
Pre-existing issues outside the branch diff do not count; they are filed as issues.

| cycle | head | lens | HIGH | MED | LOW/DOCS | outcome |
|---|---|---|---|---|---|---|
| 1 | 4051259 | BoardTransition seams, engine integration, window geometry, validate surface | 0 | 2 | 6 | fixed in 6d8200c (all 7 in-scope items) |

## Cycle 1 (reviewer: opus) — findings and dispositions
1. MED — section `easing` makes `t` non-linear in the frame index; `pace_floor` assumes linear, so `ease_out` brings back ~0.5 symbols/frame at the floor. **Disposition:** document (README/spec/CLAUDE.md: slots assumes `easing = "linear"`, the default); core follow-up idea: pass linear frame progress to `frame_at` (API minor). A transition cannot see the easing today.
2. MED — integer `k` makes per-reel cruise speed vary (up to (spins+2)/(spins+1.5)× nominal: 1.33× at spins = 0); the pace tripwire checked only the first reel. **Ruling:** keep continuous stop times (quantising stops to symbol boundaries — the reviewer's suggestion — can push the last stop past 1.0 and groups reels for low `spins`, losing "stop in sequence"); instead fold the rounding bound into `pace_floor` so the WORST reel at any knob combination is no faster than the worst reel of the defaults at 60 frames, and sweep every stop position in the tripwire. Spec wording "same speed" → "same nominal speed, within one whole symbol of rounding".
3. DOCS — slots README blocks landed inside the Split-flap section. Fix: move.
4. LOW — gliding symbol can step 1 px backwards (window left/width rounded separately). Fix: place symbols from the unrounded centre, keep the rounded window for clipping.
5. LOW/DOCS — README "never spill over the neighbouring reels" overstates; soften to "at rest … and never outside its own window".
6. LOW — `strip_symbols` can show the same in-between twice running at the cycle wrap. Fix: skip a repeat when the pool has ≥ 2 in-betweens.
7. LOW — `reel_stop` is tested but unused since `_schedule` delegates to the base. Fix: delete it; port its test to the schedule.
8. DOCS — core docs-site pages: already listed as a follow-up in the PR body (after the flair release).
Pre-existing (out of scope, to file as core issues after the loop): refire rule with an easing that is non-zero at 0 (unreachable today); `validate` is silent when `min_frames` lifts a configured `duration`.
Checks the reviewer ran: 157 focused tests; splitflap byte-equivalence base vs branch 0/11,808 frames differ; real `run_transition` refires, cross-scale, letterbox, breaker, `random` pool floors; validate on bad knobs.
| 2 | 6d8200c | mutation testing of tripwires, painter/motion math, least-examined surfaces, perf at the 504-frame floor | 0 | 4 | 3 | fixed in a277568 (all items) |

## Cycle 2 (reviewer: opus) — findings and dispositions
24 mutations run against a scratch copy; 4 survived the whole flair suite:
1. MED — unrounded glide centre (cycle-1 fix 4) has no paint-path tripwire. Fix: `test_paint_reel_glide_never_steps_backwards` (drive `paint_reel` over `reel_window(*geo, i/400)`, painted min-x monotone).
2. MED — no-repeat in-between skip's tripwire uses a 2-glyph pool that never repeats. Fix: fixture `(a, x, y, x, b)`, k = 8, assert no adjacent equal keys; CLAUDE.md tripwire name updated.
3. MED — ring/under switch at s = 0.5 and frame-0 exactness WITH a border are unpinned. Fix: outgoing ring BLUE / incoming RED; frame 0 == outgoing draw; (0,0) BLUE at s = 0.3, RED at s = 0.7.
4. MED — static-cell test compares to the transition's own frame 0, so a constant dim survives. Fix: compare static columns to the widget's own pixels at several t.
5. LOW — shade pops (0.26 in one frame) for `spins = 0` with high `stagger`: the first reel lives only ~10 frames at the floor. **Ruling:** document ("low `spins` with high `stagger` gives a brisk first reel; its dim is a blink") and parametrize the ramp test with the bound each combo meets; NOT raising the floor again for the shortest reel's life — it would make `(0, 0.9)` 234 frames for a cosmetic blink on a one-symbol reel. Cost if wrong: a visible blink at an edge knob combination.
6. LOW — window clip edges can step 1 px backwards (left/width rounded separately). Fix: `l = round(cx - wf/2)`, `r = round(cx + wf/2)`, return `(l, r - l, cx)`; endpoints stay exact; add `test_window_edges_monotone`.
7. DOCS — spec test list names an `image` widget that no test uses; `_board_transition.py` docstring "supply only `_paint`" vs `Slots` also overriding `__init__`/`min_frames`; TestPerf docstring says "longboi" for 512 wide (longboi is 128×64).
Pre-existing: no flair transition implements `end_firing` (board held until the next firing; bounded); splitflap's own ring switch is likely unpinned the same way.
Checks: `_integral` vs numeric 1e-6; visit bound 3000 random strips 0 mismatches; pace at bucket edges ≤ defaults' worst; perf 504 frames at 512×64 ≤ 6.5 ms/frame; validate clean; registration/Cycling/README table consistent.
Fix-wave notes (cycle 2): tripwires 2, 3, 4 confirmed RED under their mutations. Tripwire 1: after the monotone-edge fix (item 6) the end-to-end glide test no longer distinguishes rounded-window placement (both are monotone), so the biting tripwire is `test_paint_reel_places_symbols_from_the_unrounded_centre` (RED `198 == 8`); the end-to-end test bites on a reverted `reel_window`. Ruling: accepted — the invariant is pinned at the unit level and the user-visible property at the paint level. In the ring mutation the frame-0 assertion trips first; the 0.3/0.7 checks are belt-and-braces. Ruling: accepted.
| 3 | a277568 | sign-owner view: smallsign render, content types, docs vs behaviour, maintainer traps | 0 | 2 | 6 | fix wave dispatched |

## Cycle 3 (reviewer: opus) — findings and dispositions
1. MED (docs, but with a behaviour root) — "one turn per reel" at `spins = 0` is false: the board builds no in-betweens at `flips = 0`, so later reels (k = 2..5 at `stagger = 0.8`) alternate OLD/blank — a stutter. **Ruling:** slots asks the board for `max(spins, 2)` in-betweens regardless of `spins` (the pool it cycles), while `spins` keeps its meaning (advances of the first reel); README/spec/smoke wording: "`spins = 0`: the first reel makes one turn; later reels keep spinning through borrowed characters until their stop". Cost if wrong: a `spins = 0` firing shows in-betweens on later reels instead of the old glyph flashing.
2. MED (docs) — README minimum-duration formula omits the 3 s floor. Fix: `max(3, …)`.
3. LOW — smallsign settle dip clips the glyph's bottom row for 1–2 frames (E reads as F). **Ruling:** leave; the spec designs the dip as clipped rows and the gate accepted it; note in README smallsign bullet.
4. LOW/DOCS — "7 or 8 LEDs tall" → "7 to 9" (descenders).
5. LOW/DOCS — smoke label "worst documented combination" → "worst combination recommended for section-to-section".
6. LOW (maintainer) — `_paint` skeleton duplicated between slots and splitflap; `min_frames = 36` lives in the base. **Ruling:** move `min_frames = 36` onto `SplitFlap` (base defaults to core's 0); do NOT hoist the skeleton now — it touches splitflap's byte-equivalent path for no user-visible gain; recorded as a follow-up.
7. LOW/DOCS — garbled parentheticals in the CLAUDE.md Reel window bullet.
8. LOW — unexplained `# type: ignore[arg-type]` in a paint test.
Content types checked clean: emoji, rainbow (pool ≈ 20 cells), border, "1111"→"2222", identical, one-char, wider-than-panel, two_row long bottom, bg one side. Smallsign render: reads as a spin (2–3 rows/frame, in-betweens readable ~3 frames, B = 1 dip visible).
