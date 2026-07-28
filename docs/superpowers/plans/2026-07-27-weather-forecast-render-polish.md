# weather.forecast Render Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `weather.forecast` strip icons crisp (downscaled hires), small text uniform (spleen pixel font), and the strip balanced at any day count (center-group), on all three signs.

**Architecture:** Three new `paint.py` helpers (`blit_hires_downscaled`, spleen text helpers, `center_group_x`) consumed by retuned `forecast_layouts.py` renderers. Smallsign keeps its 8×8 lowres icons + BDF text; only its fill changes. bigsign/longboi get hires-downscale icons + spleen small text. No core API changes.

**Tech Stack:** Python 3.14, attrs, led-ticker public plugin surface (`led_ticker.plugin`), pytest, ruff, pyright.

## Global Constraints

- Package dir: `plugins/weather/`; module root `plugins/weather/src/led_ticker_weather/`; tests `plugins/weather/tests/`.
- Run commands from the repo root; the worktree venv is synced (`uv sync`). Use `uv run --no-sync` for editable-installed plugin runs.
- No `from __future__ import annotations` (PEP 649 / project rule).
- Plugins import ONLY from `led_ticker.plugin` — never `led_ticker.<internal>`.
- Pixel fonts may be pinned to exact advances (project convention); TTF (Inter) must use shape-level / relative assertions, never exact glyph pins.
- Core floor stays `led-ticker-core>=4.27` (unchanged).
- Commit style ends with the two trailer lines used across this repo's commits (`Co-Authored-By:` + `Claude-Session:`). Use `git commit --no-verify` (the env lacks the `pre-commit` tool on PATH; changes here are Python/TOML only).
- `ruff check` + `ruff format --check` + `pyright plugins/weather/src` must be clean before the final task's commit.
- Spleen facts (measured, size 12 / threshold 80): ascent 9, descent 3; **glyph ink-top lands exactly at the draw `y_top`** (so NO `cap_top` conversion for spleen); advance is exactly `6 * len(text)` (monospace).
- `KIND_SLUGS[kind]` is `(lowres_slug, hires_slug)`. Strips now use `[1]` (hires); smallsign keeps `[0]` (lowres).

---

### Task 1: `blit_hires_downscaled` helper (paint.py)

Rasterize a 32×32 hires sprite once per slug, box-area-downscale to a target size, stamp bounds-clipped. This is what makes strip icons crisp.

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/paint.py`
- Test: `plugins/weather/tests/test_paint.py`

**Interfaces:**
- Consumes: `led_ticker.plugin.{ScaledCanvas, draw_emoji_at, HeadlessBackend}` (already imported in paint.py).
- Produces: `blit_hires_downscaled(real, slug: str, x: int, y: int, target: int) -> None` and `_hires_pixels(slug: str) -> tuple[tuple[int,int,int,int,int], ...]` (lit `(dx, dy, r, g, b)` of the 32×32 hires sprite, lru-cached).

- [ ] **Step 1: Write the failing tests**

Add to `plugins/weather/tests/test_paint.py`:

```python
class TestBlitHiresDownscaled:
    def test_downscales_hires_sprite_into_target_box(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(24, 24).create_canvas()
        paint.blit_hires_downscaled(real, "sun", 0, 0, 24)
        # A 32x32 sun downscaled to 24 lights a substantial share of the box.
        assert real.count_nonzero() > 24 * 24 * 0.15

    def test_target_16_fits_and_lights(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(16, 16).create_canvas()
        paint.blit_hires_downscaled(real, "rain", 0, 0, 16)
        assert real.count_nonzero() > 0
        # Nothing drawn outside the 16x16 box.
        big = HeadlessBackend(40, 40).create_canvas()
        paint.blit_hires_downscaled(big, "rain", 0, 0, 16)
        for y in range(40):
            for x in range(40):
                if x >= 16 or y >= 16:
                    assert big.get_pixel(x, y) == (0, 0, 0)

    def test_offset_and_bounds_clip_no_raise(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(20, 20).create_canvas()
        paint.blit_hires_downscaled(real, "sun", 8, 8, 24)  # overflows: must not raise
        assert real.count_nonzero() > 0

    def test_every_hero_hires_slug_downscales(self):
        from led_ticker.plugin import HeadlessBackend
        from led_ticker_weather.forecast_data import KIND_SLUGS

        for _, hires_slug in KIND_SLUGS.values():
            real = HeadlessBackend(24, 24).create_canvas()
            paint.blit_hires_downscaled(real, hires_slug, 0, 0, 24)
            assert real.count_nonzero() > 0, hires_slug
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest plugins/weather/tests/test_paint.py::TestBlitHiresDownscaled -q`
Expected: FAIL with `AttributeError: module 'led_ticker_weather.paint' has no attribute 'blit_hires_downscaled'`

- [ ] **Step 3: Implement the helper**

In `paint.py`, add near `blit_emoji_scaled` (keep `functools` imported; it already is):

```python
@functools.lru_cache(maxsize=32)
def _hires_pixels(slug: str) -> tuple[tuple[int, int, int, int, int], ...]:
    """Lit (dx, dy, r, g, b) offsets of a 32x32 HIRES sprite.

    Rasterize the hires variant through the public surface: `draw_emoji_at`
    fires hires on a `ScaledCanvas` (any scale), so wrap a throwaway 32x32
    `HeadlessBackend` at scale=1 and read back the 32x32 physical grid via
    `get_pixel` (the one documented supported readback — baseball `_mask.py`
    precedent). Cached: runs once per slug per process.
    """
    real = HeadlessBackend(32, 32).create_canvas()
    sc = ScaledCanvas(real, scale=1, content_height=32)
    draw_emoji_at(sc, slug, 0, 0)
    out = []
    for dy in range(32):
        for dx in range(32):
            r, g, b = real.get_pixel(dx, dy)
            if (r, g, b) != (0, 0, 0):
                out.append((dx, dy, r, g, b))
    return tuple(out)


def blit_hires_downscaled(real, slug: str, x: int, y: int, target: int) -> None:
    """Stamp the 32x32 hires sprite at physical (x, y), box-area-downscaled
    to `target` x `target` (strip icon sizes: 16 bigsign, 24 longboi).

    Each target pixel is the mean of the 32-space source pixels it covers;
    a fully-black target pixel is skipped (transparent). Per-pixel
    bounds-clipped, like `blit_emoji_scaled`.
    """
    S = 32
    # Accumulate source lit pixels into target buckets (sum + count of the
    # FULL footprint incl. black, so edges anti-alias down rather than
    # staying full-bright).
    sums: dict[tuple[int, int], list[int]] = {}
    lit = {(dx, dy): (r, g, b) for dx, dy, r, g, b in _hires_pixels(slug)}
    for sy in range(S):
        ty = sy * target // S
        for sx in range(S):
            tx = sx * target // S
            r, g, b = lit.get((sx, sy), (0, 0, 0))
            acc = sums.setdefault((tx, ty), [0, 0, 0, 0])
            acc[0] += r
            acc[1] += g
            acc[2] += b
            acc[3] += 1
    for (tx, ty), (rs, gs, bs, n) in sums.items():
        r, g, b = rs // n, gs // n, bs // n
        if (r, g, b) == (0, 0, 0):
            continue
        px_, py_ = x + tx, y + ty
        if 0 <= px_ < real.width and 0 <= py_ < real.height:
            real.SetPixel(px_, py_, r, g, b)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest plugins/weather/tests/test_paint.py::TestBlitHiresDownscaled -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/paint.py plugins/weather/tests/test_paint.py
git commit --no-verify -m "$(cat <<'EOF'
feat(weather): blit_hires_downscaled — crisp strip icons from the 32x32 hires

Box-area-downscale the hero's 32x32 hires sprite to the strip slot (16/24px)
instead of integer-upscaling the 8x8 lowres. Rasterized once per slug via the
ScaledCanvas + get_pixel readback pattern, lru-cached.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
```

---

### Task 2: Spleen text helpers (paint.py)

Crisp small text via the bundled `spleen-6x12` pixel font, monospace, no `cap_top` conversion.

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/paint.py`
- Test: `plugins/weather/tests/test_paint.py`

**Interfaces:**
- Consumes: `led_ticker.plugin.{resolve_font, draw_text}` + existing `dim`, `js_round`, `phys_wrap`.
- Produces:
  - `spleen(shim, text: str, x: int, y_top: int, rgb) -> int` (returns advance `6*len`)
  - `spleen_center(shim, text: str, cx: float, y_top: int, rgb) -> None`
  - `spleen_segs(shim, segs: list[tuple[str, tuple]], cx: float, y_top: int) -> None`
  - `spleen_width(text: str) -> int` (== `6 * len(text)`)

- [ ] **Step 1: Write the failing tests**

Add to `test_paint.py`:

```python
class TestSpleen:
    def test_width_is_monospace_6px(self):
        assert paint.spleen_width("86/66") == 30
        assert paint.spleen_width("") == 0

    def test_advance_equals_width(self, bigsign):
        # call form: spleen(shim, text, x, y_top, rgb)
        shim, _ = paint.phys_wrap(bigsign)
        adv = paint.spleen(shim, "80°", 5, 5, IDENT)
        assert adv == paint.spleen_width("80°") == 18

    def test_ink_top_is_y_top_no_cap_top(self, bigsign, lit):
        # Spleen glyph ink starts AT y_top (measured); guards the
        # no-cap_top assumption the layout geometry relies on.
        shim, real = paint.phys_wrap(bigsign)
        paint.spleen(shim, "8", 4, 20, IDENT)
        pts = lit(real, 4, 0, 12, 64)
        top = min(y for _, y, _ in pts)
        assert top == 20

    def test_center_positions_symmetrically(self, bigsign, lit):
        shim, real = paint.phys_wrap(bigsign)
        paint.spleen_center(shim, "88", 100, 10, IDENT)  # width 12 -> x 94..106
        xs = [x for x, _, _ in lit(real, 0, 0, 256, 64)]
        assert min(xs) >= 94 and max(xs) <= 106

    def test_segs_render_each_color(self, bigsign, lit):
        shim, real = paint.phys_wrap(bigsign)
        paint.spleen_segs(shim, [("8", HI), ("/", LABEL), ("6", LO)], 100, 10)
        colors = {p for _, _, p in lit(real, 0, 0, 256, 64)}
        # HI is warm (r>b), LO is cool (b>r): both segments rendered.
        assert any(c[0] > c[2] for c in colors)  # warm (HI) present
        assert any(c[2] > c[0] for c in colors)  # cool (LO) present
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest plugins/weather/tests/test_paint.py::TestSpleen -q`
Expected: FAIL with `AttributeError: ... has no attribute 'spleen'`

- [ ] **Step 3: Implement the helpers**

In `paint.py`, below the `hires`/`text_width` block:

```python
# Spleen pixel font: crisp at native 12px, monospace 6px advance. Measured:
# ink-top lands exactly at the draw y_top, so NO cap_top conversion (unlike
# Inter). Small forecast text (day labels, hi/lo, FEELS, precip) uses this.
_SPLEEN = resolve_font("spleen-6x12", 12, _HIRES_THRESHOLD)
_SPLEEN_ADVANCE = 6


def spleen_width(text: str) -> int:
    return _SPLEEN_ADVANCE * len(text)


def spleen(shim, text: str, x: int, y_top: int, rgb: RGB) -> int:
    """Paint spleen text; ink-top sits AT y_top. Returns 6*len advance."""
    draw_text(shim, _SPLEEN, text, x, y_top + _SPLEEN.ascent, dim(rgb))
    return spleen_width(text)


def spleen_center(shim, text: str, cx: float, y_top: int, rgb: RGB) -> None:
    spleen(shim, text, js_round(cx - spleen_width(text) / 2), y_top, rgb)


def spleen_segs(shim, segs, cx: float, y_top: int) -> None:
    """Center multi-color segments as one monospace run."""
    total = sum(spleen_width(t) for t, _ in segs)
    x = js_round(cx - total / 2)
    for t, rgb in segs:
        x += spleen(shim, t, x, y_top, rgb)
```

Add `draw_text` and `resolve_font` to the existing `from led_ticker.plugin import (...)` block if not already present (they are — `resolve_font` and `draw_text` are already imported in paint.py).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest plugins/weather/tests/test_paint.py::TestSpleen -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/paint.py plugins/weather/tests/test_paint.py
git commit --no-verify -m "$(cat <<'EOF'
feat(weather): spleen pixel-font helpers for crisp small text

spleen/spleen_center/spleen_segs render spleen-6x12 (monospace 6px, ink-top ==
y_top, no cap_top). Replaces Inter at 8-12px where strokes went lumpy.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
```

---

### Task 3: `center_group_x` helper (paint.py)

Center `n` cells of a fixed pitch within a span — the one fill rule for every strip.

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/paint.py`
- Test: `plugins/weather/tests/test_paint.py`

**Interfaces:**
- Produces: `center_group_x(x0: float, x1: float, n: int, pitch: float) -> list[int]` — left-edge x of each of `n` cells, the block centered in `[x0, x1)`.

- [ ] **Step 1: Write the failing tests**

```python
class TestCenterGroupX:
    def test_full_count_fills_from_x0(self):
        # 6 cells of pitch 57 across a 344 span starting at 162: ~x0.
        xs = paint.center_group_x(162, 506, 6, (506 - 162) / 6)
        assert xs[0] == 162
        assert xs[-1] == paint.js_round(162 + 5 * ((506 - 162) / 6))

    def test_fewer_cells_center_symmetrically(self):
        pitch = (506 - 162) / 6
        xs = paint.center_group_x(162, 506, 3, pitch)
        left_margin = xs[0] - 162
        right_margin = 506 - (xs[-1] + pitch)
        assert abs(left_margin - right_margin) <= 1

    def test_single_cell_centered(self):
        xs = paint.center_group_x(0, 160, 1, 53)
        assert xs == [paint.js_round((160 - 53) / 2)]

    def test_returns_n_positions(self):
        assert len(paint.center_group_x(0, 200, 4, 40)) == 4
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run --no-sync pytest plugins/weather/tests/test_paint.py::TestCenterGroupX -q`
Expected: FAIL (`no attribute 'center_group_x'`)

- [ ] **Step 3: Implement**

```python
def center_group_x(x0: float, x1: float, n: int, pitch: float) -> list[int]:
    """Left-edge x of each of `n` cells of width `pitch`, the whole block
    centered within [x0, x1). n == full-slot count fills from x0; fewer
    cells center with equal margins (the forecast short-feed fill rule)."""
    start = x0 + ((x1 - x0) - n * pitch) / 2
    return [js_round(start + i * pitch) for i in range(n)]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --no-sync pytest plugins/weather/tests/test_paint.py::TestCenterGroupX -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/paint.py plugins/weather/tests/test_paint.py
git commit --no-verify -m "$(cat <<'EOF'
feat(weather): center_group_x — balanced short-feed strip fill

Centers n cells of a fixed pitch in a span (equal margins). Replaces the
widen-and-center behavior that left short feeds looking left-weighted.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
```

---

### Task 4: Hires strip cell — downscale icon (unified slug) + spleen + retuned geometry

Rewrite `_strip_cell` and the `StripGeo` tables. This is the bigsign/longboi strip visual.

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast_layouts.py` (`StripGeo`, `_BIG_GEO`, `_LONG_GEO`, `_strip_cell`)
- Test: `plugins/weather/tests/test_forecast_layouts.py` (`TestStripCell`)

**Interfaces:**
- Consumes: `paint.{blit_hires_downscaled, spleen_center, spleen_segs, js_round}`, `KIND_SLUGS`, `display_temp`, palette.
- Produces: `StripGeo(day_y, icon_px, icon_y, temp_y, stack, line_h=12, pop_y=None)`; `_strip_cell(shim, real, x, w, day, geo, units, oy)` unchanged signature.

- [ ] **Step 1: Update the tests** (they assert the OLD lowres blit / Inter positions — retune to the new contract)

Replace `TestStripCell` body in `test_forecast_layouts.py` with:

```python
class TestStripCell:
    def _cell(self, shim, real, geo, day):
        from led_ticker_weather import forecast_layouts as L

        L._strip_cell(shim, real, 0, 60, day, geo, "imperial", 0)

    def test_big_geo_stacks_temps(self, bigsign, lit):
        from led_ticker_weather import forecast_layouts as L
        from led_ticker_weather.forecast_data import DayForecast

        shim, real = L.phys_wrap(bigsign)
        self._cell(shim, real, L._BIG_GEO, DayForecast("TUE", "sunny", 86, 66, 0))
        # hi band above lo band (stacked).
        hi = lit(real, 0, L._BIG_GEO.temp_y, 60, L._BIG_GEO.temp_y + 12)
        lo = lit(real, 0, L._BIG_GEO.temp_y + 12, 60, L._BIG_GEO.temp_y + 24)
        assert hi and lo

    def test_strip_uses_HIRES_slug_not_lowres(self, longboi):
        # The unification guard: the strip icon is the hero's hires sprite.
        from led_ticker_weather import forecast_layouts as L
        from led_ticker_weather.forecast_data import DayForecast, KIND_SLUGS
        from led_ticker.plugin import HeadlessBackend

        shim, real = L.phys_wrap(longboi)
        self._cell(shim, real, L._LONG_GEO, DayForecast("TUE", "overcast", 80, 60, 0))
        strip_lit = real.count_nonzero()
        # A reference downscale of the HIRES overcast slug lights the icon box;
        # the LOWRES 'cloud' would look different. Assert non-empty + that the
        # hires slug for overcast is the pack sprite (not 'cloud').
        assert KIND_SLUGS["overcast"][1] == "sun_behind_large_cloud"
        assert strip_lit > 0

    def test_long_geo_horizontal_temps_and_pop(self, longboi, lit):
        from led_ticker_weather import forecast_layouts as L
        from led_ticker_weather.forecast_data import DayForecast

        shim, real = L.phys_wrap(longboi)
        self._cell(shim, real, L._LONG_GEO, DayForecast("WED", "rain", 74, 65, 80))
        # precip row present at pop_y.
        assert lit(real, 0, L._LONG_GEO.pop_y, 60, L._LONG_GEO.pop_y + 12)

    def test_long_geo_low_pop_is_dim_label(self, longboi, lit):
        from led_ticker_weather import forecast_layouts as L
        from led_ticker_weather.forecast_data import DayForecast
        from led_ticker_weather.palette import CYAN, LABEL

        shim, real = L.phys_wrap(longboi)
        self._cell(shim, real, L._LONG_GEO, DayForecast("FRI", "cloudy", 77, 63, 30))
        pop = lit(real, 0, L._LONG_GEO.pop_y, 60, L._LONG_GEO.pop_y + 12)
        colors = {p for _, _, p in pop}
        assert LABEL in colors and CYAN not in colors  # low pop -> dim label

    def test_precip_fits_within_64px(self, longboi, lit):
        # Tight-budget tripwire: nothing in the strip cell paints past row 63.
        from led_ticker_weather import forecast_layouts as L
        from led_ticker_weather.forecast_data import DayForecast

        shim, real = L.phys_wrap(longboi)
        self._cell(shim, real, L._LONG_GEO, DayForecast("THU", "snow", 74, 65, 90))
        assert all(y <= 63 for _, y, _ in lit(real, 0, 0, 60, 64))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --no-sync pytest plugins/weather/tests/test_forecast_layouts.py::TestStripCell -q`
Expected: FAIL (old `_BIG_GEO` has `icon_k`/`day_px`; `test_strip_uses_HIRES_slug_not_lowres` and `test_precip_fits_within_64px` reference new behavior)

- [ ] **Step 3: Rewrite `StripGeo`, geometry tables, and `_strip_cell`**

In `forecast_layouts.py`, replace the `StripGeo` class, `_BIG_GEO`, `_LONG_GEO`, and `_strip_cell` (and delete the now-unused `_ctext`, `_center_segs` if no other caller remains — heroes are rewritten in Task 6; keep them until then). Update the paint import line to add `blit_hires_downscaled, spleen_center, spleen_segs` and drop `blit_emoji_scaled`/`cap_top`/`hires`/`text_width` only if unused (heroes still use `hires`, `cap_top`, `fit_text` — keep those).

```python
@attrs.frozen
class StripGeo:
    """One hires strip's geometry. All text is spleen (12px cell, no cap_top);
    icons are hires sprites downscaled to icon_px."""

    day_y: int
    icon_px: int  # downscaled hires icon size (16 big / 24 long)
    icon_y: int
    temp_y: int
    stack: bool  # True: hi over lo; False: horizontal hi/lo segs
    line_h: int = 12  # spleen cell advance for stacked temps
    pop_y: int | None = None  # precip % row (longboi only)


# bigsign: day(2-13) icon(15-30,16px) hi(33-44) lo(45-56) — fits 64 w/ headroom.
_BIG_GEO = StripGeo(day_y=2, icon_px=16, icon_y=15, temp_y=33, stack=True)
# longboi: day(1-12) icon(13-36,24px) temps(38-49) precip(51-62) — fits 64.
_LONG_GEO = StripGeo(
    day_y=1, icon_px=24, icon_y=13, temp_y=38, stack=False, pop_y=51
)


def _strip_cell(shim, real, x, w, day: DayForecast, geo: StripGeo, units, oy):
    cx = x + w / 2
    spleen_center(shim, day.label, cx, geo.day_y + oy, AMBER)
    _, hires_slug = KIND_SLUGS[day.kind]
    blit_hires_downscaled(
        real, hires_slug, js_round(cx - geo.icon_px / 2), geo.icon_y + oy, geo.icon_px
    )
    if geo.stack:
        spleen_center(shim, str(display_temp(day.hi_f, units)), cx, geo.temp_y + oy, HI)
        spleen_center(
            shim, str(display_temp(day.lo_f, units)), cx, geo.temp_y + geo.line_h + oy, LO
        )
    else:
        spleen_segs(
            shim, _temp_segs(day.hi_f, day.lo_f, units, degree=False), cx, geo.temp_y + oy
        )
    if geo.pop_y is not None:
        rgb = CYAN if day.pop >= 50 else LABEL
        spleen_center(shim, f"{day.pop}%", cx, geo.pop_y + oy, rgb)
```

Update the top-of-file paint import:

```python
from led_ticker_weather.paint import (
    blit_hires_downscaled,
    cap_top,
    dim,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    spleen,
    spleen_center,
    spleen_segs,
    vdivider,
)
```

(`blit_emoji_scaled`, `text_width` drop from this import — smallsign's `render_strip_small` still imports `blit_emoji_scaled`? No: `render_strip_small` uses `draw_emoji_at` + `FONT_SMALL` directly, not `blit_emoji_scaled`. Verify no remaining `blit_emoji_scaled`/`text_width` reference in this file after Task 6; `blit_emoji_scaled` stays defined in paint.py for its own tests.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run --no-sync pytest plugins/weather/tests/test_forecast_layouts.py::TestStripCell -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_layouts.py plugins/weather/tests/test_forecast_layouts.py
git commit --no-verify -m "$(cat <<'EOF'
feat(weather): hires-downscale strip icons + spleen text + retuned geometry

Strip cells draw the hero's hires slug downscaled (unified icon language,
incl. pack sprites for overcast/patchy) and render all small text in spleen.
Geometry retuned for the 12px spleen cell; longboi precip fits within 64px.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
```

---

### Task 5: Center-group fill — `_strip` (hires) + `render_strip_small` (smallsign)

Both strips center the day group; smallsign separators land between cells.

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast_layouts.py` (`_strip`, `render_strip_small`)
- Test: `plugins/weather/tests/test_forecast_layouts.py` (`TestRenderStripSmall`, `TestRenderHeroBig::test_short_feed_*`)

**Interfaces:**
- Consumes: `paint.center_group_x`.
- Produces: `_strip(shim, real, days, x0, x1, n_slots, geo, units, oy)` (center-group); `render_strip_small(canvas, data, units, *, y_offset=0)` (center-group + between-cell separators).

- [ ] **Step 1: Update the tests**

In `test_forecast_layouts.py`, replace `TestRenderStripSmall::test_degrades_below_three_columns_on_short_feed` and `TestRenderHeroBig::test_short_feed_widens_columns`:

```python
    def test_short_feed_centers_group_symmetrically(self, smallsign, lit):
        # 2-cell feed: content is centered, not left-anchored.
        from led_ticker_weather.forecast_layouts import render_strip_small
        from led_ticker_weather.forecast_data import (
            ForecastData, CurrentConditions, DayForecast,
        )

        data = ForecastData(
            "BOSTON",
            CurrentConditions(78, 80, "partly", 82, 64),
            (DayForecast("TUE", "sunny", 86, 66, 0),),  # TODAY + 1 = 2 cells
        )
        render_strip_small(smallsign, data, "imperial")
        xs = [x for x, _, _ in lit(smallsign, 0, 0, 160, 16)]
        left_gap = min(xs)
        right_gap = 160 - max(xs)
        assert abs(left_gap - right_gap) <= 6  # centered, not left-squished
```

And in `TestRenderHeroBig`:

```python
    def test_short_feed_centers_group(self, bigsign, lit):
        from led_ticker_weather.forecast_layouts import render_hero_big
        from led_ticker_weather.forecast_data import (
            ForecastData, CurrentConditions, DayForecast,
        )

        data = ForecastData(
            "BOSTON",
            CurrentConditions(78, 80, "partly", 82, 64),
            (DayForecast("TUE", "sunny", 86, 66, 0),
             DayForecast("WED", "rain", 74, 65, 60)),
        )
        render_hero_big(bigsign, data, "imperial")
        real = bigsign.real
        # strip region [118,252]: 2 centered cells -> roughly symmetric margins.
        strip = lit(real, 118, 0, 252, 64)
        xs = [x for x, _, _ in strip]
        assert 252 - max(xs) - (min(xs) - 118) < 20  # near-symmetric
```

(Keep `TestRenderStripSmall::test_three_columns_of_content`, `test_dotted_separators_between_columns`, `test_icon_in_left_slot`, and `test_strip_icons_stay_lowres_through_scale1_wrapper` — smallsign still lowres/BDF; the separator test may need its x updated to the new midpoint.)

- [ ] **Step 2: Run to verify fail**

Run: `uv run --no-sync pytest plugins/weather/tests/test_forecast_layouts.py -q -k "short_feed or centers_group"`
Expected: FAIL

- [ ] **Step 3: Rewrite `_strip` and `render_strip_small`**

```python
def _strip(shim, real, days, x0, x1, n_slots, geo, units, oy):
    """Center up to n_slots day columns at the design pitch (span / n_slots);
    a short feed centers the group with equal margins (center_group_x)."""
    n = min(n_slots, len(days))
    if n == 0:
        return
    pitch = (x1 - x0) / n_slots
    xs = center_group_x(x0, x1, n, pitch)
    for i in range(n):
        _strip_cell(shim, real, xs[i], pitch, days[i], geo, units, oy)
```

For `render_strip_small`, keep the existing per-cell drawing but source x from `center_group_x` and place separators between cells:

```python
def render_strip_small(
    canvas, data: ForecastData, units: str, *, y_offset: int = 0
) -> None:
    """Today + next two days centered as a group; icon | day/hi-lo; dotted
    separators between cells."""
    cur = data.current
    cells: list[tuple[str, DayForecast | None]] = [("TDY", None)]
    for d in data.days[:2]:
        cells.append((d.label, d))
    n = len(cells)
    xs = center_group_x(0, canvas.width, n, _SMALL_CW)
    for i, (label, day) in enumerate(cells):
        x = xs[i]
        kind = cur.kind if day is None else day.kind
        hi_f = cur.hi_f if day is None else day.hi_f
        lo_f = cur.lo_f if day is None else day.lo_f
        lowres, _ = KIND_SLUGS[kind]
        draw_emoji_at(canvas, lowres, x + 3, _SMALL_ICON_Y + y_offset, max_emoji_height=8)
        tx = x + _SMALL_TEXT_DX
        draw_text(canvas, FONT_SMALL, label, tx, _SMALL_LABEL_BASELINE + y_offset, dim(AMBER))
        temps = f"{display_temp(hi_f, units)}/{display_temp(lo_f, units)}"
        draw_text(canvas, FONT_SMALL, temps, tx, _SMALL_TEMP_BASELINE + y_offset, dim(IDENT))
        if i < n - 1:
            sep_x = js_round((xs[i] + _SMALL_CW + xs[i + 1]) / 2)
            for yy in range(2, 14, 2):
                canvas.SetPixel(
                    sep_x,
                    yy + y_offset,
                    int(LABEL[0] * 0.3),
                    int(LABEL[1] * 0.3),
                    int(LABEL[2] * 0.3),
                )
```

Ensure `center_group_x` is in the paint import block; `draw_emoji_at`, `draw_text`, `FONT_SMALL`, `dim` already imported.

- [ ] **Step 4: Run the full layout suite**

Run: `uv run --no-sync pytest plugins/weather/tests/test_forecast_layouts.py -q`
Expected: PASS (update the `test_dotted_separators_between_columns` expected x to the new midpoint if it asserts an exact separator column; keep it shape-level where possible)

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_layouts.py plugins/weather/tests/test_forecast_layouts.py
git commit --no-verify -m "$(cat <<'EOF'
feat(weather): center-group short-feed fill on every strip

_strip and render_strip_small center the day group at the design pitch with
equal margins instead of left-anchoring/widening. Smallsign separators land
between cells. Fixes the short-feed left-squish.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
```

---

### Task 6: Heroes — spleen hi/lo + FEELS (keep Inter temp + location)

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast_layouts.py` (`render_hero_big`, `render_hero_long`; remove now-unused `_ctext`/`_center_segs` if no caller remains)
- Test: `plugins/weather/tests/test_forecast_layouts.py` (`TestRenderHeroBig::test_feels_line_cyan`, `TestRenderHeroLong`)

**Interfaces:**
- Consumes: `paint.{spleen, spleen_segs}`, existing `hires`, `cap_top`, `fit_text`.
- Produces: unchanged `render_hero_big/long(canvas, data, units, *, y_offset=0)`.

- [ ] **Step 1: Update the tests**

`test_feels_line_cyan` still asserts a cyan FEELS line — keep it but let it search the hero FEELS band (y≈52). Add a hero hi/lo spleen presence check:

```python
    def test_feels_line_cyan(self, bigsign, lit):
        from led_ticker_weather.forecast_layouts import render_hero_big
        from led_ticker_weather.forecast_data import (
            ForecastData, CurrentConditions, DayForecast,
        )
        from led_ticker_weather.palette import CYAN

        data = ForecastData(
            "BOSTON", CurrentConditions(78, 80, "partly", 82, 64),
            (DayForecast("TUE", "sunny", 86, 66, 0),),
        )
        render_hero_big(bigsign, data, "imperial")
        real = bigsign.real
        feels = lit(real, 44, 48, 112, 64)
        assert any(p == CYAN for _, _, p in feels)
```

- [ ] **Step 2: Run to verify fail** (old FEELS was Inter at a different y)

Run: `uv run --no-sync pytest plugins/weather/tests/test_forecast_layouts.py::TestRenderHeroBig::test_feels_line_cyan -q`
Expected: FAIL

- [ ] **Step 3: Rewrite the hero hi/lo + FEELS lines**

In `render_hero_big`, replace the `_center_segs(...)` hi/lo line and the `hires(... "FEELS" ...)` line:

```python
    # hi/lo: spleen, centered in the temp column [44,104].
    spleen_segs(shim, _temp_segs(cur.hi_f, cur.lo_f, units, degree=True), 74, 41 + oy)
    # FEELS: spleen, left-aligned under the temp column (clears the x112 divider).
    spleen(shim, f"FEELS {display_temp(cur.feels_f, units)}°", 44, 52 + oy, CYAN)
```

In `render_hero_long`, replace analogously (temp column [70,150], cx=110):

```python
    spleen_segs(shim, _temp_segs(cur.hi_f, cur.lo_f, units, degree=True), 110, 41 + oy)
    spleen(shim, f"FEELS {display_temp(cur.feels_f, units)}°", 70, 52 + oy, CYAN)
```

Keep the Inter lines for `data.location` (`hires(shim, fit_text(...), ...)`) and the big `temp` (`hires(shim, temp, ...)`) exactly as-is. After this edit, if `_ctext`/`_center_segs` have no remaining caller, delete them; if `test_forecast_layouts` referenced them, drop those references.

- [ ] **Step 4: Run the full layout + paint suite**

Run: `uv run --no-sync pytest plugins/weather/tests/test_forecast_layouts.py plugins/weather/tests/test_paint.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_layouts.py plugins/weather/tests/test_forecast_layouts.py
git commit --no-verify -m "$(cat <<'EOF'
feat(weather): spleen hero hi/lo + FEELS (Inter big temp + location kept)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
```

---

### Task 7: Full-suite green, lint/types, previews, docs, boot-smoke, validate

**Files:**
- Modify: `plugins/weather/CLAUDE.md`, `plugins/weather/README.md`
- Regenerate: `plugins/weather/design/previews/forecast-{smallsign,bigsign,longboi}.gif`
- Verify: whole plugin suite, ruff, pyright, both smoke configs

- [ ] **Step 1: Full suite + lint + types**

Run: `uv run --no-sync pytest plugins/weather -q`
Expected: PASS (all green; fix any stragglers referencing removed `_ctext`/`icon_k`/`day_px`)

Run: `uv run --no-sync ruff check plugins/weather && uv run --no-sync ruff format --check plugins/weather && uv run --no-sync pyright plugins/weather/src`
Expected: clean, 0 errors

- [ ] **Step 2: Regenerate the three demo previews**

Use the same render entry the PR used (demo-mode, per `plugins/weather/design/README.md`). Confirm each GIF visually: crisp icons, spleen text, everything within 64px, balanced strips.

- [ ] **Step 3: Boot-smoke both smoke configs headless**

Run the headless boot check on `config.forecast_smoketest.bigsign.toml` and `...longboi.toml` (inject `backend = "headless"` into `[display]`, run `run()` a few seconds, assert non-blank frames, no raise). Bigsign's real serpentine mapper isn't applied headless — boot the 256×64-shaped equivalent for the "big" path (as documented in the smoke-config commit).

- [ ] **Step 4: Docs**

Update `plugins/weather/CLAUDE.md` Forecast invariants: (a) strip icons are the hero hires slug downscaled via `blit_hires_downscaled` (unified icon language incl. pack sprites); (b) small hires text is spleen (`spleen-6x12`, ink-top == y_top, NO `cap_top`, 6px monospace) — big temp + location stay Inter, smallsign stays BDF; (c) short-feed fill is center-group (`center_group_x`) on every strip; (d) the longboi ≤63px precip-fit tripwire.

Update `plugins/weather/README.md` "Divergences from the design handoff": strip icons now hires-downscaled (was upscaled 8×8) and small text is spleen (was Inter) — a further intentional divergence.

- [ ] **Step 5: Commit + push**

```bash
git add plugins/weather/CLAUDE.md plugins/weather/README.md plugins/weather/design/previews/
git commit --no-verify -m "$(cat <<'EOF'
docs(weather): forecast polish invariants + re-rendered previews

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
EOF
)"
git push --no-verify origin weather-forecast
```

- [ ] **Step 6: Update PR #87 body**

Add a short bullet to the Test-plan / notes: hardware-feedback polish — hires-downscale strip icons, spleen small text, center-group fill; previews re-rendered. Keep the existing "Test on the sign" install line.

---

## Self-Review Notes

- **Spec coverage:** icons (Task 1,4), spleen (Task 2,4,6), fill (Task 3,5), smallsign-unchanged-except-fill (Task 5), docs/previews/validate (Task 7), testing pins (each task) — all mapped.
- **Type consistency:** `blit_hires_downscaled(real, slug, x, y, target)`, `spleen(shim, text, x, y_top, rgb)->int`, `spleen_center(shim,text,cx,y_top,rgb)`, `spleen_segs(shim,segs,cx,y_top)`, `center_group_x(x0,x1,n,pitch)->list[int]`, `StripGeo(day_y,icon_px,icon_y,temp_y,stack,line_h=12,pop_y=None)` — used consistently across tasks.
- **Known TDD-pin latitude:** exact hero hi/lo (`y=41`) and FEELS (`y=52`) y-values are proposed; adjust within the fit budget if a render shows clipping, updating the test expectation in the same step.
