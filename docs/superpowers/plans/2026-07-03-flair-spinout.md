# flair.spinout Implementation Plan (core export + flair transition)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the `flair.spinout` transition — the outgoing widget's content propeller-spins (accelerating, ease-in cubic) then cuts to the incoming — as the first consumer of the RotationSurface transition-reuse seam.

**Spec:** `docs/superpowers/specs/2026-07-03-flair-spinout-transition-design.md` (antagonist-reviewed; governs). Two sequential parts across two repos with a core release between.

**Contract corrections vs the spec's sketch (verified against effects.py:Cut):** `frame_at` RETURNS the canvas (`return canvas` on every path), and the cut draw is `incoming.draw(canvas, cursor_pos=0)`.

## Global Constraints

- Worktrees + PRs, never main. No `from __future__ import annotations`; "sanity"/"sane" banned; PEP-758 except style; `Any` for duck-typed params.
- Antagonist lens on every task review; gif validation + visual review before the flair PR.
- Monorepo co-dev: `uv run --no-sync` everywhere; `uv pip install --no-deps -e plugins/flair`; editable core from the sibling checkout.
- `Spinout.scale_switch_at = 1.0` is LOAD-BEARING (antagonist finding 1 — bg + cross-scale). Do not drop it as an "unused attribute".

---

## PART A — core repo (→ v4.6.0)

### Task A1: export `make_rotation_surface` + `RotationSurface`

**Files:** Modify `src/led_ticker/plugin.py`; `docs/site/src/content/docs/plugins/api-reference.mdx` (guarded exported-names region + one prose sentence for transition authors); Test: extend `tests/test_animations_rotation.py` (it holds the ENGINE_TICK_MS export test — the sibling pattern).

**Steps:**
1. Failing test:
```python
def test_rotation_surface_on_plugin_surface() -> None:
    """flair.spinout imports the seam through the public surface only."""
    from led_ticker import plugin, rotate

    assert plugin.make_rotation_surface is rotate.make_rotation_surface
    assert plugin.RotationSurface is rotate.RotationSurface
    assert "make_rotation_surface" in plugin.__all__
    assert "RotationSurface" in plugin.__all__
```
2. Run → FAIL (AttributeError). Implement: `from led_ticker.rotate import RotationSurface, make_rotation_surface` in plugin.py's import block (alphabetical) + both names in `__all__`. Run the drift guard — it WILL fail on the new names; add both to the api-reference guarded region (match format), plus one prose sentence in the rotation section: transitions construct a surface once, snapshot the outgoing, blit per frame (cite the construct-once + `t < _last_t` pattern).
3. Gates: new test + `tests/test_docs_plugin_api_drift.py` + `make docs-format && make docs-lint`; ruff/format/pyright; full `make test`.
4. Commit `feat(plugin): export the rotation seam for transition authors`; PR (body: one-paragraph, cites the spec, notes flair.spinout as the consumer); merge on green per the session's flow; then cut **v4.6.0** (release notes: "rotation seam public for transition authors — first consumer: flair.spinout, shipping in flair v0.3.0") and PyPI-publish via the gate.

## PART B — plugins monorepo (→ flair v0.3.0)

### Task B1: the `Spinout` transition + tests

**Files:** Create `plugins/flair/src/led_ticker_flair/flair/spinout.py`; modify `flair/__init__.py` (register; guard message → ">= 4.6"); `plugins/flair/pyproject.toml` (dep floor `led-ticker-core>=4.6`); Test: `plugins/flair/tests/test_flair_spinout.py`.

**Implementation (spec §2 with the contract corrections):**

```python
"""flair.spinout — the outgoing widget propeller-spins out, then cuts."""

from typing import Any

from led_ticker.plugin import Canvas, make_rotation_surface

_DIRECTIONS = ("cw", "ccw")


class Spinout:
    # LOAD-BEARING (spec finding 1): outgoing bg holds for the whole spin
    # and the cross-scale re-wrap defers to the cut frame. Precedent:
    # SplitHorizontal / Scroll / Push*.
    scale_switch_at = 1.0

    def __init__(self, revolutions: int = 2, direction: str = "cw") -> None:
        bad_rev = not isinstance(revolutions, int) or isinstance(revolutions, bool)
        if bad_rev or revolutions < 1:
            raise ValueError(f"revolutions must be an int >= 1; got {revolutions!r}")
        if direction not in _DIRECTIONS:
            raise ValueError(f"direction must be one of {_DIRECTIONS}; got {direction!r}")
        self.revolutions = revolutions
        self.direction = direction
        self._surface: Any = None
        self._last_t = 1.0  # re-fire detection (PushRandom precedent)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas
        if self._surface is None or not self._surface.matches(canvas):
            self._surface = make_rotation_surface(canvas)
        if t < self._last_t:
            self._surface.invalidate()  # new firing -> fresh snapshot
        self._last_t = t
        if not self._surface.has_snapshot:
            self._surface.clear()
            outgoing.draw(
                self._surface.target,
                cursor_pos=kwargs.get("outgoing_scroll_pos", 0),
            )
            self._surface.snapshot()
        angle = 360.0 * self.revolutions * (t**3)  # ease-in cubic (accelerate out)
        if self.direction == "ccw":
            angle = -angle % 360.0
        self._surface.blit(canvas, angle, canvas.width / 2)
        return canvas
```

Registration in `flair/__init__.py` — the guard changes its PROBE, not
just its message (antagonist plan finding 1, HIGH): `_import_seam()` must
import `make_rotation_surface` (the actual 4.6 symbol) — probing
`ENGINE_TICK_MS` (a 4.3 symbol) while claiming ">= 4.6" is a no-op guard
that lets a 4.3-4.5 core through to a raw ImportError inside registration.
Since `register()` registers propeller AND spinout together and the
pyproject floor is >= 4.6 anyway, failing the whole register() on < 4.6
is consistent — state so in the guard docstring. Message: "requires
led-ticker-core >= 4.6 (the RotationSurface transition seam); update the
core image, not the flair plugin." Then
`from led_ticker_flair.flair.spinout import Spinout  # noqa: PLC0415` and
`api.transition("spinout")(Spinout)` alongside the propeller registration.

IN LOCKSTEP (finding 2, HIGH): update the EXISTING
`test_register_guard_message_when_seam_missing` in
test_flair_propeller.py — its stub module must withhold
`make_rotation_surface` (it currently withholds ENGINE_TICK_MS) and its
regex becomes `>= 4\.6`.

RESOLVED (antagonist finding 3): `_build_plugin_style` passes ONLY the
config `extra` dict and validates keys against `inspect.signature(cls)` —
so the explicit two-param `__init__` gets rule-53 unknown-kwarg rejection
FOR FREE. Do NOT add `**kwargs` to `__init__` (it would silently swallow
config typos like `revolution=3`); `**kwargs` stays only on `frame_at`
(the runner passes outgoing_scroll_pos/duration_ms/bg kwargs there).

**Tests (all real assertions; follow flair's existing test conventions; `_RecordingAPI` + stub widgets per the file precedents):**
- Registration: `flair.spinout` registered; guard message matches `>= 4\.6`.
- Ctor validation (revolutions bool/0/-1; direction "sideways").
- `scale_switch_at == 1.0` class attribute pin (finding 1 — a deleted attribute must fail a test, not just a review).
- Envelope: pre-mod monotonic `360·revs·t³`; t=0 → angle 0; ccw mirror.
- Snapshot-once: N frame_at calls, t ascending FROM 0.0 (matching the
  runner — ease_fn(0) == 0.0 for every registered easing, antagonist
  finding 4) → outgoing.draw called once, blit N times;
  `outgoing_scroll_pos` forwarded as cursor_pos (spy; negative value —
  the scrolled-out sign semantics per push.py precedent).
- t ≥ 1.0 → `incoming.draw(canvas, cursor_pos=0)` called, blit NOT, returns canvas.
- Re-fire pin: full sweep then new t=0 → re-snapshot (draw count 2).
- Cross-scale tripwire: a full firing on a scale-4 wrapper snapshots
  ONCE and the t=1.0 frame draws the incoming on whatever canvas is
  passed (the runner re-wraps only at scale_switch_at=1.0, so the
  surface sees a stable canvas all spin).
- Scale-1 AND scaled stub canvases both blit (block-partiality
  granularity smoke on the scaled one — the established assertion).
- bg-correctness note (deliberate omission, not a gap): the outgoing-bg-
  for-all-t<1 behavior lives in run_transition's reset (keyed off
  scale_switch_at), NOT in frame_at — a frame_at-level unit test cannot
  reach it. The `scale_switch_at == 1.0` attribute pin is the unit-level
  proxy; the different-bg gif in B2 is the behavioral verification.
- Compound-rotation edge non-crash: outgoing whose draw() itself uses a rotation surface (or simply a stub raising nothing while drawing rotated content) — a full sweep completes without exception.
- Every frame_at path returns the canvas.

Gates: `uv run --no-sync pytest plugins/flair -q` green; ruff; the env note (editable core from the sibling checkout must carry the A1 export — `uv pip install -e ../led-ticker` refresh + `--no-sync` everywhere).

### Task B2: README + gif validation

- README: spinout section in the flair README (config snippets incl. the dict form, knobs table, "outgoing bg holds through the spin", the compound-rotation edge note, core >= 4.6); CLAUDE.md invariant line (the flair namespace = text-effects: one animation + one transition).
- Gif matrix (visual-validation checklist, rendered through the real loader with editable core+flair): spinout after a HELD message; after a SCROLLED long message (scroll-pos continuity); different bg colors on the two sections (the finding-1 pin, visually); propeller-in + spinout-out composition; ccw; hires font outgoing on bigsign geometry; smallsign regression. Frame checks: zero fully-black frames; outgoing bg present on ALL t<1 frames; the cut lands the incoming cleanly; visual review agent on the results.

### Task B3: full verification + PR + release

- Full monorepo flair suite; PR (body: spec link, the finding-1 bg fix, gifs); merge on green per session flow; cut **flair-v0.3.0** (notes: spinout + requires core >= 4.6).
