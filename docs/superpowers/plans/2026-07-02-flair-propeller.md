# Flair Propeller Animation Implementation Plan (PR 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.propeller` — the spin-in-then-rest whole-text rotation animation — as the flair wheel's fifth namespace, consuming the core rotation seam merged in led-ticker#345.

**Architecture:** One new family module `src/led_ticker_flair/flair/` (register + `Propeller`). The class emits `AnimationFrame(visible_text=full_text, rotation=angle)` per frame with an ease-out-cubic envelope, declares `emits_rotation = True` (core validate rule 63 reads it) and `frames_to_rest` (composes with the defer-to-rest settle). `register()` guards the seam import with an actionable version error.

**Tech Stack:** Python 3.14, uv workspace, pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-07-02-flair-spin-animation-design.md` in the **led-ticker core repo** (on main; §8–§9 are this PR's scope). The Propeller math was already gif-validated end-to-end against the merged seam via a stub.

## Global Constraints

- Work on a feature branch of the **led-ticker-plugins** monorepo ONLY (`git branch --show-current` first; abort if `main`).
- Plugin imports come ONLY from `led_ticker.plugin` (`tests/test_import_purity.py` auto-covers the new module via rglob).
- No `from __future__ import annotations`. Avoid "sanity"/"sane" and gun metaphors in all text.
- **Release gate:** CI resolves `led-ticker-core` from PyPI; the seam ships in core **v4.3** (not yet released at plan time). Local dev/tests use the co-dev path: after `uv sync`, run `uv pip install -e ../led-ticker` (sibling checkout, which has the seam on main). The PR merges only after core v4.3 is on PyPI.
- Lint/typecheck from the monorepo ROOT: `make lint` (or `uv run ruff check plugins/flair` + `uv run ruff format plugins/flair`); tests: `uv run pytest plugins/flair -q`.
- Exact math values come from the spec §9 verbatim — do not re-derive.

---

### Task 1: package skeleton — entry point, guarded register, dep floor

**Files:**
- Modify: `plugins/flair/pyproject.toml` (entry points; `dependencies`)
- Create: `plugins/flair/src/led_ticker_flair/flair/__init__.py`
- Create: `plugins/flair/src/led_ticker_flair/flair/propeller.py` (minimal stub this task; full class in Task 2)
- Test: `plugins/flair/tests/test_flair_propeller.py` (create; registration + guard tests this task)

**Interfaces:**
- Produces: entry point `flair = "led_ticker_flair.flair:register"`; `register(api)` that (a) fails with an actionable version message when the core seam is missing, (b) otherwise registers `api.animation("propeller")(Propeller)`. Task 2 fills in `Propeller`.

- [ ] **Step 1: Write the failing tests**

Create `plugins/flair/tests/test_flair_propeller.py`:

```python
"""flair.propeller — registration, seam guard, and Propeller math."""

import pytest

from led_ticker_flair import flair as flair_pkg


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording animation registrations
    (mirror the pattern in test_packaging.py / other family tests —
    check those files and reuse their helper if one exists)."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}

    def animation(self, style: str):
        def deco(cls):
            self.animations[style] = cls
            return cls

        return deco


def test_register_registers_propeller() -> None:
    api = _RecordingAPI()
    flair_pkg.register(api)
    assert "propeller" in api.animations


def test_register_guard_message_when_seam_missing(monkeypatch) -> None:
    """Version-skew error quality (spec §9): a core without the seam must
    produce an actionable 'update core' message, not a bare ImportError."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "led_ticker.plugin":
            mod = real_import(name, *args, **kwargs)
            # simulate a pre-seam core: hide ENGINE_TICK_MS
            if args and args[2] and "ENGINE_TICK_MS" in (args[2] or ()):
                raise ImportError("cannot import name 'ENGINE_TICK_MS'")
            return mod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"led-ticker-core >= 4\.3"):
        flair_pkg.register(_RecordingAPI())
```

NOTE for the implementer: the monkeypatch shape above is a sketch — the
robust pattern is to make `register()`'s guarded import mockable and
assert on the raised message. If patching `builtins.__import__` proves
brittle, an equally valid test is: monkeypatch
`led_ticker_flair.flair._import_seam` (extract the guarded import into a
module-level helper precisely so the test can patch it) to raise
ImportError, then assert the re-raise message matches
`led-ticker-core >= 4.3`. Choose the helper approach if in doubt — it is
deterministic. The assertion targets must not weaken: a registration
test and a guard-message test.

- [ ] **Step 2: Verify environment + failing tests**

First the co-dev install (the venv's PyPI core lacks the seam):

```bash
uv sync && uv pip install -e ../led-ticker
uv run python -c "from led_ticker.plugin import ENGINE_TICK_MS; print('seam OK')"
```

Expected: `seam OK`. Then run: `uv run pytest plugins/flair/tests/test_flair_propeller.py -v`
Expected: FAIL — `ImportError: cannot import name 'flair' from 'led_ticker_flair'`.

- [ ] **Step 3: Implement the package + guard**

`plugins/flair/src/led_ticker_flair/flair/__init__.py`:

```python
"""led-ticker-flair / flair: the wheel's own namespace — text animations.

The entry-point name ``flair`` is the plugin namespace, so animations are
referenced in config.toml as ``animation = "flair.propeller"``.

Unlike the four sprite families, this namespace is named after the wheel
itself (documented exception to the namespace-per-sprite-family pattern).
"""


def _import_seam():
    """Import the core rotation seam; raise an actionable error when the
    installed core predates it (version-skew guard, spec §9)."""
    try:
        from led_ticker.plugin import ENGINE_TICK_MS  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair.propeller requires led-ticker-core >= 4.3 (the "
            "AnimationFrame.rotation seam and the ENGINE_TICK_MS export). "
            "Update the core image, not the flair plugin."
        ) from exc


def register(api):
    _import_seam()
    from led_ticker_flair.flair.propeller import Propeller  # noqa: PLC0415

    api.animation("propeller")(Propeller)
```

`plugins/flair/src/led_ticker_flair/flair/propeller.py` (Task-1 stub — Task 2 replaces the body):

```python
"""flair.propeller — spin-in-then-rest whole-text rotation."""

from led_ticker.plugin import ENGINE_TICK_MS, AnimationFrame


class Propeller:
    """Placeholder — implemented in the next commit."""

    restart_on_visit = True
    emits_rotation = True
```

`plugins/flair/pyproject.toml`: add the fifth entry point (aligned with the existing four):

```toml
flair       = "led_ticker_flair.flair:register"
```

and bump the dependency floor:

```toml
dependencies = [
    "led-ticker-core>=4.3",
]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest plugins/flair/tests/test_flair_propeller.py plugins/flair/tests/test_import_purity.py plugins/flair/tests/test_packaging.py -q`
Expected: the two new tests pass; import purity auto-covers the new module. If `test_packaging.py` asserts an exact entry-point set, update it to include `flair` (read the file first).

- [ ] **Step 5: Lint, commit**

```bash
uv run ruff check plugins/flair && uv run ruff format plugins/flair
git add plugins/flair/pyproject.toml plugins/flair/src/led_ticker_flair/flair/ plugins/flair/tests/test_flair_propeller.py
# plus tests/test_packaging.py if updated
git commit -m "feat(flair): fifth namespace + guarded register for flair.propeller

Entry point 'flair' (the wheel's own name — documented exception to the
sprite-family pattern). register() wraps the core-seam import so a
pre-4.3 core produces an actionable 'update core' error instead of a
bare plugin-load failure. Dep floor -> led-ticker-core>=4.3."
```

---

### Task 2: the `Propeller` class

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/propeller.py` (replace the stub body)
- Test: `plugins/flair/tests/test_flair_propeller.py` (extend)

**Interfaces:**
- Consumes: `ENGINE_TICK_MS`, `AnimationFrame` from `led_ticker.plugin`.
- Produces: `Propeller(revolutions=2, spin_seconds=1.0, direction="cw")` with `frame_for`, `frames_to_rest`, `restart_on_visit = True`, `emits_rotation = True`. TOML dict-form kwargs reach the constructor via core's `_coerce_animation`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/flair/tests/test_flair_propeller.py`:

```python
import math

from led_ticker.plugin import ENGINE_TICK_MS

from led_ticker_flair.flair.propeller import Propeller


class TestPropellerEnvelope:
    def test_frame_zero_is_flat(self) -> None:
        p = Propeller()
        assert p.frame_for(0, "HELLO", 160, 40).rotation == 0.0

    def test_pre_mod_angle_strictly_increasing(self) -> None:
        """Engineer round-1 finding 4: monotonicity holds PRE-modulo (the
        post-mod angle legitimately wraps down once per revolution)."""
        p = Propeller(revolutions=2, spin_seconds=1.0)
        prev = -1.0
        for frame in range(0, p.total_frames + 1):
            t = min(1.0, frame / p.total_frames)
            eased = 1.0 - (1.0 - t) ** 3
            pre_mod = 360.0 * p.revolutions * eased
            assert pre_mod > prev or frame == 0
            prev = pre_mod

    def test_lands_exactly_flat_and_stays(self) -> None:
        p = Propeller(revolutions=2, spin_seconds=1.0)
        for frame in (p.total_frames, p.total_frames + 1, p.total_frames + 500):
            assert p.frame_for(frame, "HELLO", 160, 40).rotation == 0.0

    def test_visible_text_always_full(self) -> None:
        p = Propeller()
        for frame in (0, 3, p.total_frames // 2, p.total_frames + 9):
            assert p.frame_for(frame, "FULL TEXT", 160, 60).visible_text == "FULL TEXT"

    def test_ccw_mirrors_angles(self) -> None:
        cw = Propeller(direction="cw")
        ccw = Propeller(direction="ccw")
        mid = cw.total_frames // 3
        a_cw = cw.frame_for(mid, "HI", 160, 12).rotation
        a_ccw = ccw.frame_for(mid, "HI", 160, 12).rotation
        assert a_cw != 0.0  # mid-spin really is rotated
        assert a_ccw == pytest.approx((-a_cw) % 360.0)

    def test_ccw_lands_exactly_flat(self) -> None:
        p = Propeller(direction="ccw")
        assert p.frame_for(p.total_frames, "HI", 160, 12).rotation == 0.0

    def test_total_frames_from_spin_seconds(self) -> None:
        p = Propeller(spin_seconds=1.5)
        assert p.total_frames == max(1, int(1.5 * 1000) // ENGINE_TICK_MS)  # 30


class TestPropellerRest:
    def test_frames_to_rest_counts_down(self) -> None:
        p = Propeller(spin_seconds=1.0)
        assert p.frames_to_rest(0, 10) == p.total_frames
        assert p.frames_to_rest(p.total_frames - 3, 10) == 3
        assert p.frames_to_rest(p.total_frames, 10) == 0
        assert p.frames_to_rest(p.total_frames + 100, 10) == 0


class TestPropellerContract:
    def test_class_markers(self) -> None:
        assert Propeller.restart_on_visit is True
        assert Propeller.emits_rotation is True

    def test_constructor_validation(self) -> None:
        with pytest.raises(ValueError):
            Propeller(revolutions=0)
        with pytest.raises(ValueError):
            Propeller(spin_seconds=0.0)
        with pytest.raises(ValueError):
            Propeller(direction="sideways")
```

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest plugins/flair/tests/test_flair_propeller.py -v`
Expected: the new tests FAIL (stub has no `frame_for`).

- [ ] **Step 3: Implement (spec §9 verbatim)**

Replace `propeller.py`'s class body:

```python
"""flair.propeller — spin-in-then-rest whole-text rotation.

The message text spins in-plane like a propeller on visit entry
(ease-out cubic: fast start, soft landing), settles exactly flat, and
stays readable for the rest of the hold. Emits AnimationFrame.rotation;
the core seam (led-ticker-core >= 4.3) renders it. Composes with the
defer-to-rest settle via frames_to_rest, and with validate rules 62
(duration vs hold) / 63 (hires fonts don't rotate) via emits_rotation.
"""

from led_ticker.plugin import ENGINE_TICK_MS, AnimationFrame

_DIRECTIONS = ("cw", "ccw")


class Propeller:
    restart_on_visit = True  # spin on every visit
    emits_rotation = True  # read by core validate rule 63

    def __init__(
        self,
        revolutions: int = 2,
        spin_seconds: float = 1.0,
        direction: str = "cw",
    ) -> None:
        if not isinstance(revolutions, int) or isinstance(revolutions, bool) or revolutions < 1:
            raise ValueError(f"revolutions must be an int >= 1; got {revolutions!r}")
        if spin_seconds <= 0:
            raise ValueError(f"spin_seconds must be > 0; got {spin_seconds!r}")
        if direction not in _DIRECTIONS:
            raise ValueError(f"direction must be one of {_DIRECTIONS}; got {direction!r}")
        self.revolutions = revolutions
        self.spin_seconds = spin_seconds
        self.direction = direction
        self.total_frames = max(1, int(spin_seconds * 1000) // ENGINE_TICK_MS)

    def frame_for(self, frame, full_text, canvas_width, text_width):
        t = min(1.0, frame / self.total_frames)
        eased = 1.0 - (1.0 - t) ** 3  # ease-out cubic
        angle = (360.0 * self.revolutions * eased) % 360.0
        if self.direction == "ccw":
            angle = -angle % 360.0
        return AnimationFrame(visible_text=full_text, rotation=angle)

    def frames_to_rest(self, frame, total_chars):
        """One-shot rest: frames until the spin completes (0 forever after).
        The core settle seam consults this at the hold->transition handoff."""
        return max(0, self.total_frames - frame)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest plugins/flair -q`
Expected: all flair tests pass (new + the four sprite families + purity + packaging).

- [ ] **Step 5: Lint, pyright, commit**

```bash
uv run ruff check plugins/flair && uv run ruff format plugins/flair
uv run pyright plugins/flair/src 2>/dev/null || true  # run if the root Makefile wires pyright; follow monorepo convention
git add plugins/flair/src/led_ticker_flair/flair/propeller.py plugins/flair/tests/test_flair_propeller.py
git commit -m "feat(flair): Propeller — spin-in-then-rest rotation animation

Ease-out cubic envelope (exact 0.0 landing, gif-validated against the
core seam), cw/ccw, frames_to_rest for the settle seam, emits_rotation
for validate rule 63. Spec §9 verbatim."
```

---

### Task 3: docs + wheel metadata

**Files:**
- Modify: `plugins/flair/CLAUDE.md` ("One wheel, four plugin namespaces" → five, with the naming-exception note)
- Modify: `plugins/flair/README.md` (user-facing: the `flair.propeller` section — TOML examples for string + dict forms, the knobs table, the spin-in/rest behavior, the hires-font and short-hold caveats pointing at validate rules 62/63)
- Modify: `plugins/flair/pyproject.toml` `description` (mention the propeller animation)

**Steps:**

- [ ] **Step 1:** Read both files fully; match their voice. README gets: what it looks like (one sentence), config snippets (`animation = "flair.propeller"` and `{style = "flair.propeller", revolutions = 3, spin_seconds = 1.5, direction = "ccw"}`), knob table (revolutions ≥1 int, default 2; spin_seconds >0 float, default 1.0; direction cw/ccw, default cw), behavior notes (restarts each visit; transitions wait for the settle; `led-ticker validate` warns when the spin outlasts the hold (rule 62) or the widget uses a hires font (rule 63) — BDF fonts only for now), and the core version requirement (led-ticker-core >= 4.3).
- [ ] **Step 2:** CLAUDE.md invariants: update the namespace count, add one line: the `flair` namespace is the wheel's own name (animations), an intentional exception to the sprite-family pattern; sprites-beside-module invariant doesn't apply (no sprites).
- [ ] **Step 3:** `uv run pytest plugins/flair -q` still green (test_packaging may assert metadata — re-run).
- [ ] **Step 4:** Commit:

```bash
git add plugins/flair/CLAUDE.md plugins/flair/README.md plugins/flair/pyproject.toml
git commit -m "docs(flair): propeller README section + five-namespace invariants"
```

---

### Task 4: full verification + end-to-end gif through the real plugin loader

- [ ] **Step 1:** Monorepo-wide gates from the root: `uv run pytest plugins/flair -q` (and `make lint` if defined; otherwise `uv run ruff check plugins/ && uv run ruff format --check plugins/`).
- [ ] **Step 2:** END-TO-END gif (visual-validation checklist, `docs/visual-validation.md` in the core repo — this feature touches the render path, so run the matrix): with the monorepo venv carrying the editable core AND the flair package (`uv pip install -e plugins/flair` if not already a workspace member in the venv — verify with `uv run python -c "from importlib.metadata import entry_points; print([e.name for e in entry_points(group='led_ticker.plugins')])"` which must list `flair`), render from the CORE repo checkout using this venv... SIMPLER equivalent: run the render inside the monorepo venv with a small driver script that imports the core render pipeline (`sys.path` the core checkout's `tools/render_demo`). The configs to render, per the checklist matrix:
  - short text + `animation = "flair.propeller"` (defaults) + cut;
  - overflowing text (>2× canvas) + propeller;
  - emoji text (`:sun:`) + propeller;
  - `direction = "ccw"` variant;
  - a short-hold config (hold_time=0.5) to eyeball the settle handoff.
  Verify: no fully-black frames (lit-pixel profile), exact-flat rest (long deduped frames), ccw spins the other way. THIS time the animation resolves through the REAL entry-point loader — the last untested link.
- [ ] **Step 3:** Fix anything found (fail-first test, then fix); re-run.
- [ ] **Step 4:** Commit any fixes; report results honestly, including the render outputs.
