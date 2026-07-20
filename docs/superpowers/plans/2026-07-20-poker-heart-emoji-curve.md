# Poker Heart Emoji-Curve Mask Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace poker's pinched heart mask with core's `:heart:` emoji implicit curve (spec-approved candidate B), fixing the dangling-tip pinch on hearts and the needle-top on spades.

**Architecture:** One function body swap in `plugins/flair/src/led_ticker_flair/flair/poker.py` (`_in_heart`), guarded by a new pinch-regression tripwire. `_in_spade` inherits the fix unchanged. All existing shape/reveal/perf tests re-verify against the new geometry.

**Tech Stack:** Python, pytest. Repo `led-ticker-plugins`, checkout `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `poker-heart-emoji`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-poker-heart-emoji-curve-design.md` — the replacement formula there is normative (scale `(2*r)/2.6`, bias `+0.25`, strict `< 0`).
- Work ONLY on branch `poker-heart-emoji`; `git branch --show-current` first, abort otherwise.
- `_in_spade`, diamonds, clubs, ring width, pulse timing, knobs: UNCHANGED.
- Full-reveal matrix (`_FULL_REVEAL_POOLS` × geometries × seeds + pinned clubs cases) must pass unchanged — do not weaken any reveal test.
- Lint gates from `plugins/flair/`: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`.
- Task 2 ends at a HARD STOP: James reviews in-motion GIFs before the PR opens.
- PR body carries "Test on the sign" (branch-ref line + `down -v` note) + the perf sweep numbers. Release after merge word: `cut_release.py flair patch`.

All commands run from `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair/` unless noted.

---

### Task 1: Pinch tripwire + mask swap

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/poker.py` (`_in_heart`, currently the two-lobes + linear-wedge body around lines 24–42)
- Test: `plugins/flair/tests/test_flair_poker_shapes.py` (append)

**Interfaces:**
- Consumes: existing `interior_pixels(suit, r)` / `inside(suit, x, y, r)` helpers.
- Produces: the new `_in_heart(x, y, r) -> bool` (same signature); Task 2 renders with it.

- [ ] **Step 1: Write the failing pinch tripwire**

Append to `plugins/flair/tests/test_flair_poker_shapes.py`:

```python
class TestHeartNotPinched:
    """James (2026-07-19): the heart bottom looked pinched on the sign — the
    old linear wedge left a multi-row 1–4 px spike dangling below the body.
    The emoji-curve mask (spec 2026-07-20) tapers to the tip within a couple
    of rows. Guard the taper rate, not the exact silhouette."""

    @staticmethod
    def _row_widths(r):
        pts = interior_pixels("hearts", r)
        rows = {}
        for x, y in pts:
            lo, hi = rows.get(y, (x, x))
            rows[y] = (min(lo, x), max(hi, x))
        return {y: hi - lo + 1 for y, (lo, hi) in rows.items()}

    def test_bottom_taper_is_short(self):
        # At each display-relevant radius, rows narrower than a quarter of
        # the shape's width must be confined to the last couple of tip rows —
        # the old mask had 5+ such rows at r=20 (the visible spike).
        for r in (7, 12, 20):
            widths = self._row_widths(r)
            max_w = max(widths.values())
            narrow = [y for y, w in widths.items() if w <= max(2, max_w // 4)]
            assert len(narrow) <= 3, (
                f"r={r}: {len(narrow)} narrow rows {sorted(narrow)} — "
                "pinched tip is back"
            )

    def test_heart_still_heart_shaped(self):
        # Sanity net alongside the taper guard: symmetric, top notch between
        # lobes, single bottom tip, fits the ±r box.
        r = 16
        pts = interior_pixels("hearts", r)
        assert pts == {(-x, y) for x, y in pts}  # x-mirror symmetric
        ys = [y for _, y in pts]
        top, bot = min(ys), max(ys)
        assert bot > 0 > top
        assert all(abs(x) <= r and -r <= y <= r for x, y in pts)
        # top notch: on the topmost lobe row, x=0 is OUTSIDE (cleft)
        top_row_xs = {x for x, y in pts if y == top}
        assert 0 not in top_row_xs
```

- [ ] **Step 2: Run to verify the tripwire fails on the OLD mask**

Run: `uv run --extra dev pytest tests/test_flair_poker_shapes.py -q -k HeartNotPinched`
Expected: `test_bottom_taper_is_short` FAILS (old mask has 5+ narrow rows at r=20); `test_heart_still_heart_shaped` may pass (it holds for both shapes — it is the anti-regression net for the NEW one).

- [ ] **Step 3: Swap `_in_heart` to the emoji curve**

Replace the entire `_in_heart` body in `plugins/flair/src/led_ticker_flair/flair/poker.py` (keep the function name/signature; delete the old lobes+wedge code and its 2026-07-17 comment) with the spec's normative version:

```python
def _in_heart(x, y, r):
    # Core's hi-res :heart: emoji curve (pixel_emoji._generate_heart_hires):
    # classic implicit heart with the EMOJI's normalization — scale spans
    # 2.6 curve-units across the 2r-px box, +0.25 vertical bias. The July
    # "shield" reading came from a different normalization, not the curve;
    # adopted 2026-07-20 to fix the pinched bottom (spec
    # 2026-07-20-poker-heart-emoji-curve-design.md).
    if r <= 0:
        return False
    s = (2 * r) / 2.6
    nx = x / s
    ny = -y / s + 0.25
    return (nx * nx + ny * ny - 1) ** 3 - nx * nx * ny * ny * ny < 0
```

- [ ] **Step 4: Run the full flair suite + lint gates**

Run: `uv run --extra dev pytest tests/ -q`
Expected: ALL pass — including `TestHeartNotPinched` (now green), the full-reveal matrix, and the pinned clubs regression cases. If any full-reveal case fails, STOP — that's a coverage regression the spec says must not happen; do not raise `_MAX_R_FACTOR` without discussion.

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/poker.py plugins/flair/tests/test_flair_poker_shapes.py
git commit -m "fix(poker): heart mask -> emoji implicit curve (un-pinch the tip)"
```

---

### Task 2: Perf sweep + visual gate (HARD STOP for James)

**Files:**
- Scratch only: `$CLAUDE_JOB_DIR/tmp/poker_frametime2.py`, gate GIFs

**Interfaces:**
- Consumes: the swapped mask from Task 1.
- Produces: perf numbers for the PR body; two GIFs for James.

- [ ] **Step 1: Frame-time sweep (fresh + refire)**

Write `$CLAUDE_JOB_DIR/tmp/poker_frametime2.py`:

```python
import time
from unittest import mock

from led_ticker.plugin import ScaledCanvas
from led_ticker_flair.flair.poker import Poker


class Stub:
    def __init__(self, w, h):
        self.width, self.height = w, h

    def SetPixel(self, *a):
        pass

    def Clear(self):
        pass

    def Fill(self, *a):
        pass


def widget():
    w = mock.Mock()
    w.draw.side_effect = lambda c, cursor_pos=0, **k: (c, cursor_pos)
    return w


def sweep(p, canvas, o, i, label):
    times = []
    t = 0.02
    while t < 1.0:
        t0 = time.perf_counter()
        p.frame_at(round(t, 4), canvas, o, i)
        times.append((round(t, 2), (time.perf_counter() - t0) * 1000))
        t += 0.02
    ordered = sorted(times, key=lambda x: -x[1])
    avg = sum(ms for _, ms in times) / len(times)
    print(f"{label}: avg {avg:.2f}ms worst {ordered[0][1]:.2f}ms @ t={ordered[0][0]}")
    return avg, ordered[0][1]


canvas = ScaledCanvas(Stub(256, 64), scale=4, content_height=16)
o, i = widget(), widget()
p = Poker(suits=["hearts", "spades"])  # seed=None, the affected suits
a1, w1 = sweep(p, canvas, o, i, "firing 1")
a2, w2 = sweep(p, canvas, o, i, "firing 2 (refire)")
assert w1 <= 5 * a1 and w2 <= 5 * a2, "spike gate FAILED"
print("spike gate OK")
```

Run: `uv run --extra dev python $CLAUDE_JOB_DIR/tmp/poker_frametime2.py`
Expected: comparable to the 0.10.1 numbers (avg <1ms, worst <4ms after first-ever process warm; the first run in the process pays the one-time geometry warm — run the script twice and read the SECOND process's numbers, or note the warm explicitly). Record for the PR body.

- [ ] **Step 2: Render gate GIFs (hearts pool + spades pool)**

From the CORE repo (`/Users/james/projects/github/jamesawesome/led-ticker`): reinstall the branch build editable, then render two configs derived from `docs/site/demos-pinned/transition-flair-poker.toml` — copy it to `$CLAUDE_JOB_DIR/tmp/poker-hearts-gate.toml` and `$CLAUDE_JOB_DIR/tmp/poker-spades-gate.toml`, changing both sections' transition line to `{type = "flair.poker", suits = ["hearts"], seed = 3}` (hearts file) and `{type = "flair.poker", suits = ["spades"], seed = 3}` (spades file):

```bash
uv pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair
uv run --no-sync python tools/render_demo/render.py $CLAUDE_JOB_DIR/tmp/poker-hearts-gate.toml -o $CLAUDE_JOB_DIR/tmp/poker-hearts-new.gif --duration 10
uv run --no-sync python tools/render_demo/render.py $CLAUDE_JOB_DIR/tmp/poker-spades-gate.toml -o $CLAUDE_JOB_DIR/tmp/poker-spades-new.gif --duration 10
```

(`--no-sync` is load-bearing: plain `uv run` re-syncs the venv and uninstalls the editable flair.)

- [ ] **Step 3: HARD STOP — send both GIFs to James**

Send `poker-hearts-new.gif` + `poker-spades-new.gif` with the perf numbers. Ask: do the resting glyphs and the expanding ripple rings read as hearts/spades (no pinch, no shield)? Do NOT open the PR until approved. Iterate only on request.

---

### Task 3 (post-gate): PR

**Files:** none new (PR only).

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin poker-heart-emoji
gh pr create --title "fix(poker): heart mask -> emoji implicit curve (un-pinch the tip)" --body-file <body file>
```

Body: what/why (James's on-sign observation), the A/B/C comparison outcome (B = the emoji's own curve + normalization; July shield-reading was the normalization, not the curve), spade inherits the fix, the pinch tripwire, full-reveal matrix unchanged, perf numbers, gate GIFs, and:

```
## Test on the sign
config/requirements-plugins.txt:
  led-ticker-flair @ git+https://github.com/JamesAwesome/led-ticker-plugins.git@poker-heart-emoji#subdirectory=plugins/flair
then: docker compose down -v && docker compose up -d
The poker smoke config (plugins/flair/examples/config.poker-smoke.bigsign.toml) sections 1/5 show hearts + spades.
```

- [ ] **Step 2: Watch CI**

Run: `gh pr checks --watch --interval 30` — all green expected.

- [ ] **Step 3: After James's merge word (NOT before)**

Squash-merge, then `uv run python scripts/cut_release.py flair patch --notes <notes file>` (notes: heart un-pinch via emoji curve, spade inherited, no config changes), approve the PyPI deployment via `gh api .../pending_deployments`, verify PyPI shows the new version.
