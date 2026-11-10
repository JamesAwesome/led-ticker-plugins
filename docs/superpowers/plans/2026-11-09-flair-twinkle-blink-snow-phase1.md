# flair twinkle / blink / snow — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.blink`, `flair.twinkle` (text animation + background) and `flair.snow` (background + transition), with the one core seam per-pixel text twinkle needs.

**Architecture:** Core grows an optional `AnimationFrame.pixel_gain` callable; `message` and the image single-row overlay draw text through a SetPixel proxy that multiplies each lit pixel by `gain(x_real, y_real)`. Everything else is flair-only, on existing seams: animations (`visible_text` blanking), `background` (pure function of real dims + frame), and transitions (`_raster.py` snapshot-only).

**Tech Stack:** Python 3.14, attrs, pytest, uv. Two repos: core `led-ticker` (PR 1, released as a minor), plugins monorepo `led-ticker-plugins` (PR 2).

**Spec:** `docs/superpowers/specs/2026-11-09-flair-twinkle-blink-snow-design.md` (plugins repo). Phase 2 (spec §8) gets its own plan after this merges.

## Global Constraints

- Work in worktrees, never the primary checkouts. Core: `git worktree add -b feat/pixel-gain-seam ../led-ticker-wt-gain origin/main`. Plugins: `git worktree add -b feat/flair-twinkle-blink-snow ../led-ticker-plugins-wt-fx2 origin/main` (after PR 1 is released). Verify `pwd` + `git branch --show-current` before every git op.
- No `from __future__ import annotations` (PEP 649).
- flair imports ONLY from `led_ticker.plugin` (`tests/test_import_purity.py`).
- Every effect is a pure function of `(real dims, frame, seed)`; no state advanced per `paint()`/`draw()` call.
- Backgrounds never paint black; paint at physical resolution on `unwrap_to_real(canvas)`; `frame_invariant = False`; `restart_on_visit = False`.
- Transitions: re-derive `unwrap_to_real(canvas)` every `frame_at`; refire on `t == 0.0 or t < self._last_t`; at `t >= SNAP_THRESHOLD`: `snap_reset(canvas, kwargs.get("incoming_bg_color"))` + `incoming.draw(canvas, cursor_pos=0)`.
- Photosensitivity: blink refuses an effective rate > 3 Hz (period < 7 engine frames = 350 ms) unless `allow_fast = true`; twinkle `speed` capped at `2.0`.
- Perf budget: ≤ 50 ms/frame projected on Pi 5 at 256×64 (dev-machine assertion: ≤ 8 ms per frame in the perf tests).
- Core: `make test`, `make lint`, `uv run pyright` before push. Plugins: `make lint`, `uv run pytest plugins/flair` from the monorepo root.
- PRs are drafts; never merge without James's per-PR go-ahead; `gh pr create` needs his approval.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Spec adjustments made while planning (my calls — update the spec in Task 9)

1. Twinkle-background `density` default is `0.03` (fraction of real pixels that are stars), not `0.6`. 0.6 is the text-twinkle default; 60% of a panel lit as stars is a wash.
2. Twinkle `speed` cap is `2.0`, not `3.0` (keeps every pixel's cycle ≥ 6 frames ≈ ≤3.3 Hz).
3. Snow `density` is flakes per 1000 real px² with default `3.0` (bigsign 49, longboi 25, smallsign 8 flakes); `0.5` gave smallsign 1 flake.
4. Snow fall speed is normalized to panel height: at `speed = 1.0` a flake crosses the panel in ~5 s on every geometry.

## Review Focus

1. **Blink hold ending in the off phase** → the transition's outgoing frame must show text, not a blank panel (`frames_to_rest` + Task 3 test `test_frames_to_rest_counts_to_next_on`).
2. **Twinkle on a bigsign hi-res font** → hi-res glyphs paint through `unwrap_to_real`; they must twinkle too, not only BDF (Task 1 test `test_gain_reaches_hires_path`).
3. **Snow with a pack-only emoji slug on the smallsign** (no 8×8) → refused at config-load with a hint, not an invisible flake (Task 6 `test_hires_only_slug_refused`).
4. **Blink with inline emoji or a colored value token** → off phase must blank cleanly, no exception from the empty slice (Task 3 `test_empty_slice_with_emoji_and_token`).
5. **Snow transition from a widget with no lit pixels / to a bordered widget** → completes, no stale outgoing pixels after the snap (Task 7 `test_empty_outgoing` + `test_no_outgoing_pixels_after_snap`).

---

## PR 1 — core (`led-ticker`)

### Task 1: `pixel_gain` seam + gain proxy

**Files:**
- Create: `src/led_ticker/pixel_gain.py`
- Modify: `src/led_ticker/animations.py` (`AnimationFrame`), `src/led_ticker/widgets/message.py` (text branch, ~line 433 `draw_text_run(draw_canvas, ...)`), `src/led_ticker/widgets/_image_base.py` (`_lensed_or_plain_draw` + every site that reads `getattr(anim_frame, "lens", None)`), `src/led_ticker/plugin.py` (docstring only — `AnimationFrame` already exported)
- Test: `tests/test_pixel_gain.py`

**Interfaces:**
- Produces: `AnimationFrame.pixel_gain: Callable[[int, int], float] | None = None` (real-pixel coords → multiplier, clamped to `[0, 1]`).
- Produces: `led_ticker.pixel_gain.with_pixel_gain(canvas: Canvas, gain: Callable[[int, int], float]) -> Canvas` — returns `GainCanvas(canvas, gain)` for a plain canvas; for a `ScaledCanvas` returns a NEW `ScaledCanvas(GainCanvas(canvas.real, gain), scale=canvas.scale, content_height=canvas.content_height)` so both the block-expanding `SetPixel` and the hi-res `unwrap_to_real(...)` path hit the proxy. `GainCanvas.SetPixel(x, y, r, g, b)` writes `round(c * clamp(gain(x, y)))` per channel; every other attribute forwards via `__getattr__`.

- [ ] **Step 1: Write failing tests** in `tests/test_pixel_gain.py`:
  - `test_default_is_none`: `AnimationFrame(visible_text="x").pixel_gain is None`.
  - `test_gain_scales_setpixel`: `with_pixel_gain(HeadlessCanvas(8,8), lambda x,y: 0.5).SetPixel(1,1,200,100,0)` → underlying pixel `(100, 50, 0)`.
  - `test_gain_clamped`: gain `2.0` → unchanged; gain `-1` → `(0,0,0)`.
  - `test_gain_reaches_bdf_scaled_path`: `ScaledCanvas(scale=4)` wrapped; one logical `SetPixel` → 16 real writes each scaled, gain called with REAL coords.
  - `test_gain_reaches_hires_path`: `unwrap_to_real(with_pixel_gain(scaled, g))` is the `GainCanvas`.
  - `test_message_text_twinkles_border_does_not`: a `TickerMessage` with a constant border and an animation stub returning `pixel_gain=lambda x,y: 0.0` → no text pixels lit, all border pixels at full color.
  - `test_message_byte_identical_without_gain`: draw with `pixel_gain=None` equals draw with no animation (pixel dict equality).
  - `test_image_overlay_text_twinkles`: `StillImage` single-row overlay text with gain `0.0` → text absent, image pixels intact.
  - `test_rotation_and_lens_ignore_gain`: an `AnimationFrame` with `rotation=90` and `pixel_gain` set draws identically to `rotation=90` alone (documented precedence: rotation > lens > gain).

- [ ] **Step 2: Run** `uv run pytest tests/test_pixel_gain.py -v` → FAIL (`ImportError` / missing field).

- [ ] **Step 3: Implement.** Add the field to `AnimationFrame` (+ docstring entry). In `message.draw`, read `pixel_gain = getattr(anim_frame, "pixel_gain", None)` next to `lens`; when `rotate_surface is None and pixel_gain is not None`, pass `with_pixel_gain(draw_canvas, pixel_gain)` to `draw_text_run` (border/background calls stay on the raw canvas). In `_image_base`, thread `pixel_gain` beside `lens` into `_lensed_or_plain_draw(..., pixel_gain=None)`; on the `lens is None` branch wrap `text_canvas` before `_draw_text`. Re-wrap per call (the canvas changes every swap — never cache the proxy).

- [ ] **Step 4: Run** `uv run pytest tests/test_pixel_gain.py tests/test_animations.py tests/test_lens.py tests/test_image_animation.py -v` → PASS.

- [ ] **Step 5: Commit** `feat(animations): AnimationFrame.pixel_gain per-pixel text seam`.

### Task 2: docs, validate parity, release notes

**Files:**
- Modify: docs-site Plugin API reference page (`docs/site/**/plugins/api-reference.mdx`, the `AnimationFrame` section) and the animations concept page; `CLAUDE.md` (new bullet under "Color providers and animations": `pixel_gain` seam, precedence rotation > lens > gain, proxy re-wrapped per call, border/background never routed through it; tripwire `tests/test_pixel_gain.py`).
- Test: `tests/test_docs_plugin_api_drift.py` (existing — must pass).

- [ ] **Step 1:** Add the field to the API reference (follow `docs/DOCS-STYLE.md`). Run `uv run pytest tests/test_docs_plugin_api_drift.py -v` → PASS.
- [ ] **Step 2:** `make test && make lint && uv run pyright` → all green.
- [ ] **Step 3: Commit** `docs(animations): document pixel_gain`; push; open a DRAFT PR (ask James before `gh pr create`). After merge, the core release (next minor, expected `4.33.0`) is James's click.

---

## PR 2 — flair (`led-ticker-plugins`), after core release

### Task 3: `flair.blink` animation

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/blink.py`
- Test: `plugins/flair/tests/test_flair_blink.py`

**Interfaces:**
- Produces: `class Blink(period_ms: int = 1000, duty: float = 0.75, count: int = 0, allow_fast: bool = False)`; class attrs `restart_on_visit = True`, `emits_rotation = False`; `frame_for(frame, full_text, canvas_width, text_width) -> AnimationFrame`; `frames_to_rest(frame, total_chars) -> int`.
- Frames: `period = max(2, round(period_ms / ENGINE_TICK_MS))`; `on = min(period - 1, max(1, round(period * duty)))`; ON iff `count and frame >= count * period` or `frame % period < on`.

- [ ] **Step 1: Write failing tests:**
  - `test_frame_zero_is_on`, `test_default_cycle`: frames 0–14 on, 15–19 off, 20 on (1000 ms, 0.75).
  - `test_off_phase_blanks`: `frame_for(15, "NEWS", ...).visible_text == ""`.
  - `test_count_stops_on`: `count=2` → every frame ≥ 40 is on.
  - `test_frames_to_rest_counts_to_next_on`: `frames_to_rest(15)` == 5, `frames_to_rest(3)` == 0.
  - `test_fast_rate_refused`: `Blink(period_ms=300)` raises `ValueError` matching `"WCAG 2.3.1"` and `"allow_fast"`; `Blink(period_ms=300, allow_fast=True)` OK; `Blink(period_ms=350)` OK.
  - `test_bad_args`: `duty` ∉ (0,1), `count < 0`, `count` bool, `period_ms <= 0` → `ValueError`.
  - `test_empty_slice_with_emoji_and_token`: a real `TickerMessage(text="HOT :sun: deal")` with `animation=Blink()` drawn at frame 15 on `HeadlessCanvas` → no exception, no lit pixels outside the border.
  - `test_message_end_cursor_unchanged`: off-phase `draw()` returns the same cursor as on-phase (scroll math stable).
- [ ] **Step 2: Run** `uv run pytest plugins/flair/tests/test_flair_blink.py -v` → FAIL.
- [ ] **Step 3: Implement** `Blink` per Interfaces; error text: `"flair.blink: period_ms={p} blinks faster than 3 Hz (WCAG 2.3.1 photosensitivity limit); set allow_fast = true to opt in"`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(flair): flair.blink animation`.

### Task 4: twinkle math (`_twinkle.py`)

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_twinkle.py`
- Test: `plugins/flair/tests/test_flair_twinkle_math.py`

**Interfaces:**
- Produces: `hash32(x: int, y: int, seed: int, salt: int) -> int` (pure integer mix, no `random`); `is_twinkler(x, y, seed, density) -> bool` (`hash32(..., salt=1) / 2**32 < density`); `level(x, y, frame, seed, speed) -> float` in `[0, 1]`.
- `level` algorithm (TwinkleFOX): `cycle = 24 / speed` frames; `factor = 1 + (hash32(x,y,seed,2) % 8) / 8` (∈ [1, 2)); `offset = hash32(x,y,seed,3) / 2**32`; `p = (frame * factor / cycle + offset) % 1`; `level = 3p if p < 1/3 else 1.5(1 - p)`.

- [ ] **Step 1: Write failing tests:** `test_level_bounds` (all in [0,1] over a 32×16×200 sweep); `test_pure` (same args → same value); `test_desynchronized` (at a fixed frame, levels across 100 pixels have stdev > 0.2); `test_density_fraction` (twinklers over 256×64 within ±0.02 of 0.6); `test_min_cycle_at_max_speed` (at speed 2.0 every pixel's period ≥ 6 frames); `test_seed_changes_pattern`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(flair): TwinkleFOX-style twinkle math`.

### Task 5: `flair.twinkle` animation + background

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/twinkle.py` (animation), `plugins/flair/src/led_ticker_flair/flair/twinkle_background.py`
- Test: `plugins/flair/tests/test_flair_twinkle.py`, `plugins/flair/tests/test_flair_twinkle_background.py`

**Interfaces:**
- Consumes: `_twinkle.level`, `_twinkle.is_twinkler`, `_twinkle.hash32` (Task 4); core `AnimationFrame.pixel_gain` (Task 1).
- Produces: `class Twinkle(density=0.6, speed=1.0, min_brightness=0.15, seed=None)`; `restart_on_visit = False`; `frame_for` returns `AnimationFrame(visible_text=full_text, pixel_gain=g)` with `g(x, y) = 1.0` for non-twinklers else `min_brightness + (1 - min_brightness) * level(...)`; `frames_to_rest` → 0.
- Produces: `class TwinkleBackground(BackgroundEffectBase)(density=0.03, speed=1.0, color=(255, 230, 180), seed=None)`; `frame_invariant = False`; `restart_on_visit = False`; `paint(canvas, frame_count)`: star positions = a list built once per `(real.width, real.height)` (every pixel with `is_twinkler(x, y, seed, density)`, cached on the instance — derived data, not sim state); per star paint `color * level`, skipping writes that round to black.
- Validation (both): `density` in `(0, 1]`; `speed` in `(0, 2.0]`; `min_brightness` in `[0, 1)`; `color` an `[r,g,b]` of ints 0–255; `seed` int or None. `seed=None` → one OS-entropy seed at construction.

- [ ] **Step 1: Write failing tests:**
  - animation: `test_gain_is_one_for_non_twinklers`, `test_gain_floor` (never below `min_brightness`), `test_pure_function_of_frame`, `test_speed_cap` (`speed=2.5` raises), `test_bigsign_hires_message_twinkles` (real `TickerMessage` with a hires font on `ScaledCanvas(scale=4)` over a 256×64 `HeadlessCanvas`: some lit text pixels dimmer than the font color at frame 7), `test_perf_bigsign` (≤ 8 ms per `draw()` for a 20-char hires message at 256×64).
  - background: `test_never_paints_black`, `test_pure_function_of_frame`, `test_unseeded_instance_is_still_frame_pure`, `test_star_count_scales_with_area` (smallsign vs bigsign within ±30% of `0.03 * area`), `TestScaledCanvas` (patch `ScaledCanvas.SetPixel` at the class to fail — paints only on real), `test_perf_bigsign` (≤ 2 ms per `paint`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(flair): flair.twinkle text animation and starfield background`.

### Task 6: `flair.snow` background

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_snow.py` (shared flake model), `plugins/flair/src/led_ticker_flair/flair/snow_background.py`
- Test: `plugins/flair/tests/test_flair_snow_background.py`

**Interfaces:**
- Consumes: `stickers.capture_sprite(slug, 1, None)` for 8×8 sprite pixels (bbox-normalized `{(x, y): (r, g, b)}`); `emoji_slugs()`; `_twinkle.hash32`.
- Produces (`_snow.py`): `flake_pixels(flake: str, color: tuple[int,int,int]) -> dict[tuple[int,int], tuple[int,int,int]]` (`"dot"` → 1 px, `"plus"` → 5-px +, slug → captured 8×8, cached via `functools.cache`); `flake_count(width, height, density) -> int` (`max(1, round(density * w * h / 1000))`); `flake_position(i, frame, w, h, seed, speed, speed_variation, drift, wind, sprite_h) -> tuple[int, int, float]` → `(x, y, intensity)`: per-flake `x0`, `y0`, `v` (fall px/frame = `h / 100 * speed * (1 ± speed_variation)`), wobble phase and intensity ∈ [0.5, 1] all from `hash32(i, epoch, seed, salt)` where `epoch` increments each time the flake wraps past the bottom (so it re-enters at a new x); `x = (x0 + wind*frame + drift * 3 * sin(frame/10 + phase)) % w`.
- Produces: `class SnowBackground(BackgroundEffectBase)(flake="dot", density=3.0, speed=1.0, speed_variation=0.4, drift=0.3, wind=0.0, color=(200, 220, 255), seed=None)`; `frame_invariant = False`; `restart_on_visit = False`.
- Validation: `flake` ∈ `{"dot","plus"}` or a slug in `emoji_slugs()` that has an 8×8 form (`capture_sprite(slug, 1, None)` non-empty) — else `ValueError` naming the slug and suggesting `"dot"`; numeric ranges `density > 0`, `speed` in `(0, 5]`, `speed_variation` in `[0, 1)`, `drift >= 0`.

- [ ] **Step 1: Write failing tests:** `test_never_paints_black`; `test_pure_function_of_frame`; `test_flakes_fall` (flake 0's y increases between frames 0 and 10); `test_wrap_reenters_at_new_x`; `test_count_by_geometry` (160×16 → 8, 128×64 → 25, 256×64 → 49 at default density); `test_emoji_flake_is_8px_on_bigsign` (`flake="snow"` on scale-4 canvas: one flake's lit bbox ≤ 8×8 real px); `test_hires_only_slug_refused` (pick a pack-only slug from `emoji_slugs()` whose `capture_sprite(slug,1,None)` is empty); `test_unknown_slug_refused`; `TestScaledCanvas`; `test_perf_bigsign` (≤ 3 ms per `paint`, `flake="snow"`, density 3).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(flair): flair.snow background`.

### Task 7: `flair.snow` transition (`flurry`)

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/snow.py`
- Test: `plugins/flair/tests/test_flair_snow_transition.py`

**Interfaces:**
- Consumes: `_raster.Raster`, `_raster.snapshot_into`, `_raster.is_lit`; `_snow.flake_pixels`/`flake_count`/`flake_position` (Task 6).
- Produces: `class Snow(flake="dot", density=6.0, drift=0.3, wind=0.0, color=(230, 240, 255), seed=None, mode="flurry")`; `min_frames = 24`; `scale_switch_at = 1.0`; `frame_at(t, canvas, outgoing, incoming, **kwargs)`.
- Algorithm: on refire, snapshot outgoing AND incoming once into two `Raster`s (physical res; laser pattern) and collect lit pixel lists. Front per real column: `J = max(2, h // 4)`; `jit(x) = hash32(x, 0, seed, 9) % (J + 1)`; `front(x, t) = (t / SNAP_THRESHOLD) * (h + J) - J + jit(x)`. Paint incoming lit pixels with `y < front(x)`, outgoing lit pixels with `y >= front(x)`. Flakes (count `flake_count(w, h, density) * sin(pi * t)`) paint on top, each falling 1.5× faster than the front so the flurry leads it. `mode` accepts only `"flurry"` in v1 (`"build"` → `ValueError` "planned, not yet available").

- [ ] **Step 1: Write failing tests:** `test_t0_shows_only_outgoing`; `test_snap_shows_only_incoming` (t=0.95); `test_no_outgoing_pixels_after_snap`; `test_front_monotone` (a column's incoming-pixel count never decreases with t); `test_outgoing_not_drawn_live_after_snapshot` (spy on `outgoing.draw` call count = 1 per firing); `test_refire_resnapshots` (`t` goes 0.9 → 0.1); `test_t0_always_refires`; `test_empty_outgoing` (completes; incoming fully shown at snap); `test_bordered_incoming_no_flash` (`incoming_bg_color` forwarded to `snap_reset`); `test_scaled_physical_resolution`; `test_build_mode_refused`; `test_perf_bigsign` (≤ 8 ms per frame at 256×64, density 6, worst t=0.5).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(flair): flair.snow flurry transition`.

### Task 8: registration, version seam, fakes

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py`, `plugins/flair/pyproject.toml` (`led-ticker-core>=4.33` — the release from PR 1), every test file defining `_RecordingAPI` (no new methods needed; verify `background()` present), `plugins/flair/tests/test_smoke.py`
- Test: `plugins/flair/tests/test_smoke.py`, `test_import_purity.py`

- [ ] **Step 1: Write failing tests** in `test_smoke.py`: `register()` puts `blink`, `twinkle` in animations; `twinkle`, `snow` in backgrounds; `snow` in transitions. `test_import_seam_requires_pixel_gain`: monkeypatch `AnimationFrame` without the field → `register()` raises `ImportError` mentioning `"4.33"`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement:** registrations `api.animation("blink")(Blink)`, `api.animation("twinkle")(Twinkle)`, `api.background("twinkle")(TwinkleBackground)`, `api.background("snow")(SnowBackground)`, `api.transition("snow")(Snow)`; `_import_seam` probe `"pixel_gain" in AnimationFrame.__dataclass_fields__` with message `"flair requires led-ticker-core >= 4.33 (the AnimationFrame.pixel_gain seam flair.twinkle needs); update the core image, not the flair plugin."`; floor bump.
- [ ] **Step 4: Run** `uv run pytest plugins/flair -q && make lint` → PASS.
- [ ] **Step 5: Commit** `feat(flair): register twinkle, blink, snow`.

### Task 9: docs, examples, gifs

**Files:**
- Modify: `plugins/flair/CLAUDE.md` (one invariants section per new module, tripwires named from Tasks 3–7), `plugins/flair/README.md`, the spec (apply "Spec adjustments" 1–4).
- Create: `plugins/flair/examples/config.{blink,twinkle,snow}-smoke.{smallsign,bigsign,longboi}.toml`; demo gifs in `plugins/flair/docs/` via the `making-a-gif` skill (bigsign needs the rows=64/cols=256/chain=1 render copy; render via `uv run --project ../led-ticker-plugins`).
- Core docs-site catalogue entries (animations, backgrounds, transitions pages) — a small follow-up core docs PR, snippets verbatim from the demo TOMLs.

- [ ] **Step 1:** `uv run led-ticker validate --config plugins/flair/examples/<each>.toml` → no errors for all 9 configs.
- [ ] **Step 2:** Render gifs; Read each PNG/GIF frame and show James before committing.
- [ ] **Step 3: Commit** `docs(flair): twinkle, blink, snow docs + smoke configs`; push; DRAFT PR (James approves `gh pr create`).
