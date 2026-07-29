# weather.forecast Multi-Day Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `weather.forecast` widget — a held multi-day forecast card with per-sign auto-detected layouts (smallsign 3-day strip / bigsign hero+4-day / longboi hero+6-day) per the approved spec.

**Architecture:** Flight-pattern modules inside `plugins/weather/`: a pure `resolve_forecast_layout`, a data layer (`forecast_data.py`) over WeatherAPI `/v1/forecast.json`, physical-paint helpers (`paint.py`, ported from baseball `_paint.py`), and three renderers sharing one parameterized strip cell (`forecast_layouts.py`). Icons come from packaged emoji (curated lowres blits in strips, 32×32 hires/pack sprites in heroes).

**Tech Stack:** Python 3.14, attrs, aiohttp, `led_ticker.plugin` public surface only, pytest.

**Spec:** `docs/superpowers/specs/2026-07-22-weather-forecast-widget-design.md` (this repo). Normative visual reference: `plugins/weather/design/` (README.md + `Weather Forecast.dc.html`).

## Global Constraints

- **Worktree/branch:** all work in `/Users/james/projects/github/jamesawesome/led-ticker-plugins-weather-forecast` on branch `weather-forecast`. Run all commands from that repo root. Before any git operation, verify `pwd` and `git branch --show-current` = `weather-forecast`.
- **Public surface only:** every `led_ticker` import from `led_ticker.plugin`. `tests/test_import_purity.py` AST-enforces this; a failure is a contract violation, never a test to relax.
- **No `from __future__ import annotations`** anywhere (Python 3.14 / PEP 649).
- **`js_round`, never bare `round()`** for any handoff-ported geometry (JS `Math.round` is half-up; Python's is banker's).
- **Never exact-pin hi-res text pixels in tests** (freetype differs macOS vs Linux CI). Assert "pixels of color C exist in region R". Lowres emoji blits and dotted dividers ARE exact-pinnable.
- **Held-cursor contract:** `draw()` returns `cursor = canvas.width` — the wrapper's LOGICAL width, never `real.width`.
- **`bg_color` declared only** — the engine paints it; `draw()` never calls `Fill()`.
- Handoff cap-top convention: the design engine crops text masks to visible ink, so every handoff `y` for hires text is a VISUAL CAP-TOP y; convert with `cap_top(y_target, size)` before calling `hires()` (verified against the bundle's `rasterize()`; same as baseball, NOT flight's raw ascent-top).
- Test command: `uv run pytest plugins/weather -q` (suite must stay green after every task). Lint: `uv run ruff check plugins/weather`.
- Commit style: `feat(weather): …` / `test(weather): …` / `docs(weather): …`, ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Canvas fixtures + palette + paint core helpers

**Files:**
- Modify: `plugins/weather/tests/conftest.py`
- Create: `plugins/weather/src/led_ticker_weather/palette.py`
- Create: `plugins/weather/src/led_ticker_weather/paint.py`
- Test: `plugins/weather/tests/test_paint.py`

**Interfaces:**
- Produces: `palette.RGB = tuple[int, int, int]`; constants `IDENT/LABEL/AMBER/HI/LO/CYAN`.
- Produces: `paint.js_round(v: float) -> int`, `paint.cap_top(y_target: int, size: int) -> int`, `paint.phys_wrap(canvas) -> (shim, real)`, `paint.dim(rgb: RGB, bright: float = 1.0) -> Color`, `paint.px(real, x, y, rgb, bright=1.0) -> None`, `paint.hires(shim, text, x, y_top, rgb, size, *, bold=True) -> int` (ADVANCE width, physical px), `paint.text_width(size, text, *, bold=True) -> int`, `paint.fit_text(text, max_w, size, *, bold=True) -> str`, `paint.vdivider(real, x, y0, y1) -> None`.
- Produces (fixtures): `smallsign` (HeadlessCanvas 160×16), `bigsign` (ScaledCanvas over 256×64, scale 4, content_height 16), `longboi` (ScaledCanvas over 512×64, scale 4, content_height 16), `lit` (helper: lit pixels in a physical region).

- [ ] **Step 1: Add canvas fixtures to conftest**

Append to `plugins/weather/tests/conftest.py`:

```python
from led_ticker.plugin import HeadlessBackend, ScaledCanvas


@pytest.fixture
def smallsign():
    """160x16 scale-1 headless canvas (smallsign geometry)."""
    return HeadlessBackend(160, 16).create_canvas()


@pytest.fixture
def bigsign():
    """256x64 physical wrapped at scale 4 (bigsign geometry)."""
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def longboi():
    """512x64 physical wrapped at scale 4 (longboi geometry)."""
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def lit():
    """Lit pixels [(x, y, (r, g, b)), ...] in a physical region of a
    HeadlessCanvas (get_pixel is the one supported readback)."""

    def _lit(real, x0, y0, x1, y1):
        out = []
        for y in range(y0, y1):
            for x in range(x0, x1):
                p = real.get_pixel(x, y)
                if p != (0, 0, 0):
                    out.append((x, y, p))
        return out

    return _lit
```

- [ ] **Step 2: Write failing tests**

Create `plugins/weather/tests/test_paint.py`:

```python
"""paint.py helpers — ported from baseball _paint.py (see that module's
docstrings for the cap-top derivation)."""

from led_ticker_weather import paint
from led_ticker_weather.palette import AMBER, CYAN, HI, IDENT, LABEL, LO


class TestJsRound:
    def test_half_up_at_boundary(self):
        assert paint.js_round(2.5) == 3  # Python round() would give 2

    def test_negative_half(self):
        assert paint.js_round(-2.5) == -2  # JS Math.round(-2.5) == -2

    def test_plain_values(self):
        assert paint.js_round(2.4) == 2
        assert paint.js_round(2.6) == 3


class TestCapTop:
    def test_formula(self):
        # y_target - size + js_round(size * 0.72), the baseball formula
        assert paint.cap_top(13, 27) == 13 - 27 + paint.js_round(27 * 0.72)

    def test_shifts_up(self):
        assert paint.cap_top(10, 12) < 10


class TestPalette:
    def test_semantic_tokens_match_handoff(self):
        assert IDENT == (255, 255, 255)
        assert LABEL == (70, 90, 130)
        assert AMBER == (255, 180, 0)
        assert HI == (255, 148, 36)
        assert LO == (70, 180, 255)
        assert CYAN == (0, 200, 255)


class TestPx:
    def test_sets_pixel_with_brightness(self, smallsign):
        paint.px(smallsign, 3, 4, (200, 100, 50), 0.5)
        assert smallsign.get_pixel(3, 4) == (100, 50, 25)

    def test_out_of_bounds_is_noop(self, smallsign):
        paint.px(smallsign, -1, 0, (255, 255, 255))
        paint.px(smallsign, 160, 0, (255, 255, 255))
        paint.px(smallsign, 0, 16, (255, 255, 255))
        assert smallsign.count_nonzero() == 0


class TestHires:
    def test_draws_ink_and_returns_positive_advance(self, bigsign, lit):
        shim, real = paint.phys_wrap(bigsign)
        adv = paint.hires(shim, "78", 10, 10, IDENT, 20)
        assert adv > 0
        assert lit(real, 10, 10, 10 + adv + 2, 40)  # shape-level, never exact-pin

    def test_advance_is_relative_not_absolute(self, bigsign):
        shim, _ = paint.phys_wrap(bigsign)
        a0 = paint.hires(shim, "78", 0, 10, IDENT, 20)
        a50 = paint.hires(shim, "78", 50, 10, IDENT, 20)
        assert a0 == a50  # advance width, not end-x


class TestTextWidth:
    def test_matches_hires_advance(self, bigsign):
        shim, _ = paint.phys_wrap(bigsign)
        assert paint.text_width(20, "78/64") == paint.hires(
            shim, "78/64", 0, 10, IDENT, 20
        )

    def test_wider_text_measures_wider(self):
        assert paint.text_width(12, "100") > paint.text_width(12, "7")


class TestFitText:
    def test_fits_unchanged(self):
        assert paint.fit_text("BOS", 500, 11) == "BOS"

    def test_truncates_with_ellipsis(self):
        long = "SOUTH BURLINGTON HEIGHTS"
        out = paint.fit_text(long, 60, 11)
        assert out.endswith("…")
        assert paint.text_width(11, out) <= 60

    def test_strips_trailing_space_before_ellipsis(self):
        out = paint.fit_text("AB CDEFGHIJ", 30, 11)
        assert " …" not in out


class TestVdivider:
    def test_dotted_every_third_row(self, bigsign, lit):
        _, real = paint.phys_wrap(bigsign)
        paint.vdivider(real, 112, 6, 58)
        pts = lit(real, 112, 6, 113, 58)
        assert [(x, y) for x, y, _ in pts] == [(112, y) for y in range(6, 58, 3)]

    def test_dim_label_color(self, bigsign):
        _, real = paint.phys_wrap(bigsign)
        paint.vdivider(real, 112, 6, 58)
        r, g, b = real.get_pixel(112, 6)
        assert (r, g, b) == (int(70 * 0.4), int(90 * 0.4), int(130 * 0.4))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_paint.py -q`
Expected: FAIL / collection error — `No module named 'led_ticker_weather.paint'`.

- [ ] **Step 4: Create palette.py**

```python
"""Semantic palette from design/README.md Design Tokens.

Values are the handoff table's 0-255 RGB verbatim. The handoff's own 0-1
normalization is prototype-engine-specific (its framebuffer stores 0-1)
and deliberately does NOT port — core takes 0-255.

Glyph-drawing tokens (sun/moon/cloud/rain/snow/bolt) do not port either:
icon colors come from the packaged emoji sprites themselves (spec
divergence 1).
"""

RGB = tuple[int, int, int]

IDENT: RGB = (255, 255, 255)  # current temp / neutral text
LABEL: RGB = (70, 90, 130)  # dim labels, dividers, low precip, hi/lo slash
AMBER: RGB = (255, 180, 0)  # day labels
HI: RGB = (255, 148, 36)  # high temp (warm)
LO: RGB = (70, 180, 255)  # low temp (cool)
CYAN: RGB = (0, 200, 255)  # FEELS line, precip >= 50%
```

- [ ] **Step 5: Create paint.py**

```python
"""Physical-pixel hi-res paint helpers (ported from baseball `_paint.py` /
flight `paint.py` — the proven scale-1 ScaledCanvas shim pattern).

`phys_wrap` wraps the REAL canvas at scale=1 so `draw_text` places hi-res
glyphs at exact physical coordinates (logical == physical). All handoff
geometry was authored against JS Math.round — use `js_round`, never round().

Every handoff hires-text `y` is a VISUAL CAP-TOP y (the design engine crops
its text masks to visible ink — see design/led-engine-bundle.js
`rasterize()`); convert through `cap_top` before calling `hires()`.
"""

import math

from led_ticker.plugin import (
    Color,
    ScaledCanvas,
    draw_text,
    make_color,
    measure_width,
    resolve_font,
    unwrap_to_real,
)

from led_ticker_weather.palette import LABEL, RGB

# Thin Inter strokes drop out at the default 128 threshold on small sizes;
# 80 is the documented thin-font value (core CLAUDE.md `font_threshold`).
_HIRES_THRESHOLD = 80


def js_round(v: float) -> int:
    """JS Math.round semantics: half-up (floor(v + 0.5))."""
    return math.floor(v + 0.5)


def cap_top(y_target: int, size: int) -> int:
    """dc.html visual-cap-top y -> `hires()`'s ascent-box-top y (the
    baseball `_paint.cap_top` formula, hardware-validated there)."""
    return y_target - size + js_round(size * 0.72)


def phys_wrap(canvas):
    real = unwrap_to_real(canvas)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


def dim(rgb: RGB, bright: float = 1.0) -> Color:
    r, g, b = rgb
    return make_color(int(r * bright), int(g * bright), int(b * bright))


def px(real, x: int, y: int, rgb: RGB, bright: float = 1.0) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        r, g, b = rgb
        real.SetPixel(x, y, int(r * bright), int(g * bright), int(b * bright))


def hires(
    shim, text: str, x: int, y_top: int, rgb: RGB, size: int, *, bold: bool = True
) -> int:
    """Paint Inter text at physical (x, y_top); return ADVANCE width in
    physical px (call sites do `x += hires(...) + gap`, so returning
    draw_text's absolute end-x would double-count)."""
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return draw_text(shim, font, text, x, y_top + font.ascent, dim(rgb)) - x


class _ScaleOneProbe:
    """`measure_width(canvas=None)` falls back to SCALE_FALLBACK=4; this
    probe pins the measurement to scale 1 (physical px) instead."""

    scale = 1


_PROBE = _ScaleOneProbe()


def text_width(size: int, text: str, *, bold: bool = True) -> int:
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return measure_width(font, text, _PROBE)


def fit_text(text: str, max_w: int, size: int, *, bold: bool = True) -> str:
    """Handoff `fitText`: ellipsis-truncate until the text fits `max_w`."""
    if text_width(size, text, bold=bold) <= max_w:
        return text
    s = text
    while len(s) > 1 and text_width(size, s.rstrip() + "…", bold=bold) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def vdivider(real, x: int, y0: int, y1: int) -> None:
    """Dotted vertical rule (handoff `vdivider`: LABEL at 0.4, every 3rd row)."""
    for y in range(y0, y1, 3):
        px(real, x, y, LABEL, 0.4)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_paint.py -q`
Expected: PASS. Then full suite: `uv run pytest plugins/weather -q` — all green (import-purity picks up the new modules automatically).

- [ ] **Step 7: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/palette.py plugins/weather/src/led_ticker_weather/paint.py plugins/weather/tests/test_paint.py plugins/weather/tests/conftest.py
git commit -m "feat(weather): palette + physical paint helpers for forecast layouts"
```

---

### Task 2: `blit_emoji_scaled` — integer-scaled lowres emoji blits

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/paint.py`
- Test: `plugins/weather/tests/test_paint.py` (append)

**Interfaces:**
- Produces: `paint.blit_emoji_scaled(real, slug: str, x: int, y: int, k: int) -> None` — stamps the curated 8×8 lowres sprite at physical (x, y), each sprite pixel as a k×k block. Bounds-clipped. Sprite readback cached per slug.

- [ ] **Step 1: Write failing tests**

Append to `plugins/weather/tests/test_paint.py`:

```python
class TestBlitEmojiScaled:
    def test_k1_matches_direct_draw(self, lit):
        from led_ticker.plugin import HeadlessBackend, draw_emoji_at

        direct = HeadlessBackend(16, 8).create_canvas()
        draw_emoji_at(direct, "sun", 0, 0)
        blitted = HeadlessBackend(16, 8).create_canvas()
        paint.blit_emoji_scaled(blitted, "sun", 0, 0, 1)
        for y in range(8):
            for x in range(8):
                assert blitted.get_pixel(x, y) == direct.get_pixel(x, y)

    def test_k2_expands_each_pixel_to_2x2(self):
        from led_ticker.plugin import HeadlessBackend

        one = HeadlessBackend(16, 8).create_canvas()
        paint.blit_emoji_scaled(one, "rain", 0, 0, 1)
        two = HeadlessBackend(32, 16).create_canvas()
        paint.blit_emoji_scaled(two, "rain", 0, 0, 2)
        for y in range(8):
            for x in range(8):
                p = one.get_pixel(x, y)
                for j in range(2):
                    for i in range(2):
                        assert two.get_pixel(x * 2 + i, y * 2 + j) == p

    def test_offset_and_bounds_clip(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(20, 20).create_canvas()
        # 8*3=24 wide from x=10 overflows a 20-wide canvas: must not raise
        paint.blit_emoji_scaled(real, "sun", 10, 10, 3)
        assert real.count_nonzero() > 0

    def test_every_curated_weather_slug_blits(self):
        from led_ticker.plugin import HeadlessBackend

        for slug in ("sun", "moon", "cloud", "partly_cloudy", "rain", "snow",
                     "thunder", "fog"):
            real = HeadlessBackend(16, 8).create_canvas()
            paint.blit_emoji_scaled(real, slug, 0, 0, 1)
            assert real.count_nonzero() > 0, slug
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_paint.py::TestBlitEmojiScaled -q`
Expected: FAIL — `AttributeError: ... no attribute 'blit_emoji_scaled'`.

- [ ] **Step 3: Implement**

Append to `plugins/weather/src/led_ticker_weather/paint.py` (add `functools` to the stdlib imports and `HeadlessBackend, draw_emoji_at` to the `led_ticker.plugin` import):

```python
# 8x8 lowres sprite box (curated weather emoji are all 8x8).
_SPRITE_BOX = 8


@functools.lru_cache(maxsize=32)
def _emoji_pixels(slug: str) -> tuple[tuple[int, int, int, int, int], ...]:
    """Lit (dx, dy, r, g, b) offsets of a curated lowres sprite.

    Offscreen-rasterize the 8x8 through the PUBLIC surface (`draw_emoji_at`
    on a throwaway `HeadlessBackend` canvas) and read back via `get_pixel`
    — the one documented supported readback (baseball `_mask.py`
    precedent). Cached: the scan runs once per slug per process.
    """
    real = HeadlessBackend(_SPRITE_BOX * 2, _SPRITE_BOX).create_canvas()
    draw_emoji_at(real, slug, 0, 0)
    out = []
    for dy in range(_SPRITE_BOX):
        for dx in range(_SPRITE_BOX):
            r, g, b = real.get_pixel(dx, dy)
            if (r, g, b) != (0, 0, 0):
                out.append((dx, dy, r, g, b))
    return tuple(out)


def blit_emoji_scaled(real, slug: str, x: int, y: int, k: int) -> None:
    """Stamp the curated lowres sprite at physical (x, y), each sprite
    pixel expanded to a k x k block (the strip-icon sizes: k=2 bigsign,
    k=3 longboi). Bounds-clipped per pixel."""
    for dx, dy, r, g, b in _emoji_pixels(slug):
        bx, by = x + dx * k, y + dy * k
        for j in range(k):
            for i in range(k):
                xx, yy = bx + i, by + j
                if 0 <= xx < real.width and 0 <= yy < real.height:
                    real.SetPixel(xx, yy, r, g, b)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_paint.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/paint.py plugins/weather/tests/test_paint.py
git commit -m "feat(weather): integer-scaled lowres emoji blit for strip icons"
```

---

### Task 3: `cond_kind` + kind→slug tables

**Files:**
- Create: `plugins/weather/src/led_ticker_weather/forecast_data.py`
- Test: `plugins/weather/tests/test_forecast_data.py`

**Interfaces:**
- Produces: `cond_kind(code: int, is_day: int) -> str` — one of `sunny, clear, partly, partly_night, cloudy, overcast, rain, rain_patchy, thunder, snow, fog`.
- Produces: `KIND_SLUGS: dict[str, tuple[str, str]]` — kind → `(lowres_slug, hero_hires_slug)`.

- [ ] **Step 1: Write failing tests**

Create `plugins/weather/tests/test_forecast_data.py`:

```python
"""forecast_data: condition-code mapping + slug tables (+ later: models,
parsing, demo data)."""

import pytest

from led_ticker_weather.forecast_data import KIND_SLUGS, cond_kind


class TestCondKind:
    """Per-code-band tripwires for the handoff condKind table
    (design/README.md Data Sources section)."""

    @pytest.mark.parametrize(
        ("code", "is_day", "kind"),
        [
            (1000, 1, "sunny"),
            (1000, 0, "clear"),
            (1003, 1, "partly"),
            (1003, 0, "partly_night"),
            (1006, 1, "cloudy"),
            (1006, 0, "cloudy"),  # night swap only applies to 1000/1003
            (1009, 1, "overcast"),
            (1030, 1, "fog"),
            (1135, 1, "fog"),
            (1147, 1, "fog"),
            (1063, 1, "rain_patchy"),  # patchy rain possible
            (1150, 1, "rain_patchy"),  # patchy light drizzle
            (1183, 1, "rain_patchy"),  # light rain
            (1240, 1, "rain_patchy"),  # light rain shower
            (1186, 1, "rain"),  # moderate rain at times
            (1201, 1, "rain"),  # heavy freezing rain
            (1243, 1, "rain"),  # moderate/heavy rain shower
            (1246, 1, "rain"),  # torrential rain shower
            (1066, 1, "snow"),
            (1114, 1, "snow"),
            (1210, 1, "snow"),
            (1225, 1, "snow"),
            (1255, 1, "snow"),
            (1258, 1, "snow"),
            (1087, 1, "thunder"),
            (1273, 1, "thunder"),
            (1282, 1, "thunder"),
            (9999, 1, "cloudy"),  # unknown code -> handoff drawIcon default
        ],
    )
    def test_code_band(self, code, is_day, kind):
        assert cond_kind(code, is_day) == kind


class TestKindSlugs:
    def test_every_kind_has_an_entry(self):
        kinds = {
            "sunny", "clear", "partly", "partly_night", "cloudy",
            "overcast", "rain", "rain_patchy", "thunder", "snow", "fog",
        }
        assert set(KIND_SLUGS) == kinds

    def test_lowres_slugs_exist_in_both_curated_registries(self):
        # Strip icons blit the lowres sprite; heroes may fall back to it.
        from led_ticker import pixel_emoji

        lowres = pixel_emoji._get_registry()
        for kind, (lo, _) in KIND_SLUGS.items():
            assert lo in lowres, f"{kind}: lowres {lo!r} missing"
            assert lo in pixel_emoji.HIRES_REGISTRY, f"{kind}: {lo!r} no hires pair"

    def test_pack_hires_slugs_resolve(self):
        # overcast / rain_patchy upgrade to pack sprites in the hero.
        from led_ticker import emoji_pack, pixel_emoji

        for kind, (_, hi) in KIND_SLUGS.items():
            in_curated = hi in pixel_emoji.HIRES_REGISTRY
            assert in_curated or emoji_pack.has_slug(hi), (
                f"{kind}: hires {hi!r} in neither curated registry nor pack"
            )

    def test_pack_upgrades_are_where_the_spec_says(self):
        assert KIND_SLUGS["overcast"] == ("cloud", "sun_behind_large_cloud")
        assert KIND_SLUGS["rain_patchy"] == ("rain", "sun_behind_rain_cloud")
        assert KIND_SLUGS["partly_night"] == ("partly_cloudy", "moon")
```

Note: `test_lowres_slugs_exist...`/`test_pack_hires_slugs_resolve` intentionally
reach into `led_ticker.pixel_emoji`/`led_ticker.emoji_pack` — TEST-side registry
introspection, the same pattern the existing `test_weather.py` uses. The
import-purity AST scan covers `src/` only; do NOT add these imports to source
modules.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_forecast_data.py -q`
Expected: FAIL — `No module named 'led_ticker_weather.forecast_data'`.

- [ ] **Step 3: Implement**

Create `plugins/weather/src/led_ticker_weather/forecast_data.py`:

```python
"""Forecast data layer: WeatherAPI /v1/forecast.json fetch, condition-code
-> kind mapping (handoff condKind, ported verbatim), kind -> emoji-slug
tables, and the parsed models the renderers consume.

Icon language (spec divergence 1): kinds resolve to PACKAGED emoji — the
curated 8x8/32x32 weather pairs everywhere, upgraded to standard-pack
sprites for two hero-only distinctions (overcast, patchy rain) that the
curated set can't draw. Strips always use the lowres column.
"""

# WeatherAPI condition codes, from the handoff table (design/README.md):
#   1000 sunny/clear · 1003 partly · 1006 cloudy · 1009 overcast ·
#   1030/1135/1147 fog · 1063/1150-1201/1240-1246 rain ·
#   1066/1114/1210-1225/1255-1258 snow · 1087/1273-1282 thunder.
# The patchy/solid rain split (spec Icons table) refines the rain band:
# patchy = 1063, 1150-1183, 1240; solid = 1186-1201, 1243-1246.
_FOG_CODES = frozenset({1030, 1135, 1147})
_SNOW_SINGLES = frozenset({1066, 1114})
_PATCHY_RAIN_SINGLES = frozenset({1063, 1240})


def cond_kind(code: int, is_day: int) -> str:
    """Map a WeatherAPI condition code (+ is_day) to a glyph kind."""
    if code == 1000:
        return "sunny" if is_day else "clear"
    if code == 1003:
        return "partly" if is_day else "partly_night"
    if code == 1006:
        return "cloudy"
    if code == 1009:
        return "overcast"
    if code in _FOG_CODES:
        return "fog"
    if code == 1087 or 1273 <= code <= 1282:
        return "thunder"
    if code in _SNOW_SINGLES or 1210 <= code <= 1225 or 1255 <= code <= 1258:
        return "snow"
    if code in _PATCHY_RAIN_SINGLES or 1150 <= code <= 1183:
        return "rain_patchy"
    if 1186 <= code <= 1201 or 1243 <= code <= 1246:
        return "rain"
    return "cloudy"  # unknown -> handoff drawIcon default (plain cloud)


# kind -> (lowres_slug, hero_hires_slug). Lowres column: curated 8x8
# sprites only (strips + smallsign — must render on every sign). Hires
# column: what the HERO slot draws at scale > 1; two entries upgrade to
# standard-pack sprites (hires-only, fine in the hero, never in strips).
KIND_SLUGS: dict[str, tuple[str, str]] = {
    "sunny": ("sun", "sun"),
    "clear": ("moon", "moon"),
    "partly": ("partly_cloudy", "partly_cloudy"),
    "partly_night": ("partly_cloudy", "moon"),
    "cloudy": ("cloud", "cloud"),
    "overcast": ("cloud", "sun_behind_large_cloud"),
    "rain": ("rain", "rain"),
    "rain_patchy": ("rain", "sun_behind_rain_cloud"),
    "thunder": ("thunder", "thunder"),
    "snow": ("snow", "snow"),
    "fog": ("fog", "fog"),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_forecast_data.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_data.py plugins/weather/tests/test_forecast_data.py
git commit -m "feat(weather): condition-code kind mapping + emoji slug tables"
```

---

### Task 4: Models, payload parsing, demo data, fetch, unit conversion

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast_data.py`
- Test: `plugins/weather/tests/test_forecast_data.py` (append)

**Interfaces:**
- Produces: `DayForecast(label, kind, hi_f, lo_f, pop)` and `CurrentConditions(temp_f, feels_f, kind, hi_f, lo_f)` (attrs frozen), `ForecastData(location, current, days: tuple[DayForecast, ...])`.
- Produces: `parse_forecast_payload(payload: dict) -> ForecastData`.
- Produces: `display_temp(f: float, units: str) -> int` (handoff `TF`, js_round).
- Produces: `async fetch_forecast(session, location) -> dict` (raw payload; ValueError on missing key / API error).
- Produces: `DEMO_DATA: ForecastData` (the handoff's fixed BOSTON week).

- [ ] **Step 1: Write failing tests**

Append to `plugins/weather/tests/test_forecast_data.py`:

```python
def _payload(n_days=7):
    """Minimal /v1/forecast.json shape (fields per design/README.md)."""
    fd = [
        {
            "date": "2026-07-21",  # a Tuesday
            "day": {
                "maxtemp_f": 86.0,
                "mintemp_f": 66.0,
                "daily_chance_of_rain": 0,
                "condition": {"code": 1000},
            },
        }
    ]
    for i in range(1, n_days):
        fd.append(
            {
                "date": f"2026-07-{21 + i}",
                "day": {
                    "maxtemp_f": 80.0 + i,
                    "mintemp_f": 60.0 + i,
                    "daily_chance_of_rain": 10 * i,
                    "condition": {"code": 1063},
                },
            }
        )
    return {
        "location": {"name": "Boston"},
        "current": {
            "temp_f": 78.0,
            "feelslike_f": 80.0,
            "is_day": 1,
            "condition": {"code": 1003},
        },
        "forecast": {"forecastday": fd},
    }


class TestParseForecastPayload:
    def test_current_merges_today_hi_lo(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        data = parse_forecast_payload(_payload())
        assert data.location == "Boston"
        assert data.current.temp_f == 78.0
        assert data.current.feels_f == 80.0
        assert data.current.kind == "partly"
        assert data.current.hi_f == 86.0  # forecastday[0]
        assert data.current.lo_f == 66.0

    def test_days_are_tomorrow_onward(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        data = parse_forecast_payload(_payload())
        assert len(data.days) == 6  # forecastday[1:]
        assert data.days[0].label == "WED"  # 2026-07-22
        assert data.days[0].kind == "rain_patchy"
        assert data.days[0].pop == 10

    def test_day_kind_always_resolves_as_day(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        p = _payload()
        p["forecast"]["forecastday"][1]["day"]["condition"]["code"] = 1000
        data = parse_forecast_payload(p)
        assert data.days[0].kind == "sunny"  # never "clear"

    def test_short_feed_parses_short(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        data = parse_forecast_payload(_payload(n_days=3))
        assert len(data.days) == 2

    def test_night_current_swaps_kind(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        p = _payload()
        p["current"]["is_day"] = 0
        assert parse_forecast_payload(p).current.kind == "partly_night"


class TestDisplayTemp:
    def test_imperial_rounds(self):
        from led_ticker_weather.forecast_data import display_temp

        assert display_temp(78.4, "imperial") == 78
        assert display_temp(78.5, "imperial") == 79  # js_round half-up

    def test_metric_converts(self):
        from led_ticker_weather.forecast_data import display_temp

        assert display_temp(78.0, "metric") == 26  # (78-32)*5/9 = 25.6


class TestDemoData:
    def test_demo_is_the_handoff_boston_week(self):
        from led_ticker_weather.forecast_data import DEMO_DATA

        assert DEMO_DATA.location == "BOSTON"
        assert DEMO_DATA.current.temp_f == 78
        assert DEMO_DATA.current.kind == "partly"
        assert [d.label for d in DEMO_DATA.days] == [
            "TUE", "WED", "THU", "FRI", "SAT", "SUN",
        ]
        assert DEMO_DATA.days[1].kind == "thunder"
        assert DEMO_DATA.days[2].pop == 80


class TestFetchForecast:
    async def test_missing_key_raises(self, monkeypatch):
        from led_ticker_weather.forecast_data import fetch_forecast

        monkeypatch.delenv("WEATHERAPI_KEY", raising=False)
        with pytest.raises(ValueError, match="WEATHERAPI_KEY"):
            await fetch_forecast(None, "Boston")

    async def test_api_error_payload_raises(self, monkeypatch):
        import unittest.mock as mock

        from led_ticker_weather.forecast_data import fetch_forecast

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        resp = mock.MagicMock()
        resp.json = mock.AsyncMock(
            return_value={"error": {"code": 2008, "message": "disabled"}}
        )
        session = mock.MagicMock()
        session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
        session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        with pytest.raises(ValueError, match="2008"):
            await fetch_forecast(session, "Boston")

    async def test_requests_seven_days(self, monkeypatch):
        import unittest.mock as mock

        from led_ticker_weather.forecast_data import fetch_forecast

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        resp = mock.MagicMock()
        resp.json = mock.AsyncMock(return_value=_payload())
        session = mock.MagicMock()
        session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
        session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        await fetch_forecast(session, "Boston")
        params = session.get.call_args.kwargs["params"]
        assert params["days"] == 7
        assert params["q"] == "Boston"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_forecast_data.py -q`
Expected: the new classes FAIL with ImportError (existing TestCondKind/TestKindSlugs still pass).

- [ ] **Step 3: Implement**

Append to `plugins/weather/src/led_ticker_weather/forecast_data.py` (new imports at top: `import datetime`, `import os`, `import aiohttp`, `import attrs`, and `from led_ticker_weather.paint import js_round`):

```python
FORECAST_URL: str = "https://api.weatherapi.com/v1/forecast.json"

# Always request the deepest strip any layout wants (longboi: today + 6).
# Free-tier keys return fewer days; parsing and the renderers degrade
# (spec: Data — degrade on short feed).
_REQUEST_DAYS = 7


@attrs.frozen
class DayForecast:
    label: str  # weekday abbrev ("TUE")
    kind: str  # cond_kind() output
    hi_f: float
    lo_f: float
    pop: int  # daily_chance_of_rain, 0-100


@attrs.frozen
class CurrentConditions:
    temp_f: float
    feels_f: float
    kind: str
    hi_f: float  # today's forecast hi (forecastday[0])
    lo_f: float


@attrs.frozen
class ForecastData:
    location: str
    current: CurrentConditions
    days: tuple[DayForecast, ...]  # tomorrow onward (forecastday[1:])


def display_temp(f: float, units: str) -> int:
    """Handoff `TF()`: whole degrees, js_round; metric converts from F."""
    if units == "metric":
        return js_round((f - 32) * 5 / 9)
    return js_round(f)


def _day_label(date_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    return d.strftime("%a").upper()[:3]


def parse_forecast_payload(payload: dict) -> ForecastData:
    """Field mapping per design/README.md Data Sources (inlined in the
    .dc.html above its data block)."""
    cur = payload["current"]
    fdays = payload["forecast"]["forecastday"]
    today = fdays[0]["day"]
    current = CurrentConditions(
        temp_f=cur["temp_f"],
        feels_f=cur["feelslike_f"],
        kind=cond_kind(cur["condition"]["code"], cur["is_day"]),
        hi_f=today["maxtemp_f"],
        lo_f=today["mintemp_f"],
    )
    days = tuple(
        DayForecast(
            label=_day_label(fd["date"]),
            kind=cond_kind(fd["day"]["condition"]["code"], 1),
            hi_f=fd["day"]["maxtemp_f"],
            lo_f=fd["day"]["mintemp_f"],
            pop=int(fd["day"]["daily_chance_of_rain"]),
        )
        for fd in fdays[1:]
    )
    return ForecastData(location=payload["location"]["name"], current=current, days=days)


async def fetch_forecast(session: aiohttp.ClientSession | None, location: str) -> dict:
    """GET /v1/forecast.json and return the raw payload dict. Reads
    WEATHERAPI_KEY from env; raises ValueError on a missing key or an API
    error (same convention as weather.py's fetch_current). `session` is
    the ENGINE'S SHARED session when run by core (never close it; timeout
    is per-request); None (tests, direct use) opens a short-lived one.
    """
    api_key = os.getenv("WEATHERAPI_KEY", "")
    if not api_key:
        raise ValueError("WEATHERAPI_KEY not set. Add it to your .env file.")
    params = {
        "key": api_key,
        "q": location,
        "days": _REQUEST_DAYS,
        "aqi": "no",
        "alerts": "no",
    }
    timeout = aiohttp.ClientTimeout(total=10)
    if session is None:
        async with aiohttp.ClientSession() as own:
            async with own.get(FORECAST_URL, params=params, timeout=timeout) as resp:
                data = await resp.json()
    else:
        async with session.get(FORECAST_URL, params=params, timeout=timeout) as resp:
            data = await resp.json()
    if "error" in data:
        code = data["error"].get("code", "?")
        msg = data["error"].get("message", "Unknown error")
        raise ValueError(f"WeatherAPI error {code}: {msg}")
    return data


# The handoff's fixed sample week (design .dc.html CUR/FC data block),
# used by demo = true and the layout tests. Fictional placeholder data.
DEMO_DATA: ForecastData = ForecastData(
    location="BOSTON",
    current=CurrentConditions(temp_f=78, feels_f=80, kind="partly", hi_f=82, lo_f=64),
    days=(
        DayForecast(label="TUE", kind="sunny", hi_f=86, lo_f=66, pop=0),
        DayForecast(label="WED", kind="thunder", hi_f=79, lo_f=68, pop=60),
        DayForecast(label="THU", kind="rain", hi_f=74, lo_f=65, pop=80),
        DayForecast(label="FRI", kind="cloudy", hi_f=77, lo_f=63, pop=30),
        DayForecast(label="SAT", kind="sunny", hi_f=83, lo_f=62, pop=5),
        DayForecast(label="SUN", kind="partly", hi_f=85, lo_f=64, pop=15),
    ),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_forecast_data.py -q`
Expected: PASS (async tests run under the repo's `asyncio_mode = "auto"`).

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_data.py plugins/weather/tests/test_forecast_data.py
git commit -m "feat(weather): forecast models, payload parsing, fetch, demo week"
```

---

### Task 5: `resolve_forecast_layout`

**Files:**
- Create: `plugins/weather/src/led_ticker_weather/forecast.py` (resolver only; widget lands in Task 9)
- Test: `plugins/weather/tests/test_resolve_forecast_layout.py`

**Interfaces:**
- Produces: `VALID_LAYOUTS: tuple[str, ...] = ("auto", "strip", "big", "long")`, `resolve_forecast_layout(cfg_layout: str, scale: int, phys_w: int) -> str`.

- [ ] **Step 1: Write failing tests**

Create `plugins/weather/tests/test_resolve_forecast_layout.py`:

```python
import pytest

from led_ticker_weather.forecast import VALID_LAYOUTS, resolve_forecast_layout


class TestResolveForecastLayout:
    @pytest.mark.parametrize(
        ("cfg", "scale", "phys_w", "expect"),
        [
            # scale 1: always strip, whatever the config asked for
            ("auto", 1, 160, "strip"),
            ("big", 1, 160, "strip"),
            ("long", 1, 160, "strip"),
            ("strip", 1, 160, "strip"),
            # auto at scale > 1 splits on the 400px physical-width threshold
            ("auto", 4, 256, "big"),
            ("auto", 4, 512, "long"),
            ("auto", 4, 400, "long"),  # boundary: >= 400 is wide
            # explicit names honored at scale > 1 ...
            ("big", 4, 512, "big"),
            ("strip", 4, 256, "strip"),  # logical-coord draw works anywhere
            ("long", 4, 512, "long"),
            # ... with ONE width-fit degrade (baseball Finding-3 pattern):
            # explicit long on a narrow panel would draw mostly off-panel
            ("long", 4, 256, "big"),
        ],
    )
    def test_table(self, cfg, scale, phys_w, expect):
        assert resolve_forecast_layout(cfg, scale, phys_w) == expect

    def test_valid_layouts_constant(self):
        assert VALID_LAYOUTS == ("auto", "strip", "big", "long")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_resolve_forecast_layout.py -q`
Expected: FAIL — `No module named 'led_ticker_weather.forecast'`.

- [ ] **Step 3: Implement**

Create `plugins/weather/src/led_ticker_weather/forecast.py`:

```python
"""weather.forecast — held multi-day forecast card with per-sign layouts.

`resolve_forecast_layout` is stateless and runs fresh on every draw tick
(flight pattern) so hot-reloads and canvas swaps always re-resolve. The
400px physical-width threshold splits bigsign (256 -> "big") from longboi
(512 -> "long"), the same convention as baseball/flight/stocks.
"""

VALID_LAYOUTS: tuple[str, ...] = ("auto", "strip", "big", "long")

_WIDE_MIN_W = 400


def resolve_forecast_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if scale <= 1:
        return "strip"  # hi-res layouts are impossible on a scale-1 sign
    if cfg_layout == "long" and phys_w < _WIDE_MIN_W:
        # Width-fit degrade: render_hero_long hardcodes anchors out to
        # x~506; on a 256px panel it would draw mostly off-panel — land on
        # what "auto" would already pick there instead.
        return "big"
    if cfg_layout != "auto":
        return cfg_layout
    return "big" if phys_w < _WIDE_MIN_W else "long"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_resolve_forecast_layout.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast.py plugins/weather/tests/test_resolve_forecast_layout.py
git commit -m "feat(weather): forecast layout resolver with width-fit degrade"
```

---

### Task 6: `render_strip_small` (smallsign, BDF)

**Files:**
- Create: `plugins/weather/src/led_ticker_weather/forecast_layouts.py`
- Test: `plugins/weather/tests/test_forecast_layouts.py`

**Interfaces:**
- Consumes: `ForecastData`/`display_temp`/`KIND_SLUGS` (Task 3/4), `paint.dim` (Task 1).
- Produces: `render_strip_small(canvas, data: ForecastData, units: str, *, y_offset: int = 0) -> None`. Draws in LOGICAL coords (works on plain canvas and through a wrapper).

- [ ] **Step 1: Write failing tests**

Create `plugins/weather/tests/test_forecast_layouts.py`:

```python
"""Per-sign forecast renderers. Hires text is asserted shape-level only
(never exact-pinned — freetype varies across platforms); lowres emoji
blits and dotted dividers are exact SetPixel math and may be pinned."""

from led_ticker_weather.forecast_data import DEMO_DATA
from led_ticker_weather.forecast_layouts import render_strip_small


def _colors(real, x0, y0, x1, y1):
    return {
        real.get_pixel(x, y)
        for y in range(y0, y1)
        for x in range(x0, x1)
        if real.get_pixel(x, y) != (0, 0, 0)
    }


class TestRenderStripSmall:
    def test_three_columns_of_content(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        for i in range(3):
            x0 = 2 + i * 53
            assert _colors(smallsign, x0, 0, x0 + 50, 16), f"column {i} empty"

    def test_day_labels_amber_top_band(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        # label band (rows 0-7) carries amber text right of the icon
        assert (255, 180, 0) in _colors(smallsign, 19, 0, 55, 8)

    def test_hi_lo_white_bottom_band(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        assert (255, 255, 255) in _colors(smallsign, 19, 8, 55, 16)

    def test_icon_in_left_slot(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        # today = partly -> partly_cloudy lowres sprite in rows 4-12
        assert _colors(smallsign, 2, 4, 16, 12)

    def test_dotted_separators_between_columns(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        for i in range(2):
            sep_x = 2 + i * 53 + 53 - 3
            pts = [
                y for y in range(16)
                if smallsign.get_pixel(sep_x, y) != (0, 0, 0)
            ]
            assert pts == list(range(2, 14, 2)), f"separator {i}"

    def test_degrades_below_three_columns_on_short_feed(self, smallsign):
        import attrs

        short = attrs.evolve(DEMO_DATA, days=DEMO_DATA.days[:1])
        render_strip_small(smallsign, short, "imperial")
        # columns 0-1 drawn, column 2 empty
        assert _colors(smallsign, 2, 0, 55, 16)
        assert not _colors(smallsign, 110, 0, 158, 16)

    def test_y_offset_shifts_content_down(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial", y_offset=4)
        assert not _colors(smallsign, 0, 0, 160, 4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_forecast_layouts.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `plugins/weather/src/led_ticker_weather/forecast_layouts.py`:

```python
"""The three per-sign forecast renderers, ported from the handoff draw
functions (design/Weather Forecast.dc.html: weatherSmall / weatherBig /
weatherLong). Coordinates and sizes are handoff-normative; icons diverge
to packaged emoji (spec divergence 1: boxes snap to sprite sizes).
"""

from led_ticker.plugin import FONT_SMALL, draw_emoji_at, draw_text

from led_ticker_weather.forecast_data import (
    DayForecast,
    ForecastData,
    KIND_SLUGS,
    display_temp,
)
from led_ticker_weather.paint import dim
from led_ticker_weather.palette import AMBER, IDENT, LABEL

# --- smallsign (160x16, BDF, logical coords) — handoff weatherSmall ---

_SMALL_CW = 53  # column width
_SMALL_X0 = 2
_SMALL_TEXT_DX = 17  # text block starts right of the icon slot
# FONT_SMALL is 5x8 (nearest bundled BDF to the handoff's px7 Silkscreen —
# documented divergence 2): two 8-row bands stack exactly in 16 rows.
_SMALL_LABEL_BASELINE = 7
_SMALL_TEMP_BASELINE = 15
_SMALL_ICON_Y = 4  # centers the 8x8 sprite vertically


def render_strip_small(
    canvas, data: ForecastData, units: str, *, y_offset: int = 0
) -> None:
    """Today + next two days: icon | day label / hi-lo, dotted separators."""
    cur = data.current
    cells: list[tuple[str, DayForecast | None]] = [("TDY", None)]
    for d in data.days[:2]:
        cells.append((d.label, d))
    for i, (label, day) in enumerate(cells):
        x = _SMALL_X0 + i * _SMALL_CW
        kind = cur.kind if day is None else day.kind
        hi_f = cur.hi_f if day is None else day.hi_f
        lo_f = cur.lo_f if day is None else day.lo_f
        lowres, _ = KIND_SLUGS[kind]
        draw_emoji_at(canvas, lowres, x + 3, _SMALL_ICON_Y + y_offset)
        tx = x + _SMALL_TEXT_DX
        draw_text(
            canvas, FONT_SMALL, label, tx, _SMALL_LABEL_BASELINE + y_offset,
            dim(AMBER),
        )
        temps = f"{display_temp(hi_f, units)}/{display_temp(lo_f, units)}"
        draw_text(
            canvas, FONT_SMALL, temps, tx, _SMALL_TEMP_BASELINE + y_offset,
            dim(IDENT),
        )
        if i < len(cells) - 1:
            sep_x = x + _SMALL_CW - 3
            for yy in range(2, 14, 2):
                canvas.SetPixel(
                    sep_x, yy + y_offset,
                    int(LABEL[0] * 0.3), int(LABEL[1] * 0.3), int(LABEL[2] * 0.3),
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_forecast_layouts.py -q`
Expected: PASS. If the amber/white band assertions fail on baseline placement, adjust `_SMALL_LABEL_BASELINE`/`_SMALL_TEMP_BASELINE` by ±1 so the two 5x8 rows sit in rows 0-7 / 8-15 — the bands, not the exact baselines, are the contract.

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_layouts.py plugins/weather/tests/test_forecast_layouts.py
git commit -m "feat(weather): smallsign 3-day forecast strip renderer"
```

---

### Task 7: Shared strip cell + geometry tables

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast_layouts.py`
- Test: `plugins/weather/tests/test_forecast_layouts.py` (append)

**Interfaces:**
- Produces: `StripGeo` (attrs frozen: `day_y, day_px, icon_k, icon_y, temp_y, temp_px, stack, line_h=0, pop_y=None, pop_px=9`), `_BIG_GEO`, `_LONG_GEO` constants, and `_strip_cell(shim, real, x: float, w: float, day: DayForecast, geo: StripGeo, units: str, oy: int) -> None` (`oy` = physical y offset for PushUp/Down).
- Produces internal text helpers reused by the heroes: `_ctext(shim, text, x, w, y_target, rgb, size, oy, *, bold=True)` (centered, cap-top y), `_center_segs(shim, segs, x, w, y_target, size, oy)`, `_temp_segs(hi_f, lo_f, units, *, degree) -> list[tuple[str, RGB]]`.

- [ ] **Step 1: Write failing tests**

Append to `plugins/weather/tests/test_forecast_layouts.py`:

```python
class TestStripCell:
    def _cell(self, real, geo, day=None):
        from led_ticker_weather.forecast_data import DayForecast
        from led_ticker_weather.forecast_layouts import _strip_cell
        from led_ticker_weather.paint import phys_wrap

        shim, unwrapped = phys_wrap(real)
        d = day or DayForecast(label="WED", kind="thunder", hi_f=79, lo_f=68, pop=60)
        _strip_cell(shim, unwrapped, 10.0, 33.5, d, geo, "imperial", 0)
        return unwrapped

    def test_big_geo_stacks_temps(self, bigsign, lit):
        from led_ticker_weather.forecast_layouts import _BIG_GEO
        from led_ticker.plugin import unwrap_to_real

        real = self._cell(unwrap_to_real(bigsign), _BIG_GEO)
        # warm hi in the tempY band, cool lo one line below (stacked)
        hi_band = {p for _, _, p in lit(real, 10, 37, 44, 49)}
        lo_band = {p for _, _, p in lit(real, 10, 49, 44, 61)}
        assert any(r > b for r, _, b in hi_band)  # warm-ish ink present
        assert any(b > r for r, _, b in lo_band)  # cool-ish ink present

    def test_big_geo_icon_is_16px_lowres_blit(self, bigsign, lit):
        from led_ticker_weather.forecast_layouts import _BIG_GEO
        from led_ticker.plugin import unwrap_to_real

        real = self._cell(unwrap_to_real(bigsign), _BIG_GEO)
        pts = lit(real, 10, _BIG_GEO.icon_y, 44, _BIG_GEO.icon_y + 16)
        assert pts  # icon ink in the 16px slot
        assert not lit(real, 10, _BIG_GEO.icon_y + 16, 44, 37)  # none below it

    def test_long_geo_horizontal_temps_and_pop(self, longboi, lit):
        from led_ticker_weather.forecast_layouts import _LONG_GEO
        from led_ticker.plugin import unwrap_to_real

        real = self._cell(unwrap_to_real(longboi), _LONG_GEO)
        assert lit(real, 10, _LONG_GEO.temp_y, 44, _LONG_GEO.temp_y + 12)
        # pop >= 50 renders cyan-ish (0,200,255): green+blue, no red
        pop_ink = {p for _, _, p in lit(real, 10, 52, 44, 62)}
        assert any(r == 0 and b > 0 for r, g, b in pop_ink)

    def test_long_geo_low_pop_is_dim_label(self, longboi, lit):
        from led_ticker_weather.forecast_data import DayForecast
        from led_ticker_weather.forecast_layouts import _LONG_GEO
        from led_ticker.plugin import unwrap_to_real

        d = DayForecast(label="SAT", kind="sunny", hi_f=83, lo_f=62, pop=5)
        real = self._cell(unwrap_to_real(longboi), _LONG_GEO, day=d)
        pop_ink = {p for _, _, p in lit(real, 10, 52, 44, 62)}
        assert pop_ink
        assert all(b >= g >= r for r, g, b in pop_ink)  # LABEL 70,90,130 ramp

    def test_day_label_amber_in_top_band(self, bigsign, lit):
        from led_ticker_weather.forecast_layouts import _BIG_GEO
        from led_ticker.plugin import unwrap_to_real

        real = self._cell(unwrap_to_real(bigsign), _BIG_GEO)
        ink = {p for _, _, p in lit(real, 10, 0, 44, 13)}
        assert any(r > 200 and g > 100 and b == 0 for r, g, b in ink)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_forecast_layouts.py::TestStripCell -q`
Expected: FAIL — `_strip_cell`/`_BIG_GEO` not defined.

- [ ] **Step 3: Implement**

Append to `plugins/weather/src/led_ticker_weather/forecast_layouts.py` (extend imports: `import attrs`; from `led_ticker_weather.paint` also `blit_emoji_scaled, cap_top, hires, js_round, text_width`; from palette also `CYAN, HI, LO, RGB`):

```python
# --- hi-res strip cell (bigsign / longboi) — handoff stripCell ---


@attrs.frozen
class StripGeo:
    """One hires strip's geometry (the handoff stripCell options dict)."""

    day_y: int  # day label cap-top y
    day_px: int
    icon_k: int  # lowres blit factor (icon is 8*k px square)
    icon_y: int
    temp_y: int
    temp_px: int
    stack: bool  # True: hi over lo; False: horizontal hi/lo segs
    line_h: int = 0  # stacked line advance
    pop_y: int | None = None  # precip % row (longboi only)
    pop_px: int = 9


# Handoff weatherBig: {dayY:2,dayPx:9,iconS:18,iconY:13,tempY:37,tempPx:12,
# stack:true,lineH:12} — iconS 18 snaps to a 16px (k=2) sprite blit.
_BIG_GEO = StripGeo(
    day_y=2, day_px=9, icon_k=2, icon_y=13, temp_y=37, temp_px=12,
    stack=True, line_h=12,
)
# Handoff weatherLong: {dayY:2,dayPx:10,iconS:22,iconY:13,tempY:40,
# tempPx:12,popY:52,popPx:9} — iconS 22 snaps to a 24px (k=3) blit.
_LONG_GEO = StripGeo(
    day_y=2, day_px=10, icon_k=3, icon_y=13, temp_y=40, temp_px=12,
    stack=False, pop_y=52,
)


def _ctext(shim, text, x, w, y_target, rgb, size, oy, *, bold=True):
    """Center `text` in the [x, x+w) band at handoff cap-top `y_target`."""
    tw = text_width(size, text, bold=bold)
    hires(
        shim, text, js_round(x + (w - tw) / 2), cap_top(y_target, size) + oy,
        rgb, size, bold=bold,
    )


def _center_segs(shim, segs, x, w, y_target, size, oy):
    """Center multi-color segments as one run (handoff centerSegs)."""
    total = sum(text_width(size, t) for t, _ in segs)
    cx = js_round(x + (w - total) / 2)
    for t, rgb in segs:
        cx += hires(shim, t, cx, cap_top(y_target, size) + oy, rgb, size)


def _temp_segs(hi_f, lo_f, units, *, degree) -> list[tuple[str, RGB]]:
    suffix = "°" if degree else ""
    return [
        (f"{display_temp(hi_f, units)}{suffix}", HI),
        ("/", LABEL),
        (f"{display_temp(lo_f, units)}{suffix}", LO),
    ]


def _strip_cell(shim, real, x, w, day: DayForecast, geo: StripGeo, units, oy):
    _ctext(shim, day.label, x, w, geo.day_y, AMBER, geo.day_px, oy)
    lowres, _ = KIND_SLUGS[day.kind]
    icon_w = 8 * geo.icon_k
    blit_emoji_scaled(
        real, lowres, js_round(x + (w - icon_w) / 2), geo.icon_y + oy, geo.icon_k
    )
    if geo.stack:
        _ctext(
            shim, str(display_temp(day.hi_f, units)), x, w, geo.temp_y, HI,
            geo.temp_px, oy,
        )
        _ctext(
            shim, str(display_temp(day.lo_f, units)), x, w,
            geo.temp_y + geo.line_h, LO, geo.temp_px, oy,
        )
    else:
        _center_segs(
            shim, _temp_segs(day.hi_f, day.lo_f, units, degree=False), x, w,
            geo.temp_y, geo.temp_px, oy,
        )
    if geo.pop_y is not None:
        rgb = CYAN if day.pop >= 50 else LABEL
        _ctext(shim, f"{day.pop}%", x, w, geo.pop_y, rgb, geo.pop_px, oy, bold=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather/tests/test_forecast_layouts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_layouts.py plugins/weather/tests/test_forecast_layouts.py
git commit -m "feat(weather): shared hires strip cell + per-sign geometry tables"
```

---

### Task 8: Hero renderers (`render_hero_big`, `render_hero_long`)

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast_layouts.py`
- Test: `plugins/weather/tests/test_forecast_layouts.py` (append)

**Interfaces:**
- Consumes: `_strip_cell`/`_ctext`/`_center_segs`/`_temp_segs` (Task 7), `paint.phys_wrap/vdivider/fit_text/hires/cap_top` (Task 1), `draw_emoji_at` for the hero icon.
- Produces: `render_hero_big(canvas, data: ForecastData, units: str, *, y_offset: int = 0) -> None` and `render_hero_long(...)` (same signature). Both take the WRAPPER canvas.

- [ ] **Step 1: Write failing tests**

Append to `plugins/weather/tests/test_forecast_layouts.py`:

```python
class TestRenderHeroBig:
    def test_hero_and_strip_regions_populated(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, DEMO_DATA, "imperial")
        real = unwrap_to_real(bigsign)
        assert lit(real, 4, 0, 40, 13)  # location label row
        assert lit(real, 40, 10, 110, 42)  # big current temp
        assert lit(real, 4, 12, 40, 46)  # hero icon (hires sprite)
        for i in range(4):  # four strip columns
            x0 = 118 + int(i * (252 - 118) / 4)
            assert lit(real, x0, 0, x0 + 33, 62), f"strip col {i}"

    def test_divider_dotted_at_x112(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, DEMO_DATA, "imperial")
        real = unwrap_to_real(bigsign)
        xs = {(x, y) for x, y, _ in lit(real, 112, 6, 113, 58)}
        assert xs == {(112, y) for y in range(6, 58, 3)}

    def test_feels_line_cyan(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, DEMO_DATA, "imperial")
        real = unwrap_to_real(bigsign)
        ink = {p for _, _, p in lit(real, 44, 50, 112, 64)}
        assert any(r == 0 and g > 100 and b > 200 for r, g, b in ink)

    def test_short_feed_widens_columns(self, bigsign, lit):
        import attrs

        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        short = attrs.evolve(DEMO_DATA, days=DEMO_DATA.days[:2])
        render_hero_big(bigsign, short, "imperial")
        real = unwrap_to_real(bigsign)
        # two columns spanning the whole strip: content near both ends
        assert lit(real, 118, 0, 185, 62)
        assert lit(real, 185, 0, 252, 62)

    def test_no_days_draws_hero_only(self, bigsign, lit):
        import attrs

        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, attrs.evolve(DEMO_DATA, days=()), "imperial")
        real = unwrap_to_real(bigsign)
        assert lit(real, 4, 0, 110, 62)
        assert not lit(real, 118, 0, 252, 62)


class TestRenderHeroLong:
    def test_hero_strip_and_divider(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_long

        render_hero_long(longboi, DEMO_DATA, "imperial")
        real = unwrap_to_real(longboi)
        assert lit(real, 6, 0, 60, 14)  # location, left-justified
        assert lit(real, 70, 10, 160, 45)  # big temp pushed right
        xs = {(x, y) for x, y, _ in lit(real, 156, 6, 157, 58)}
        assert xs == {(156, y) for y in range(6, 58, 3)}
        for i in range(6):  # six strip columns
            x0 = 162 + int(i * (506 - 162) / 6)
            assert lit(real, x0, 0, x0 + 57, 62), f"strip col {i}"

    def test_location_ellipsizes_to_hero_width(self, longboi, lit):
        import attrs

        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_long

        wide = attrs.evolve(
            DEMO_DATA, location="SOUTH BURLINGTON INTERNATIONAL DISTRICT"
        )
        render_hero_long(longboi, wide, "imperial")
        real = unwrap_to_real(longboi)
        # never bleeds past the divider into the strip's label row
        assert not lit(real, 156, 0, 162, 13)

    def test_precip_row_present(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_long

        render_hero_long(longboi, DEMO_DATA, "imperial")
        real = unwrap_to_real(longboi)
        assert lit(real, 162, 50, 506, 62)  # pop % row on every column


class TestWorstCaseCollision:
    """Spec Testing section: column-collision guard with worst-case content
    (widest temps `-99/-99`, `100%` pop) on both hires layouts — each
    column's ink must stay inside its own column band."""

    def _worst_data(self):
        import attrs

        from led_ticker_weather.forecast_data import DayForecast

        worst = tuple(
            DayForecast(label="WED", kind="thunder", hi_f=-99, lo_f=-99, pop=100)
            for _ in range(6)
        )
        cur = attrs.evolve(
            DEMO_DATA.current, temp_f=-99, feels_f=-99, hi_f=-99, lo_f=-99
        )
        return attrs.evolve(DEMO_DATA, current=cur, days=worst)

    @staticmethod
    def _column_gaps_clear(real, lit, x0, x1, n):
        cw = (x1 - x0) / n
        for i in range(1, n):
            edge = round(x0 + i * cw)
            # 1px gutter each side of every column boundary stays dark
            assert not lit(real, edge - 1, 0, edge + 1, 62), f"boundary {i}"

    def test_big_strip_columns_stay_separated(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, self._worst_data(), "imperial")
        self._column_gaps_clear(unwrap_to_real(bigsign), lit, 118, 252, 4)

    def test_long_strip_columns_stay_separated(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_long

        render_hero_long(longboi, self._worst_data(), "imperial")
        self._column_gaps_clear(unwrap_to_real(longboi), lit, 162, 506, 6)

    def test_big_hero_never_bleeds_into_strip(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real
        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, self._worst_data(), "imperial")
        # nothing between the divider (112) and the strip origin (118)
        assert not lit(unwrap_to_real(bigsign), 113, 0, 118, 62)
```

If a boundary-gutter assertion fails by 1-2px with worst-case temps, that is
a REAL layout finding (the handoff never exercised negative temps) — shrink
the offending `temp_px` is NOT the fix; report it and widen the assertion
gutter only with James's sign-off.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_forecast_layouts.py -q`
Expected: new classes FAIL — functions not defined.

- [ ] **Step 3: Implement**

Append to `plugins/weather/src/led_ticker_weather/forecast_layouts.py` (extend paint import with `fit_text, phys_wrap, vdivider`; add `safe_scale` to the `led_ticker.plugin` import):

```python
# --- hero layouts (bigsign / longboi) — handoff weatherBig / weatherLong ---

# Hero icon: 32x32 hires/pack sprite via draw_emoji_at at LOGICAL coords,
# so the physical position quantizes to scale multiples — (4,13) lands at
# (4,12), (4,15) at (4,16). <=3px drift, accepted (spec divergence 1).


def _hero_icon(canvas, kind: str, log_x: int, log_y: int, y_offset: int) -> None:
    _, hires_slug = KIND_SLUGS[kind]
    draw_emoji_at(canvas, hires_slug, log_x, log_y + y_offset)


def _strip(shim, real, days, x0, x1, n_slots, geo, units, oy):
    """Lay out up to n_slots day columns; a short feed widens the columns
    (cw = span / actual_n, the handoff's own formula with the real count)."""
    n = min(n_slots, len(days))
    if n == 0:
        return
    cw = (x1 - x0) / n
    for i in range(n):
        _strip_cell(shim, real, x0 + i * cw, cw, days[i], geo, units, oy)


def render_hero_big(canvas, data: ForecastData, units: str, *, y_offset: int = 0) -> None:
    """256x64: today hero left of a dotted divider, 4-day strip right."""
    shim, real = phys_wrap(canvas)
    oy = y_offset * safe_scale(canvas)
    cur = data.current
    hires(shim, data.location, 6, cap_top(2, 9) + oy, LABEL, 9)
    _hero_icon(canvas, cur.kind, 1, 3, y_offset)
    temp = f"{display_temp(cur.temp_f, units)}°"
    hires(shim, temp, 44, cap_top(13, 27) + oy, IDENT, 27)
    _center_segs(
        shim, _temp_segs(cur.hi_f, cur.lo_f, units, degree=True), 44, 60, 41, 11, oy
    )
    hires(
        shim, f"FEELS {display_temp(cur.feels_f, units)}°", 44,
        cap_top(53, 8) + oy, CYAN, 8, bold=False,
    )
    vdivider(real, 112, 6 + oy, 58 + oy)
    _strip(shim, real, data.days, 118, 252, 4, _BIG_GEO, units, oy)


def render_hero_long(canvas, data: ForecastData, units: str, *, y_offset: int = 0) -> None:
    """512x64: expanded hero (ellipsized location, temp pushed right),
    dotted divider, 6-day strip with precip %."""
    shim, real = phys_wrap(canvas)
    oy = y_offset * safe_scale(canvas)
    cur = data.current
    hires(shim, fit_text(data.location, 148, 11), 6, cap_top(2, 11) + oy, LABEL, 11)
    _hero_icon(canvas, cur.kind, 1, 4, y_offset)
    temp = f"{display_temp(cur.temp_f, units)}°"
    hires(shim, temp, 70, cap_top(14, 28) + oy, IDENT, 28)
    _center_segs(
        shim, _temp_segs(cur.hi_f, cur.lo_f, units, degree=True), 70, 80, 43, 11, oy
    )
    hires(
        shim, f"FEELS {display_temp(cur.feels_f, units)}°", 70,
        cap_top(56, 8) + oy, CYAN, 8, bold=False,
    )
    vdivider(real, 156, 6 + oy, 58 + oy)
    _strip(shim, real, data.days, 162, 506, 6, _LONG_GEO, units, oy)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest plugins/weather -q`
Expected: PASS (full suite green).

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast_layouts.py plugins/weather/tests/test_forecast_layouts.py
git commit -m "feat(weather): bigsign and longboi hero+strip forecast renderers"
```

---

### Task 9: `ForecastWidget` + registration + validation

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/forecast.py`
- Modify: `plugins/weather/src/led_ticker_weather/__init__.py`
- Modify: `plugins/weather/tests/test_smoke.py`
- Test: `plugins/weather/tests/test_forecast_widget.py`

**Interfaces:**
- Consumes: `resolve_forecast_layout` (Task 5), the three renderers (Tasks 6/8), `fetch_forecast/parse_forecast_payload/DEMO_DATA` (Task 4).
- Produces: `ForecastWidget` registered as `weather.forecast`, with `start()`, `update()`, `should_display()`, `draw()` (held cursor), `validate_config`, `validate_config_warnings`.

- [ ] **Step 1: Write failing tests**

Create `plugins/weather/tests/test_forecast_widget.py`:

```python
import unittest.mock as mock

import pytest

from led_ticker.plugin import unwrap_to_real
from led_ticker_weather.forecast import ForecastWidget


def _demo():
    return ForecastWidget(location="", demo=True)


class TestConstruction:
    def test_demo_seeds_handoff_week(self):
        w = _demo()
        assert w.should_display()

    def test_location_required_without_demo(self):
        with pytest.raises(ValueError, match="location"):
            ForecastWidget(location="")

    def test_dict_location_becomes_lat_lon_query(self):
        w = ForecastWidget(location={"lat": 40.71, "lon": -74.01})
        assert w.location == "40.71,-74.01"


class TestHeldCursor:
    def test_returns_logical_width_on_every_sign(
        self, smallsign, bigsign, longboi
    ):
        w = _demo()
        for canvas in (smallsign, bigsign, longboi):
            _, cursor = w.draw(canvas)
            assert cursor == canvas.width  # LOGICAL width — never real.width

    def test_bigsign_cursor_is_wrapper_width_not_physical(self, bigsign):
        w = _demo()
        _, cursor = w.draw(bigsign)
        assert cursor == 64
        assert unwrap_to_real(bigsign).width == 256


class TestLayoutDispatch:
    def test_smallsign_renders_strip(self, smallsign):
        _demo().draw(smallsign)
        assert smallsign.count_nonzero() > 0

    def test_bigsign_renders_hero_big(self, bigsign, lit):
        _demo().draw(bigsign)
        real = unwrap_to_real(bigsign)
        assert lit(real, 112, 6, 113, 58)  # big layout's divider column

    def test_longboi_renders_hero_long(self, longboi, lit):
        _demo().draw(longboi)
        real = unwrap_to_real(longboi)
        assert lit(real, 156, 6, 157, 58)  # long layout's divider column

    def test_no_data_draws_nothing_and_holds(self, smallsign):
        w = ForecastWidget(location="Boston")
        assert not w.should_display()
        _, cursor = w.draw(smallsign)
        assert cursor == smallsign.width
        assert smallsign.count_nonzero() == 0


class TestUpdate:
    async def test_update_parses_and_flips_visibility(self, monkeypatch):
        from test_forecast_data import _payload

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        w = ForecastWidget(location="Boston")
        with mock.patch(
            "led_ticker_weather.forecast.fetch_forecast",
            mock.AsyncMock(return_value=_payload()),
        ):
            await w.update()
        assert w.should_display()

    async def test_start_survives_failed_initial_fetch(self, monkeypatch):
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        with mock.patch(
            "led_ticker_weather.forecast.fetch_forecast",
            mock.AsyncMock(side_effect=ValueError("boom")),
        ):
            w = await ForecastWidget.start(location="Boston")
        assert not w.should_display()  # hidden, retrying in background


class TestValidateConfig:
    def test_clean_config_passes(self):
        assert ForecastWidget.validate_config({"location": "Boston"}) == []

    def test_bad_layout_rejected(self):
        errs = ForecastWidget.validate_config(
            {"location": "x", "layout": "dashboard"}
        )
        assert any("layout" in e for e in errs)

    def test_bad_units_rejected(self):
        errs = ForecastWidget.validate_config({"location": "x", "units": "kelvin"})
        assert any("units" in e for e in errs)

    def test_location_required_unless_demo(self):
        assert any(
            "location" in e for e in ForecastWidget.validate_config({})
        )
        assert ForecastWidget.validate_config({"demo": True}) == []

    def test_update_interval_bool_and_nonpositive_rejected(self):
        for bad in (True, 0, -5):
            errs = ForecastWidget.validate_config(
                {"location": "x", "update_interval": bad}
            )
            assert any("update_interval" in e for e in errs), bad

    def test_warnings_for_impossible_layouts(self):
        ctx = mock.Mock(scale=1, panel_width=160)
        warns = ForecastWidget.validate_config_warnings(
            {"location": "x", "layout": "big"}, ctx
        )
        assert any("strip" in w for w in warns)
        ctx = mock.Mock(scale=4, panel_width=256)
        warns = ForecastWidget.validate_config_warnings(
            {"location": "x", "layout": "long"}, ctx
        )
        assert any("big" in w for w in warns)
```

Also append to `plugins/weather/tests/test_smoke.py`, inside the existing
`try:` block after the `get_source_class` assertion:

```python
        assert get_widget_class("weather.forecast") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest plugins/weather/tests/test_forecast_widget.py plugins/weather/tests/test_smoke.py -q`
Expected: FAIL — `ForecastWidget` not defined / `weather.forecast` unregistered.

- [ ] **Step 3: Implement the widget**

Extend `plugins/weather/src/led_ticker_weather/forecast.py`. The `import`
block below goes at the TOP of the module (above `VALID_LAYOUTS`), the class
below the existing `resolve_forecast_layout` — appending the imports verbatim
mid-file is a ruff E402 failure:

```python
import logging

import aiohttp
import attrs
from led_ticker.plugin import (
    Color,
    FrameAwareBase,
    run_monitor_loop,
    safe_scale,
    spawn_tracked,
    unwrap_to_real,
)

from led_ticker_weather.forecast_data import (
    DEMO_DATA,
    ForecastData,
    fetch_forecast,
    parse_forecast_payload,
)
from led_ticker_weather.forecast_layouts import (
    render_hero_big,
    render_hero_long,
    render_strip_small,
)


@attrs.define
class ForecastWidget(FrameAwareBase):
    """weather.forecast — held multi-day forecast card."""

    location: str = ""
    layout: str = "auto"
    units: str = "imperial"
    update_interval: int = attrs.field(default=10800, converter=int)
    demo: bool = False
    # The engine's SHARED aiohttp session (core's _build_widget passes it
    # to start()); never close it. None (tests/direct) => fetch_forecast
    # opens a short-lived session per poll.
    session: aiohttp.ClientSession | None = None
    # Declared only — the ENGINE paints bg (Clear/Fill + transition bg
    # kwargs); draw() must never Fill (push-transition compositing draws
    # outgoing + incoming on the SAME canvas).
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    _data: ForecastData | None = attrs.field(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        # dict location from TOML ({lat = 40.71, lon = -74.01}), same
        # convention as weather.current.
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"
        if self.demo:
            self._data = DEMO_DATA
        elif not self.location:
            raise ValueError(
                "weather.forecast requires location (or demo = true)"
            )

    @classmethod
    async def start(cls, *args, **kwargs):
        widget = cls(*args, **kwargs)
        if not widget.demo:
            try:
                await widget.update()
            except Exception:
                logging.exception(
                    "weather.forecast initial fetch failed for %s; "
                    "will retry in background",
                    widget.location,
                )
            spawn_tracked(run_monitor_loop(widget, widget.update_interval))
        return widget

    async def update(self) -> None:
        payload = await fetch_forecast(self.session, self.location)
        self._data = parse_forecast_payload(payload)
        logging.info(
            "weather.forecast %s updated: current + %d days",
            self.location,
            len(self._data.days),
        )

    def should_display(self) -> bool:
        """Hide from the rotation until data exists (core visibility seam)."""
        return self._data is not None

    def draw(self, canvas, cursor_pos=0, *, y_offset: int = 0, font_color=None):
        data = self._data
        if data is None:
            # Belt only — _expand_sources already drops us via
            # should_display(); a transition compositor may still call.
            return canvas, canvas.width
        layout = resolve_forecast_layout(
            self.layout, safe_scale(canvas), unwrap_to_real(canvas).width
        )
        if layout == "strip":
            render_strip_small(canvas, data, self.units, y_offset=y_offset)
        elif layout == "big":
            render_hero_big(canvas, data, self.units, y_offset=y_offset)
        else:
            render_hero_long(canvas, data, self.units, y_offset=y_offset)
        # Held card: LOGICAL width (never real.width — the engine compares
        # against the wrapper's width; real.width takes the scroll branch).
        return canvas, canvas.width

    @classmethod
    def validate_config(cls, cfg) -> list[str]:
        errs: list[str] = []
        layout = cfg.get("layout", "auto")
        if layout not in VALID_LAYOUTS:
            errs.append(f"layout must be one of {VALID_LAYOUTS}, got {layout!r}")
        units = cfg.get("units", "imperial")
        if units not in ("imperial", "metric"):
            errs.append(f'units must be "imperial" or "metric", got {units!r}')
        if not cfg.get("demo", False) and not cfg.get("location"):
            errs.append("location is required unless demo = true")
        interval = cfg.get("update_interval", 10800)
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
        ):
            errs.append(
                f"update_interval must be a positive number, got {interval!r}"
            )
        return errs

    @classmethod
    def validate_config_warnings(cls, cfg, ctx) -> list[str]:
        warns: list[str] = []
        layout = cfg.get("layout", "auto")
        if layout in ("big", "long") and ctx.scale == 1:
            warns.append(
                f'layout = "{layout}" needs a hi-res (scale > 1) sign; '
                'this panel will render the "strip" layout'
            )
        elif layout == "long" and ctx.scale > 1 and ctx.panel_width < 400:
            warns.append(
                'layout = "long" is designed for panels >= 400 px wide; '
                'this panel will render the "big" layout'
            )
        return warns
```

- [ ] **Step 4: Register the widget**

In `plugins/weather/src/led_ticker_weather/__init__.py`:

```python
"""led-ticker-weather: current-conditions widget (weather.current) and
multi-day forecast card (weather.forecast) contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``weather`` is the plugin namespace, so the widgets
are referenced in config.toml as ``type = "weather.current"`` /
``type = "weather.forecast"``.
"""

from led_ticker_weather.forecast import ForecastWidget
from led_ticker_weather.source import WeatherSource
from led_ticker_weather.weather import WeatherWidget


def register(api):
    api.widget("current")(WeatherWidget)
    api.widget("forecast")(ForecastWidget)
    api.source("current")(WeatherSource)
```

- [ ] **Step 5: Run the full plugin suite**

Run: `uv run pytest plugins/weather -q && uv run ruff check plugins/weather`
Expected: all PASS, lint clean.

- [ ] **Step 6: Commit**

```bash
git add plugins/weather/src/led_ticker_weather/forecast.py plugins/weather/src/led_ticker_weather/__init__.py plugins/weather/tests/test_forecast_widget.py plugins/weather/tests/test_smoke.py
git commit -m "feat(weather): ForecastWidget — held card, layout dispatch, validation"
```

---

### Task 10: README + visual validation (GIFs on all three signs)

**Files:**
- Modify: `plugins/weather/README.md`
- No new source (fixes from visual review get their own commits)

- [ ] **Step 1: Document the widget in the plugin README**

Add a `weather.forecast` section following the README's existing structure for
`weather.current` (read it first and match its heading/table style):
the config surface from the spec (`location`, `layout`, `units`,
`update_interval`, `demo`), the three layouts with their auto-detection rule,
the WEATHERAPI_KEY requirement and the free-tier degrade behavior, plus a
**Divergences from the design handoff** list (flight-README style) with the
spec's four divergences: packaged-emoji icons w/ size snapping + hero-only
pack sprites; nearest-BDF smallsign font; no °F/°C toggle or GLOW control
(config/hardware); no re-render loop (engine cadence).

- [ ] **Step 2: Render preview GIFs of all three signs**

Use the core repo checkout's render tooling (the `making-a-gif` skill knows
the exact command shape; the plugin must be importable — install it editable
into the core repo's venv first):

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv pip install -e ../led-ticker-plugins-weather-forecast/plugins/weather
```

Create a demo config per sign (smallsign 160×16 scale 1; bigsign 256×64
scale 4; longboi 512×64 scale 4) with one section holding
`type = "weather.forecast"`, `demo = true`. Render each with the repo's
render-demo tool, then **Read each PNG/GIF** and check against
`design/Weather Forecast.dc.html`'s intended look: column alignment, hero
text stack (location above temp, hi/lo, FEELS), divider position, icon
placement, palette (warm hi over cool lo, amber day labels, cyan FEELS/pop).

- [ ] **Step 3: Show James before finalizing**

Per the pixel-art iteration workflow: show the rendered previews and get a
visual sign-off; iterate in small steps on anything that reads wrong on the
panel (commit each accepted fix separately with its own test where the fix
is geometry the tests pin).

- [ ] **Step 4: Final full-suite run + lint + pyright**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins-weather-forecast
uv run pytest plugins/weather -q
uv run ruff check plugins/weather
uv run ruff format --check plugins/weather
uv run pyright plugins/weather/src
```

Expected: all clean (pyright is pre-push only but required before push).

- [ ] **Step 5: Commit**

```bash
git add plugins/weather/README.md
git commit -m "docs(weather): weather.forecast user surface + handoff divergences"
```

---

## Post-plan

After all tasks: antagonistic review loop applies if scope grew; otherwise
request code review, then open a draft PR via the open-pr flow (NEVER merge
without James's fresh per-PR consent).
