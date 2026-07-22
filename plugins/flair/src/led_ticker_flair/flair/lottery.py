"""flair.lottery — lottery-ball roll animation.

N labeled balls roll in from off-canvas left in a staggered relay (one ball
after another, each on its own ``ticks_per_ball``-tick window) and settle
flat into evenly spaced slots across the panel. Entry order is RACK-FILL,
not left-to-right: the first ball to roll lands in the RIGHTMOST slot, the
next stops one slot short, and so on — so no ball ever rolls through an
already-settled one. Reveal order is therefore right-to-left (the last
config word lands first), but word index always equals slot index, so the
FINAL display still reads the config's ``words`` left-to-right unchanged.
``roll_order_for_slot`` is the (self-inverse) mapping between a slot's
index and its temporal roll order; ``ball_phase`` itself stays pure
per-ball math, agnostic to which slot owns which window. The ``Lottery``
widget follows the same two-surface blit design as ``flair.propeller`` /
``flair.fisheye``: each ball is painted ONCE onto its own
``RotationSurface`` at its slot position, then re-blitted every tick at
the angle/translation this module's geometry functions compute, until it
settles exactly flat at 0 degrees onto a shared ``_rest_surface``
composite. Everything above ``Lottery`` (``layout``, ``ball_phase``,
``roll_order_for_slot``, ``auto_font_size``, ``paint_face``) is pure
geometry/paint math with no widget-lifecycle concerns; no core imports
beyond the public ``led_ticker.plugin`` surface.

Blit-geometry finding (verified against core's ``rotate.rotate_blit``,
whose forward map is ``dst = R(src - c) + c + t``): passing the ball's
own painted SLOT center as ``cx_logical`` (the pivot) makes the face spin
about itself, and ``dx_logical = current_cx - slot_cx`` (the ``RotationSurface.blit``
seam's translation) slides that spinning face to the rolling position.
Both are logical px; ``rotate_blit``'s ``t`` folds in cleanly because the
pivot and the translation are independent terms in the same forward map.

``draw()``'s ``y_offset`` renders the CURRENT roll frame shifted via
``dy_logical`` (core ``>=4.10``, same seam as ``dx_logical``) — every
``blit()`` call forwards ``dy_logical=float(y_offset)``, so a push
transition (which draws this widget at a range of ``y_offset`` values)
sees exactly the same content a plain ``y_offset=0`` draw at that frame
would show, translated. There is no separate "paint everything settled"
path for the transition case.
"""

import logging
import math
import types
from typing import Any

import attrs
from led_ticker.plugin import (
    ENGINE_TICK_MS,
    Canvas,
    DrawResult,
    FrameAwareBase,
    ValidationContext,
    compute_baseline_for_band,
    draw_with_emoji,
    get_text_width,
    is_scaled,
    make_color,
    make_rotation_surface,
    paint_hires,
    pixel_native_size,
    resolve_font,
    unwrap_to_real,
)

logger = logging.getLogger("led_ticker_flair")

# The 8 spec auto-palette colors, in spec order (red, green, amber, blue,
# magenta, cyan, orange, violet) — assigned to balls in order when
# ``ball_style == "solid"`` (widget concern; this module just ships the
# constant tuple future tasks index into).
PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 60, 60),  # red
    (60, 220, 60),  # green
    (255, 180, 0),  # amber
    (80, 140, 255),  # blue
    (255, 80, 255),  # magenta
    (0, 220, 220),  # cyan
    (255, 120, 40),  # orange
    (170, 90, 255),  # violet
)

# Physical-pixel gap between adjacent ball slots (spec constant, verbatim).
_GAP_PX = 4

# Text chord factor: usable text width as a fraction of ball diameter.
_CHORD_FACTOR = 0.72

# Largest candidate font size is this fraction of the ball diameter.
_MAX_FONT_FACTOR = 0.45

# Floor below which glyphs are unreadable (also the HiresFont size floor
# enforced by ``resolve_font``).
_MIN_FONT_SIZE = 8

# Ball-face text is always SMALL (a ~13px word inside a ~56px ball), and small
# hi-res Inter at the default rasterization threshold (128 = 50% coverage)
# drops thin-stroke pixels — on hardware "GYRO" read as "BYRD" (halal-cart
# sign, 2026-07-16). 80 is the ecosystem's established thin-stroke threshold
# (the same value the reference configs use for small hi-res text); applying
# it here keeps every stroke of every ball label. Both the fit measurement
# (auto_font_size) and the paint (paint_face) resolve with the SAME threshold
# so they share one font-cache entry and can never disagree.
_FACE_THRESHOLD = 80

# Style constants (spec, verbatim) — classic face is white with a dark
# label; solid face is color-filled with a white label.
_CLASSIC_FACE_RGB = (255, 255, 255)
_CLASSIC_TEXT_RGB = (10, 10, 10)
_SOLID_TEXT_RGB = (255, 255, 255)

# `get_text_width`'s scale divisor only matters for its logical-width
# conversion; a scale=1 stub makes it return the raw real-pixel width
# (see `auto_font_size`'s docstring for why that's what we need here).
# Shared by `auto_font_size` and `paint_face` so both measure the same way.
_REAL_SCALE1_STUB = types.SimpleNamespace(scale=1)


def layout(n: int, panel_w: int, panel_h: int, inset: int) -> tuple[int, list[int]]:
    """Compute ball diameter + slot center-x positions for ``n`` balls.

    All units are REAL (physical) pixels — the balls paint directly to the
    real canvas (bypassing the ``ScaledCanvas`` scale wrapper, same as
    hi-res emoji), so their geometry must be computed in the same space
    the panel itself is measured in.

    ``diameter = min(panel_h - 2*inset, panel_w // n - GAP)`` — the ball
    must fit the inset vertical band AND its even share of the horizontal
    width (minus the inter-slot gap). Slots are evenly spaced with
    ``_GAP_PX`` between them and centered as a group within ``panel_w``.
    """
    diameter = min(panel_h - 2 * inset, panel_w // n - _GAP_PX)
    total_width = n * diameter + (n - 1) * _GAP_PX
    start_x = (panel_w - total_width) // 2
    stride = diameter + _GAP_PX
    slot_centers = [start_x + i * stride + diameter // 2 for i in range(n)]
    return diameter, slot_centers


def ticks_per_ball(roll_ms: int) -> int:
    """Engine ticks a single ball's roll-in takes, at least 1.

    ``ENGINE_TICK_MS`` (50ms, imported from the public core surface rather
    than hardcoded) is the held-text tick cadence every frame-aware widget
    animates on.
    """
    return max(1, roll_ms // ENGINE_TICK_MS)


def ball_phase(
    frame: int, index: int, ticks_per_ball: int, diameter: int, slot_cx: int
) -> tuple[float, float, bool]:
    """Roll-timeline state for ball ``index`` at engine tick ``frame``.

    Balls roll in a staggered relay: ball ``index`` owns the tick window
    ``[index * ticks_per_ball, (index + 1) * ticks_per_ball)``.

    - Before its window: parked off-canvas left at ``cx = -diameter``,
      angle ``0.0``, not settled.
    - During its window: eased travel (cubic ease-out,
      ``t_eased = 1 - (1 - t) ** 3``) from the launch position
      ``-diameter / 2`` to ``slot_cx``. The face angle is the remaining
      travel distance (in ball-radii) converted to degrees and negated —
      a leftward-entry roll spins the face so it continuously unwinds
      toward, and lands at EXACTLY, 0 degrees when ``cx`` reaches
      ``slot_cx`` (remaining == 0).
    - After its window: settled — ``(slot_cx, 0.0, True)``.

    Returns ``(cx_px, angle_deg, settled)``.
    """
    start = index * ticks_per_ball
    end = start + ticks_per_ball

    if frame < start:
        return -float(diameter), 0.0, False
    if frame >= end:
        return float(slot_cx), 0.0, True

    t = (frame - start) / ticks_per_ball
    t_eased = 1.0 - (1.0 - t) ** 3

    launch_cx = -diameter / 2
    cx = launch_cx + t_eased * (slot_cx - launch_cx)

    radius = diameter / 2
    remaining = slot_cx - cx
    angle = -math.degrees(remaining / radius) if radius else 0.0
    return cx, angle, False


CHOREOGRAPHIES = ("rack_fill", "roll_through")


def roll_order_for_slot(
    slot_index: int, n: int, choreography: str = "rack_fill"
) -> int:
    """Map a slot index to its roll order (temporal entry order), or vice
    versa — BOTH mappings are self-inverse (``n - 1 - i`` and identity), so
    this one function converts in either direction for either mode.

    ``"rack_fill"`` (default): the FIRST ball to roll (roll order 0) targets
    the RIGHTMOST slot (``n - 1``); the next stops one slot short; and so
    on, so no ball ever rolls through an already-settled one.

    ``"roll_through"``: roll order == slot index — balls fill left-to-right
    in config order, and a later ball visibly rolls in front of (over) the
    already-settled balls it passes. The original v0.5.0-dev look, kept as
    an opt-in.

    In BOTH modes word index always equals slot index (the final display
    reads the config's ``words`` left-to-right, unchanged) — only the TIMING
    of which slot's ball rolls first differs.
    """
    if choreography == "roll_through":
        return slot_index
    return n - 1 - slot_index


def auto_font_size(word: str, diameter_px: int, font_name: str, scale: int) -> int:
    """Largest hi-res font size whose rendered ``word`` fits the ball face.

    For an OUTLINE font (``pixel_native_size(font_name)`` is ``None``),
    searches ``size`` continuously from ``int(diameter_px * 0.45)`` down to
    ``_MIN_FONT_SIZE`` (8, the ``resolve_font`` legibility floor) and
    returns the first (largest) size whose rendered width fits
    ``diameter_px * _CHORD_FACTOR`` (0.72 — the usable text-width chord of
    a circle).

    For a PIXEL font (e.g. Spleen), an off-grid size renders blurry — only
    integer multiples of the font's native cell size are crisp. The search
    is restricted to those multiples, largest first: from the largest
    native multiple ``<= int(diameter_px * 0.45)`` down to ``native``
    itself. If even ``native`` doesn't fit, falls straight through to 0
    rather than ever resolving an off-grid size.

    Returns 0 if not even the floor size fits (caller treats that as
    "doesn't fit — fall back / truncate / error", widget concern).

    Unit note on ``get_text_width`` and the ``scale`` argument: for a
    HiresFont, ``get_text_width`` sums REAL-pixel glyph advances (font
    ``size`` is always a real-pixel target — see ``resolve_font``) and
    then divides by ``canvas.scale`` to convert to LOGICAL pixels for
    layout math elsewhere in core (``canvas=None`` falls back to
    ``SCALE_FALLBACK=4``). Here ``diameter_px`` is a REAL-pixel
    measurement (balls paint directly to the real canvas), so we need the
    RAW real-pixel width, not a scale-divided logical approximation —
    dividing by the widget's real scale before comparing to a REAL
    diameter would let the search accept oversized fonts (verified: at
    diameter=56/scale=4 the naive "forward the real scale" approach picks
    size=25, whose ACTUAL real-pixel width is 77px — comfortably wider
    than the 56px ball). We deliberately pass a ``canvas`` stub with
    ``scale=1`` (a no-op divisor) so ``get_text_width`` returns the true
    real-pixel width, matching the size=13 fit that visually fits the
    chord. ``scale`` is still accepted (part of the locked public
    interface a future widget task calls with its real canvas scale) and
    is validated defensively even though it doesn't feed the fit
    computation.
    """
    if not isinstance(scale, int) or isinstance(scale, bool) or scale < 1:
        raise ValueError(f"scale must be an int >= 1; got {scale!r}")

    threshold = diameter_px * _CHORD_FACTOR
    ceil = int(diameter_px * _MAX_FONT_FACTOR)
    native = pixel_native_size(font_name)
    if native is not None:
        # Pixel font: only native multiples render crisp — search those,
        # largest first. If even `native` overflows, fall through to 0.
        candidates = range(ceil - (ceil % native), native - 1, -native)
    else:
        # Outline font: continuous search (unchanged).
        candidates = range(ceil, _MIN_FONT_SIZE - 1, -1)
    for size in candidates:
        font = resolve_font(font_name, size, _FACE_THRESHOLD)
        width = get_text_width(font, word, padding=0, canvas=_REAL_SCALE1_STUB)
        if width <= threshold:
            return size
    return 0


def paint_face(
    target,
    *,
    cx_logical: float,
    cy_logical: float,
    r_px: int,
    style: str,
    color: tuple[int, int, int],
    word: str,
    font_name: str,
    scale: int,
    warn_unfittable: bool = True,
) -> None:
    """Paint one lottery-ball face onto ``target``.

    ``target`` is a rotation-surface's ``.target`` (a full-canvas
    ``ScaledCanvas``, per ``led_ticker.rotate.RotationSurface`` — draw
    into it in logical coordinates, then ``snapshot()`` + ``blit()`` it)
    or any other canvas-alike; ``paint_hires``/``draw_with_emoji`` work
    on either.

    MIXED UNITS, deliberately (the same split hi-res emoji/fonts already
    straddle): ``cx_logical``/``cy_logical`` are LOGICAL coordinates —
    the widget's own drawing space. ``r_px`` is the ball radius in REAL
    (physical) pixels — the circle paints directly to the real canvas
    via ``paint_hires`` (bypassing the ``ScaledCanvas`` block expansion,
    same as hi-res emoji/fonts), so its geometry must be in real-pixel
    units to render a crisp circle rather than a blocky
    ``scale``-sized-square approximation. ``scale`` is the canvas's
    real/logical ratio, needed to convert the real-pixel measurements
    (radius, text width) back to the logical coordinates ``target``
    draws in.

    Style ``"classic"``: white ``(255,255,255)`` face, a ``color``
    ring band ``max(1, r_px // 8)`` px wide at the rim, dark
    ``(10,10,10)`` text. Style ``"solid"``: ``color``-filled face,
    white ``(255,255,255)`` text. Any other ``style`` raises
    ``ValueError``.

    The word is centered on the face: horizontally by measuring its
    REAL-pixel width (the same scale=1 measurement ``auto_font_size``
    uses — see its docstring) and centering that on ``cx_logical``;
    vertically via ``compute_baseline_for_band``, treating the ball's
    real diameter (converted to a logical band height) as the text
    band — this accounts for the resolved font's actual ascent/descent
    rather than a hardcoded midpoint guess.

    If ``auto_font_size`` reports the word doesn't fit (returns 0 — the
    widget's config validation should already have caught this at
    preflight), the circle is still painted but the word is skipped;
    logs one WARNING via the ``"led_ticker_flair"`` logger as a
    belt-and-braces render-time guard, unless ``warn_unfittable=False``
    (the ``Lottery`` widget passes this after the first per-word warning
    so a rebuild on every re-roll doesn't re-log the same word forever —
    see its ``_warned_words`` latch).
    """
    if style not in ("classic", "solid"):
        raise ValueError(
            f"paint_face: style must be 'classic' or 'solid'; got {style!r}"
        )

    is_classic = style == "classic"
    ring_w = max(1, r_px // 8)
    face_rgb = _CLASSIC_FACE_RGB if is_classic else color
    text_rgb = _CLASSIC_TEXT_RGB if is_classic else _SOLID_TEXT_RGB

    def _paint_circle(real, real_scale, y_offset_real):
        cx_p = cx_logical * real_scale
        cy_p = cy_logical * real_scale + y_offset_real
        r2 = r_px * r_px
        ring_r2 = max(0, r_px - ring_w) ** 2

        x0 = max(0, math.floor(cx_p - r_px))
        x1 = min(real.width - 1, math.ceil(cx_p + r_px))
        y0 = max(0, math.floor(cy_p - r_px))
        y1 = min(real.height - 1, math.ceil(cy_p + r_px))

        for py in range(y0, y1 + 1):
            dy2 = (py - cy_p) ** 2
            for px in range(x0, x1 + 1):
                d2 = (px - cx_p) ** 2 + dy2
                if d2 > r2:
                    continue
                if is_classic and d2 >= ring_r2:
                    r, g, b = color
                else:
                    r, g, b = face_rgb
                real.SetPixel(px, py, r, g, b)

    paint_hires(target, _paint_circle)

    diameter_px = 2 * r_px
    size = auto_font_size(word, diameter_px, font_name, scale)
    if size == 0:
        if warn_unfittable:
            logger.warning(
                "flair.lottery: word %r does not fit a %dpx ball face "
                "(font=%s) — painting the ball without a label",
                word,
                diameter_px,
                font_name,
            )
        return

    font = resolve_font(font_name, size, _FACE_THRESHOLD)
    real_width = get_text_width(font, word, padding=0, canvas=_REAL_SCALE1_STUB)
    x_logical = round(cx_logical - real_width / (2 * scale))

    diameter_logical = round(diameter_px / scale)
    band_top_logical = cy_logical - diameter_logical / 2
    baseline_offset = compute_baseline_for_band(font, diameter_logical, scale, "center")
    baseline_logical = round(band_top_logical + baseline_offset)

    draw_with_emoji(
        target, font, x_logical, baseline_logical, make_color(*text_rgb), word
    )


# ---------------------------------------------------------------------------
# Lottery widget (Task 3)
# ---------------------------------------------------------------------------

# Inset (real px) between a ball's edge and the vertical content band —
# tighter (1px) with no border since there's nothing else to clear; wider
# (3px) with a border painted so the ball doesn't collide with the ring.
_INSET_NO_BORDER = 1
_INSET_WITH_BORDER = 3


def _font_is_a_name(_inst, _attr, value):
    """`font` selects the ball-face font by NAME.

    ``Lottery`` sets ``RESOLVES_OWN_FONT = True``, which tells core's
    ``_resolve_fonts`` to leave a config-set ``font`` as the raw NAME
    string instead of coercing it to a Font object — the widget re-resolves
    that name itself at each auto-computed size (``auto_font_size`` /
    ``paint_face``), so it needs the name, not a pre-sized object.

    This validator only confirms the name is real: a non-string still
    raises (a stray Font/HiresFont object would mean ``RESOLVES_OWN_FONT``
    stopped being honored, or a caller bypassed it), and an unknown name
    raises via ``resolve_font`` itself (``UnknownFontError``, a ``ValueError``
    subclass whose message lists every known font — the same error a typo
    in any other widget's ``font`` gets). The probe resolves at the
    legibility floor (``_MIN_FONT_SIZE``) purely to validate the name; the
    render path re-resolves at the actual fit size, so the object built
    here is discarded.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"flair.lottery: 'font' must be a font name string, got "
            f"{type(value).__name__} ({value!r}) — RESOLVES_OWN_FONT should "
            "have kept it a raw name; the lottery re-resolves it itself at "
            "each auto-computed ball size."
        )
    resolve_font(value, _MIN_FONT_SIZE, _FACE_THRESHOLD)


@attrs.define
class Lottery(FrameAwareBase):
    """N labeled balls roll in from off-canvas left, one at a time in
    rack-fill order (first entrant lands rightmost, no ball ever crosses a
    settled one), and settle flat into evenly spaced slots (a physical
    lottery-ball draw). Reveal is right-to-left; the final display still
    reads ``words`` left-to-right.

    Requires a scaled display (``default_scale > 1`` — bigsign): the balls
    paint at physical resolution via ``paint_hires``/``RotationSurface``,
    the same hi-res-only design as inline hi-res emoji. On a scale-1
    canvas (smallsign), ``draw`` logs once and paints nothing.

    Render design: each ball owns a construct-once ``RotationSurface``
    (spec R2/R3 lifecycle) painted ONCE per visit with its face at its
    SLOT position; every tick the currently-rolling ball is re-blitted
    with ``RotationSurface.blit(canvas, angle, slot_cx, dx_logical=...)``
    — pivoting about its own painted slot center (so it spins about
    itself) and translating by the remaining travel distance (so it
    rolls). A ball settles by compositing its face into a second shared
    ``_rest_surface`` (once per settle event, not per frame) so already-
    settled balls cost one flat blit per tick regardless of ``n``.
    """

    # Opts out of core's font-name -> Font-object coercion (`_resolve_fonts`
    # in `app/factories.py`, core >=4.27): `font` stays the raw NAME string
    # config set (or the "Inter-Bold" default), and core doesn't require a
    # `font_size` alongside it. The widget re-resolves that name itself at
    # each auto-computed size (`auto_font_size` / `paint_face`) — it never
    # holds a single pre-sized Font object. Plain unannotated class
    # attribute: `@attrs.define` only turns annotated names into fields, so
    # this is inert to attrs (verified against core's own
    # `test_resolves_own_font_leaves_raw_name`).
    RESOLVES_OWN_FONT = True

    words: list[str]
    ball_style: str = "classic"
    colors: Any = None
    roll_ms: int = 800
    font: str = attrs.field(default="Inter-Bold", validator=_font_is_a_name)
    # Entry order: "rack_fill" (first entrant lands rightmost, no crossings)
    # or "roll_through" (left-to-right fill; later balls roll over settled
    # ones). See roll_order_for_slot.
    choreography: str = "rack_fill"
    border: Any | None = attrs.field(default=None, kw_only=True)
    # Layout-contract field; inert for a held full-panel widget — the engine
    # never scrolls this widget (draw() always returns cursor_pos == 0).
    end_padding: int = 0

    # Resolved per-ball ring/fill colors: `colors` verbatim (as tuples) when
    # given, else the PALETTE cycled in ball order — computed once at
    # construction so draw()/rebuilds never re-decide it.
    _resolved_colors: list[tuple[int, int, int]] = attrs.field(init=False, factory=list)

    # Per-ball construct-once rotation surfaces (one per word) + the shared
    # "already settled" composite. Both are dropped (set to None) by
    # `reset_frame` to force a from-scratch rebuild (= the re-roll) on the
    # next visit; `_ensure_built` recreates them lazily.
    _surfaces: list[Any] | None = attrs.field(init=False, default=None)
    _rest_surface: Any = attrs.field(init=False, default=None)
    # Cache key `_ensure_built` compares against to decide whether the
    # existing surfaces still match the live canvas's geometry (a shared
    # widget instance can be drawn under different scale/content_height
    # across sections — same guard shape as `RotationSurface.matches()`).
    _built_for: tuple[int, int, int, int] | None = attrs.field(init=False, default=None)
    _settled: list[bool] = attrs.field(init=False, factory=list)
    _slot_centers_px: list[int] = attrs.field(init=False, factory=list)
    _slot_cx_logical: list[float] = attrs.field(init=False, factory=list)
    _diameter_px: int = attrs.field(init=False, default=0)
    _r_px: int = attrs.field(init=False, default=0)
    _cy_logical: float = attrs.field(init=False, default=0.0)
    _tpb: int = attrs.field(init=False, default=1)
    # Scale-1 guard: latch so the "requires a scaled display" log fires
    # once per instance, not once per tick.
    _warned_scale: bool = attrs.field(init=False, default=False)
    # Unfittable-word latch: `paint_face` would otherwise re-log the same
    # word's WARNING on every re-roll rebuild (each visit rebuilds the
    # surfaces from scratch). Persists across `reset_frame` (NOT dropped
    # with the surfaces) since it's about the word/font/diameter
    # combination, not about a specific surface generation.
    _warned_words: set[str] = attrs.field(init=False, factory=set)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Preflight (error-severity) checks, run before widget construction.

        ``cfg`` is the raw per-widget TOML dict (not yet attrs-coerced) —
        see core's ``validate_widget_cfg``. Returns error strings; an empty
        list means the config is constructible.
        """
        errors: list[str] = []
        words = cfg.get("words")
        if not isinstance(words, list) or not words:
            errors.append("words is required and must be a non-empty list of strings")
        else:
            if len(words) > 8:
                errors.append(f"words supports at most 8 balls, got {len(words)}")
            if not all(isinstance(w, str) and w for w in words):
                errors.append("words must contain only non-empty strings")

        colors = cfg.get("colors")
        if colors is not None:
            if not isinstance(colors, list):
                errors.append(
                    "colors must be a list of [r, g, b] triples, "
                    f"got {type(colors).__name__}"
                )
            else:
                if isinstance(words, list) and len(colors) != len(words):
                    errors.append(
                        f"colors has {len(colors)} entries but words has "
                        f"{len(words)} — they must be the same length"
                    )
                for entry in colors:
                    if not (
                        isinstance(entry, list | tuple)
                        and len(entry) == 3
                        and all(
                            isinstance(v, int)
                            and not isinstance(v, bool)
                            and 0 <= v <= 255
                            for v in entry
                        )
                    ):
                        errors.append(
                            f"colors entry {entry!r} must be an [r, g, b] triple "
                            "of ints 0-255"
                        )

        ball_style = cfg.get("ball_style", "classic")
        if ball_style not in ("classic", "solid"):
            errors.append(f"ball_style {ball_style!r} must be 'classic' or 'solid'")

        choreography = cfg.get("choreography", "rack_fill")
        if choreography not in CHOREOGRAPHIES:
            errors.append(
                f"choreography {choreography!r} must be one of {CHOREOGRAPHIES}"
            )

        roll_ms = cfg.get("roll_ms", 800)
        if isinstance(roll_ms, bool) or not isinstance(roll_ms, int) or roll_ms < 100:
            errors.append(f"roll_ms must be an integer >= 100, got {roll_ms!r}")

        return errors

    @classmethod
    def validate_config_warnings(
        cls, cfg: dict[str, Any], ctx: ValidationContext
    ) -> list[str]:
        """Advisory (warning-severity) preflight checks.

        ``ctx.panel_width``/``ctx.panel_height`` are REAL (physical) pixels
        (verified against core ``validate._check_plugin_validation_warnings``,
        which builds ``ValidationContext`` from ``_panel_w_real``/
        ``_panel_h_real``) — the same space ``layout``/``auto_font_size``
        already compute in, so no unit conversion is needed here.

        Never raises: a widget whose geometry/font inputs are already
        malformed has those errors surfaced by ``validate_config`` instead;
        this hook wraps its own geometry probe defensively so a bug here
        degrades to "no warning" rather than breaking ``led-ticker validate``
        (core also isolates the hook, but a polite hook doesn't rely on that).
        """
        if ctx.scale == 1:
            # The widget no-ops entirely on an unscaled canvas (see `draw`) —
            # a per-word fit warning would be noise once this fires.
            return [
                "flair.lottery requires a scaled display (bigsign); "
                "the widget will be skipped"
            ]

        words = cfg.get("words")
        if not isinstance(words, list) or not words:
            return []  # required-field error surfaced by validate_config

        warnings: list[str] = []
        try:
            font_name = cfg.get("font", "Inter-Bold")
            inset = _INSET_WITH_BORDER if "border" in cfg else _INSET_NO_BORDER
            diameter_px, _slots = layout(
                len(words), ctx.panel_width, ctx.panel_height, inset
            )
            for word in words:
                if not isinstance(word, str) or not word:
                    continue  # non-string entry: surfaced as an error above
                if auto_font_size(word, diameter_px, font_name, ctx.scale) == 0:
                    warnings.append(
                        f"word {word!r} does not fit a {diameter_px}px ball "
                        f"face (font={font_name!r}) — it will render without "
                        "a label"
                    )
        except Exception:
            logger.warning(
                "flair.lottery: validate_config_warnings geometry check failed",
                exc_info=True,
            )
            return []

        return warnings

    def __attrs_post_init__(self) -> None:
        if self.colors is None:
            n = len(self.words)
            self._resolved_colors = [PALETTE[i % len(PALETTE)] for i in range(n)]
        else:
            self._resolved_colors = [tuple(c) for c in self.colors]

    def reset_frame(self) -> None:
        # Visit entry: drop the surfaces so `_ensure_built` rebuilds from
        # scratch on the next draw — that rebuild IS the re-roll (fresh
        # off-canvas start, `_settled` reset to all-False).
        super().reset_frame()
        self._surfaces = None
        self._rest_surface = None
        self._built_for = None

    def _geometry_key(self, canvas: Any) -> tuple[int, int, int, int]:
        return (canvas.scale, canvas.width, canvas.height, canvas.content_height)

    def _ensure_built(self, canvas: Any) -> None:
        key = self._geometry_key(canvas)
        if self._surfaces is not None and self._built_for == key:
            return

        real = unwrap_to_real(canvas)
        scale = canvas.scale
        panel_w = real.width
        # Real height of the CONTENT band (handles letterboxing — a
        # section's content_height can be shorter than the full real
        # panel height); `layout` needs the band the balls actually
        # occupy, not the whole physical panel.
        panel_h = canvas.height * scale
        inset = _INSET_WITH_BORDER if self.border is not None else _INSET_NO_BORDER

        diameter_px, slot_centers_px = layout(len(self.words), panel_w, panel_h, inset)
        r_px = diameter_px // 2
        cy_logical = canvas.height / 2.0
        tpb = ticks_per_ball(self.roll_ms)

        surfaces: list[Any] = []
        slot_cx_logical: list[float] = []
        for i, word in enumerate(self.words):
            cx_logical = slot_centers_px[i] / scale
            slot_cx_logical.append(cx_logical)

            fits = auto_font_size(word, diameter_px, self.font, scale) != 0
            warn = not fits and word not in self._warned_words
            if not fits:
                self._warned_words.add(word)

            surface = make_rotation_surface(canvas)
            surface.clear()
            paint_face(
                surface.target,
                cx_logical=cx_logical,
                cy_logical=cy_logical,
                r_px=r_px,
                style=self.ball_style,
                color=self._resolved_colors[i],
                word=word,
                font_name=self.font,
                scale=scale,
                warn_unfittable=warn,
            )
            surface.snapshot()
            surfaces.append(surface)

        rest_surface = make_rotation_surface(canvas)
        rest_surface.clear()
        rest_surface.snapshot()

        self._surfaces = surfaces
        self._rest_surface = rest_surface
        self._settled = [False] * len(self.words)
        self._slot_centers_px = slot_centers_px
        self._slot_cx_logical = slot_cx_logical
        self._diameter_px = diameter_px
        self._r_px = r_px
        self._cy_logical = cy_logical
        self._tpb = tpb
        self._built_for = key

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if not is_scaled(canvas):
            if not self._warned_scale:
                logger.warning(
                    "flair.lottery requires a scaled display (bigsign); skipping"
                )
                self._warned_scale = True
            return canvas, 0

        # Border paints FIRST (frames the panel, not the balls) — same
        # order as every other bordered widget in core.
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        self._ensure_built(canvas)

        # `_ensure_built` just ran (unconditionally, above) and always
        # populates both — narrow away the `| None` for the type checker.
        assert self._surfaces is not None
        surfaces = self._surfaces

        # `y_offset` is LOGICAL units (the widget-draw contract), the same
        # unit `RotationSurface.blit`'s `dy_logical` takes — every blit call
        # below forwards it unchanged. This path is used for BOTH the
        # normal y_offset=0 draw and any transition compositing that shifts
        # the widget vertically (PushUp/PushDown): rendering the CURRENT
        # roll frame shifted, rather than substituting an all-settled
        # composite, is what keeps an incoming push from spoiling the
        # reveal (it slides in whatever the frame-0 state actually is —
        # empty/just-starting — and the roll plays out after the push) and
        # keeps an outgoing mid-roll push from popping unrolled balls into
        # existence (it shows the exact mid-roll state, shifted).
        dy_logical = float(y_offset)

        frame = self._frame_count
        # Angle/pivot are irrelevant at angle=0 — an identity copy of
        # whichever balls have already settled this visit.
        self._rest_surface.blit(canvas, 0.0, 0.0, dy_logical=dy_logical)

        # Rack-fill choreography: roll-order j (0-based, the TEMPORAL order
        # balls enter) carries word/slot index n-1-j — the first ball to
        # roll targets the RIGHTMOST slot, the next stops one slot short,
        # and so on. `ball_phase`'s tick-window arg is the roll order, not
        # the slot index; `roll_order_for_slot` (self-inverse — the same
        # formula converts either direction) recovers it from `i`. Word
        # index == slot index throughout (word i always ends up at slot
        # i — unchanged config-order reading), so only the WINDOW a slot's
        # ball owns is remapped here; `colors[i]` still pairs with
        # `words[i]` and slot `i` exactly as before.
        #
        # Balls settle strictly in roll order (each owns a disjoint tick
        # window). Under the normal per-tick cadence (advance_frame then
        # draw, every tick — constraint #12) at most one ball crosses its
        # settle boundary per call. But this loop doesn't assume that: it
        # walks every not-yet-settled ball IN ROLL ORDER (rightmost slot
        # first), composites any whose window has ALREADY fully elapsed
        # (handles a multi-tick jump — e.g. a re-roll landing straight past
        # several balls' windows in one call), and stops at the first ball
        # that's still genuinely rolling (or still parked off-canvas, not
        # yet due) — that one gets the per-tick rotate+translate blit;
        # nothing past it (in roll order) is touched this tick.
        n = len(self.words)
        # Walk slots in ROLL order (the self-inverse mapping yields the slot
        # for each roll-order j): rack_fill walks right-to-left, roll_through
        # left-to-right. The rolling ball is blitted last either way, so in
        # roll_through it naturally paints OVER settled balls it passes.
        for i in (roll_order_for_slot(j, n, self.choreography) for j in range(n)):
            if self._settled[i]:
                continue

            slot_cx = self._slot_cx_logical[i]
            roll_order = roll_order_for_slot(i, n, self.choreography)
            cx_real, angle, settled = ball_phase(
                frame,
                roll_order,
                self._tpb,
                self._diameter_px,
                self._slot_centers_px[i],
            )

            if settled:
                # Composite once into the rest surface so subsequent ticks
                # render this ball via the cheap flat rest-blit instead of
                # re-computing/re-blitting its own surface. `_rest_surface`
                # was already blitted onto `canvas` above (top of this
                # tick), BEFORE this composite — so without an explicit
                # blit here, a ball settling on this exact tick wouldn't
                # appear until the NEXT tick's rest-blit (a one-frame
                # pop-in gap). `angle=0.0` / `dx_logical=0.0` (ball_phase's
                # settled branch always returns cx == slot_cx, angle ==
                # 0.0) paints it flat at its slot, same as the rest-blit
                # would next tick.
                paint_face(
                    self._rest_surface.target,
                    cx_logical=slot_cx,
                    cy_logical=self._cy_logical,
                    r_px=self._r_px,
                    style=self.ball_style,
                    color=self._resolved_colors[i],
                    word=self.words[i],
                    font_name=self.font,
                    scale=canvas.scale,
                    warn_unfittable=False,
                )
                self._rest_surface.snapshot()
                self._settled[i] = True
                surfaces[i].blit(canvas, 0.0, slot_cx, dy_logical=dy_logical)
                continue

            cx_logical = cx_real / canvas.scale
            dx_logical = cx_logical - slot_cx
            surfaces[i].blit(
                canvas, angle, slot_cx, dx_logical=dx_logical, dy_logical=dy_logical
            )
            break

        return canvas, 0
