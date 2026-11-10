# flair: twinkle, blink, snow — design

Status: APPROVED (2026-11-09). Twinkle = C + B (§2.4). Gaps in §8 are closed in a follow-up phase immediately after the v1 merge.

## Intent

Add three classic LED-sign effects, named and parameterized the way the sign / LED-animation world already names them, so users coming from BetaBrite, WLED, FastLED or CSS recognize them:

- **twinkle** — random lit pixels of the message dim and flicker while it holds.
- **blink** — "NEWS FLASH" on/off strobe of the text.
- **snow** — flakes (a dot, or a chosen emoji) falling; a **background** (behind text, while it holds) and a **transition** (flakes in the foreground over the cut).

Default home: the `flair` pack. One effect (per-pixel twinkle) has a real argument for a small core seam — see §2.

## Non-goals / anti-goals

- No effect that can exceed WCAG 2.3.1 (>3 flashes/s) without an explicit opt-in. A flair effect that can trigger a seizure by default is a failure even if it looks great.
- No stateful particle sims. Every effect is a pure function of `(dims, frame)` (transitions re-render widgets at a paused frame; fireworks-background invariant).
- No GetPixel-dependent design (core constraint #3).
- No new `type =` widgets to get these effects; they attach to existing widgets.

## Precedent (summary)

| Effect | Industry names | Key params seen | Layer semantics |
|---|---|---|---|
| Twinkle | Alpha/BetaBrite TWINKLE (`n0`), SPARKLE (`n1`); WLED Twinkle / Sparkle / Twinklefox / Sparkle Dark; FastLED TwinkleFOX; Adafruit `Sparkle` | density (FastLED 0–8, def 5 ≈ 0.6), speed, fast-attack/slow-decay curve, `mask` (Adafruit: restrict to a pixel set), dim-toward-red (incandescent) | Alpha TWINKLE = the **text's own** lit pixels flicker. WLED Sparkle has an "overlay" flag. |
| Blink | Alpha FLASH (`c`), NEWS FLASH (Betabrite 1036 only); WLED Blink / Strobe; Adafruit `Blink`; HTML `<blink>` | period (WLED 0–5.1 s), **duty cycle** (Firefox `<blink>`: 1 Hz, 0.75 on); strobe = separate style, single-frame on | Off = **blank to background** everywhere; nobody inverts by default. Alpha chains "flash then roll off" (trailing mode). |
| Snow | Alpha SNOW (`n2`, a **transition**: pixels fall and build the new text bottom-up), STARBURST (`n7`); Vixen Snowflakes; tsParticles "snow" preset | flake count/density, speed + speed variation, wobble/drift, size, random intensity/opacity, flake type (sprite), optional **build-up** (off by default) | Background: no accumulation by default. Alpha: snow is an entry effect. |

Accessibility: WCAG 2.3.1 — ≤3 flashes in any 1 s; 2.2.2 — auto-starting blinking should be stoppable / end within 5 s. The sports plugins already made their celebration flash opt-in for photosensitivity (plugins #136).

Sources: [alphasign modes](https://alphasign.readthedocs.io/en/latest/modes.html) · [AlphaSign::Format](https://www.rubydoc.info/gems/alphasign/AlphaSign/Format) · [BetaBrite Prism manual](https://daylight.net/manuals/betabrite-prism-programming.pdf) · [BetaBrite Window manual](https://www.alpha-american.com/alpha-manuals/M-BetaBrite-Window-Display-User-Manual.pdf) · [FastLED TwinkleFOX](https://gist.github.com/kriegsman/756ea6dcae8e30845b5a) · [WLED effects](https://kno.wled.ge/features/effects/) · [WLED FX.cpp](https://raw.githubusercontent.com/wled/WLED/main/wled00/FX.cpp) · [Adafruit LED Animation](https://docs.circuitpython.org/projects/led-animation/en/latest/api.html) · [blink element](https://en.wikipedia.org/wiki/Blink_element) · [Vixen Snowflakes](https://www.vixenlights.com/docs/usage/sequencer/effects/pixel/snowflakes/) · [tsParticles snow](https://raw.githubusercontent.com/tsparticles/presets/main/presets/snow/src/options.ts) · [WCAG 2.3.1](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html) · [WCAG 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html).
Confidence note: the one-line Alpha SNOW/TWINKLE semantics come from a brochure summary (primary PDF 403'd); mode names/codes are primary.

---

## 1. `flair.blink` — animation (no core change)

**Slot:** `animation = "flair.blink"` / `{style = "flair.blink", ...}`. Hosts: `message`, `gif`, `image` (core's animation host set).

**Mechanism:** `frame_for` returns `AnimationFrame(visible_text=full_text)` in the on phase and `visible_text=""` in the off phase. Core already handles sliced `visible_text` with full-width cursor math (typewriter). Border and background keep painting during off (only the text blanks) — matches "off = blank to background".

**Params** (WLED/Adafruit/`<blink>` shaped):

| Knob | Default | Notes |
|---|---|---|
| `period_ms` | `1000` | one on+off cycle. Rounded to ENGINE_TICK_MS (50 ms) frames. |
| `duty` | `0.75` | fraction ON (Firefox `<blink>`). `(0, 1)` exclusive. |
| `count` | `0` | blinks then stays ON; 0 = blink for the whole hold. Alpha "flash then move on" / WCAG 2.2.2. |
| `allow_fast` | `false` | photosensitivity opt-in; required below about 850 ms (17 frames), judged at the fastest 20 ms engine cadence (>3 Hz otherwise). |

**Invariants:**
- Frame 0 is ON (every visit opens readable; `restart_on_visit = True`).
- `frames_to_rest(frame, n)` returns frames until the next ON frame (0 when on). A hold ending mid-off would otherwise freeze a blank outgoing frame through the whole transition (`pause_frame`).
- Rate guard at construction: `period < 17 frames (about 850 ms) and not allow_fast` → `ValueError` naming WCAG 2.3.1 and the opt-in.
- `emits_rotation = False`, no lens.

**Known limits (call out in docs):**
- Image widgets refuse any non-lens animation with `text_align = "scroll"/"scroll_over"` (`_image_base.__attrs_post_init__`). A blinking marquee over an image needs a core marker (e.g. `allows_scroll = True` duck-type, mirroring `emits_lens`). **My call: ship without it; add the marker only if wanted.**
- `two_row` has no animation slot, so the classic "flashing NEWS FLASH top row, scrolling headline bottom" can't use this. That's an argument for a core `top_animation`/`bottom_animation` (or a per-row blink knob) — **out of scope for v1, flagged for later.**
- `strobe` (single-frame on bursts) is deliberately NOT a knob value; if wanted later it's its own style and always requires `allow_fast`.
- Verify in tests: empty `visible_text` on the inline-emoji path and with colored value tokens (`build_token_color_override` on an empty slice).

## 2. `flair.twinkle` — the core-vs-flair decision

"Random lit pixels dim and flicker" = Alpha TWINKLE: the **text's own pixels**. No existing seam reaches individual text pixels:
- color providers are per-character (`color_for(frame, char_index, total)`),
- `background` paints *under* the text,
- there's no GetPixel to read back what was drawn.

### 2.1 Option A — per-character twinkle color provider (flair, no core change)
`font_color = {style = "flair.twinkle", base = [...], ...}` via `api.color_provider`. Each character independently dims/flickers on a TwinkleFOX clock. Cheap, composes with every host that takes `font_color` (including `two_row` rows). But it's coarse (a whole letter dims, not pixels), can't combine with rainbow (same slot), and is close to the existing `shimmer`.

### 2.2 Option B — twinkle starfield background (flair, no core change)
`background = "flair.twinkle"`: dim stars flicker *behind* the text. Clearly useful and trivial on the existing seam, but it's a different effect — it adds pixels rather than dimming the text's.

### 2.3 Option C — per-pixel text twinkle (needs a small core seam)
Core adds an optional pixel-modulation hook to the text draw: e.g. `AnimationFrame.pixel_gain: Callable[[x_real, y_real], float] | None`. When set, the widget draws its text through a thin SetPixel proxy that multiplies each lit pixel's RGB by `gain(x, y)` (proxy installed as the innermost `.real` so both the BDF/ScaledCanvas path and the hi-res `unwrap_to_real` path go through it; border/background painted outside it). flair supplies the TwinkleFOX gain function. Cost: one multiply per text pixel per tick.

Sub-decisions under C: emoji twinkle too (my default: yes — they're "lit pixels of the message"); occupies the `animation` slot, so it can't combine with typewriter/fisheye/blink (a dedicated `text_effect` slot avoids that but is a much bigger core change).

A flair-only variant of C (a `TickerMessage` subclass that rasters via `_raster.py` and re-paints with gain) exists but twinkles the border/background too, double-paints, and needs a new `type` — rejected (anti-goal).

### 2.4 Decision — **C + B** (James, 2026-11-09)
**C + B**: per-pixel text twinkle is the industry meaning and is the only option that looks like it; the core seam is small, generic (future "glitch", "scanline", "dim-toward-red" effects reuse it), and mirrors how `LensSpec` landed. B is nearly free and covers "sparkly night sky behind the text". Skip A (overlaps shimmer). If you'd rather keep core untouched, ship B (+ optionally A) and defer C.

### 2.5 Twinkle params (shared by B and C)
| Knob | Default | Notes |
|---|---|---|
| `density` | C: `0.6`; B: `0.03` | C: fraction of text pixels twinkling (TwinkleFOX 5/8). B: fraction of real panel pixels that are stars. |
| `speed` | `1.0` | multiplier on base cycle (~1.2 s per twinkle at 1.0); max `2.0`. |
| `min_brightness` | `0.15` | trough of the dim (C only — never fully off; C must not read as blinking). |
| `color` | warm white | B (background) only: star color. The C (animation) variant has no tint knob (not built). |
| `seed` | none | reproducibility, same semantics as `flair.fireworks`. |

Note: the text-twinkle `color` tint knob was dropped from v1 (the background keeps its star `color`).

**Mechanism (TwinkleFOX):** no per-pixel state — per pixel, hash `(x, y, seed)` to a clock offset and a speed in 8/8–23/8 of base; brightness is an asymmetric triangle (fast attack ⅓, slow decay ⅔) of `(frame*speed + offset)`. Pure function of `(x, y, frame)`. Twinkle on/off rates per pixel stay well under 3 Hz; it's dimming, not full-luminance flashing, and pixels are desynchronized, so WCAG 2.3.1 is not at risk at default/max `speed` (cap `speed ≤ 2`, keeping every pixel's cycle ≥ 6 frames). On scaled signs BDF text twinkles per logical pixel (one 4×4 block = one twinkler); hi-res glyphs per real pixel.

## 3. `flair.snow` — background

**Slot:** `background = "flair.snow"`. Hosts: core's background host set. Same name registered as a transition (§4), exactly like `flair.fireworks`.

**Params** (Vixen/tsParticles shaped):

| Knob | Default | Notes |
|---|---|---|
| `flake` | `"dot"` | `"dot"` (1 real px), `"plus"` (3×3 +), `"flake"` (built-in 5×5 snowflake), or an emoji slug (`"snow"`, `"pumpkin"`, …). |
| `density` | `3.0` | flakes per 1000 real px² (smallsign 8, longboi 25, bigsign 49). |
| `speed` | `1.0` | fall speed multiplier, normalized to panel height (~5 s to cross at 1.0 on every sign); per-flake ±`speed_variation` (default 0.4). |
| `drift` | `0.3` | horizontal wobble amplitude (sine, per-flake phase). |
| `wind` | `0.0` | constant horizontal slant. |
| `color` | `[200, 220, 255]` | dot/plus only; emoji keep their own colors. Per-flake random intensity 0.5–1.0. |
| `seed` | none | as fireworks. |

**Invariants (copied from fireworks-background):** pure function of `(real dims, frame)` via per-flake seeded hash + epoch wraparound (flake re-enters at top with a new x after leaving the bottom); never paints black (`_LightOnly`-style proxy); `frame_invariant = False`, `restart_on_visit = False`; paints at physical resolution on `unwrap_to_real`.

**Flake-size trap:** `:snow:` hi-res is 32×32 (half the bigsign) and the 8×8 low-res block-expands to 32 real px at scale 4. Emoji flakes therefore paint the **low-res 8×8 sprite 1:1 at physical resolution** (8 real px on the bigsign, 8 px on smallsign — readable, flake-sized). Sprite pixels are captured once and cached (stickers' plan-time-raster pattern). Slugs validated via `emoji_slugs()`; pack-only (hires-only) slugs are refused for `flake` with a hint (no 8×8). **No accumulation in v1** (Vixen default off; build-up needs memory across frames, which is the stateful-sim anti-goal).

## 4. `flair.snow` — transition

Your words: flakes float in the **foreground** during the transition. Alpha's "pile up into the new text" is noted as precedent and offered as a mode, not the default.

**Default mode `"flurry"`:** a dense snowfall in the foreground covers the cut.
- Snapshot both widgets once per firing into `_raster.py` Rasters (laser/accordion snapshot-only pattern; no live redraw after snapshot).
- A falling "front" — the flakes' leading band, top→bottom across `[0, SNAP_THRESHOLD)` — switches each real pixel from outgoing to incoming as the front passes (a jagged, per-column-jittered line so it reads as snow, not a wipe). Flakes paint on top throughout, peak density mid-transition, thin out at the end.
- This avoids needing a whiteout at t = 0.5 to hide a hard cut (a sparse flurry can't hide one).

**Optional mode `"build"` (Alpha SNOW):** outgoing melts/falls away, then flakes fall and land on the incoming snapshot's lit pixels, building the text bottom-up. Target pixels come from the incoming Raster, so no GetPixel. **My call: v1 ships `flurry` only; `build` is a follow-up if you like the flurry.**

**Params:** `flake`, `density`, `drift`, `wind`, `color`, `seed` (same meanings as §3), `mode` (`"flurry"`).

**Idioms:** `unwrap_to_real` every call; refire on `t == 0.0 or t < _last_t`; `snap_reset(canvas, incoming_bg_color)` + `incoming.draw` at `SNAP_THRESHOLD`; `min_frames = 24`; `scale_switch_at = 1.0` (hard-edged family convention, as laser); perf bounded by panel px + flakes per frame.

---

## 5. Where it lives

| Piece | Home | Core change |
|---|---|---|
| `flair.blink` animation | flair | none (optional `allows_scroll` marker later) |
| `flair.twinkle` background (B) | flair | none |
| `flair.twinkle` text (C) | flair + core seam | `AnimationFrame.pixel_gain` + text-draw proxy (message, image single-row); validate + docs |
| `flair.snow` background | flair | none |
| `flair.snow` transition | flair | none |

Name collision note: if C lands, `flair.twinkle` exists in both the animation and background registries — fine (fireworks precedent), but the docs must say which slot does what.

## 6. Deliverables per effect

- Module under `src/led_ticker_flair/flair/`, registered in `flair/__init__.py`; `_import_seam` probe + `led-ticker-core` floor bump if C lands.
- Tests: pure-function-of-frame, never-paints-black (backgrounds), physical-resolution (`TestScaledCanvas` pattern), photosensitivity guard (blink), `frames_to_rest` (blink), snapshot-only + refire + snap (snow transition), perf bound on bigsign dims; `_RecordingAPI` fakes updated; import-purity.
- CLAUDE.md invariants section per effect; README entries.
- Smoke configs for smallsign / bigsign / longboi; demo gifs (render-demo bigsign geometry note applies).
- Core docs-site catalogue entries (transitions / backgrounds / animations pages).

## 7. Calls I made (check these)

1. Blink "off" blanks text only; border/background keep painting.
2. Blink defaults 1 Hz / 0.75 duty; >3 Hz (under 17 frames, about 850 ms) refused without `allow_fast`.
3. No blink-on-scroll for image widgets and no two-row blink in v1 — closed in §8 right after merge.
4. Twinkle C + B (decided by James).
5. Emoji snow flakes paint the 8×8 low-res sprite 1:1 at physical res; hires-only pack slugs refused.
6. No snow accumulation in v1.
7. Snow transition ships `flurry` (falling front swaps outgoing→incoming); Alpha-style `build` deferred.

## 8. Phasing

**Phase 1 (v1, core first then flair):**
1. Core PR (led-ticker): `AnimationFrame.pixel_gain` seam + text-draw proxy on `message` and image single-row overlay; validate + docs + tripwires. Released as a core minor.
2. Flair PR (led-ticker-plugins): `flair.blink`, `flair.twinkle` (animation, needs the new core floor + `_import_seam` probe), `flair.twinkle` background, `flair.snow` background + transition.

**Phase 2 (gaps, immediately after Phase 1 merges):**
- **Image-widget scrolling + non-typewriter animations.** Replace the `emits_lens` special case in `_image_base` with a general duck-typed capability marker (e.g. `allows_scroll = True`) set by lens, blink, and twinkle; typewriter keeps refusing scroll modes. validate mirrors it.
- **Two-row animations.** Core adds per-row `top_animation` / `bottom_animation` on `two_row` (and the image two-row overlay, keeping `TestFieldSurfaceMatchesTwoRow` in sync), following the `top_`/`bottom_` prefix convention. Scope: animations that don't change layout (blink, twinkle); typewriter/lens/rotation refused per row at config-load. Enables the "flashing NEWS FLASH over a scrolling headline" layout.
- **`flair.snow` `mode = "build"`** (Alpha SNOW pile-into-text) if the flurry lands well.
