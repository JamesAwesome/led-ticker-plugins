# Antagonistic review ledger — flair.slots (PR #154, stacked on #153)

Branch `feat/flair-slots`, base `5069766585181abd99ad36c850b25e8df49da62b` (origin/main). Protocol: fresh adversarial
reviewer per cycle (mechanism-first: state → trigger → observable failure; no padding),
lens rotated per cycle, one fix subagent per cycle, then the next cycle. Cap 5 cycles.
Exit: a cycle with no HIGH/MEDIUM in-scope findings — remaining LOW/DOCS are folded in.
Pre-existing issues outside the branch diff do not count; they are filed as issues.

| cycle | head | lens | HIGH | MED | LOW/DOCS | outcome |
|---|---|---|---|---|---|---|
| 1 | 4051259 | BoardTransition seams, engine integration, window geometry, validate surface | 0 | 2 | 6 | fix wave dispatched |

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
