"""Baseball sprite and rolling animation for LED matrix transitions.

Ported from led-ticker core (`transitions/baseball.py` plus the
baseball-specific hi-res path from `transitions/_hires_loader.py`) into
this plugin. Imports led-ticker symbols only from `led_ticker.plugin`;
the procedural hi-res baseball reuses the sibling
`led_ticker_baseball.emoji._generate_baseball_hires` generator.

Registration (`baseball.roll` / `baseball.roll_reverse` /
`baseball.roll_alternating`) happens in the plugin's `register(api)`;
the registry decorators from core are intentionally dropped here.
"""

import functools
from typing import Any, ClassVar

from PIL import Image

from led_ticker.plugin import Canvas, PixelData, ScaledCanvas, Transition, unwrap_to_real

SPRITE_SIZE: int = 14
SPRITE_Y_OFFSET: int = 1  # centers 14px sprite in 16px display
PIXELS_PER_ROTATION: int = 44  # circumference of 14px circle ≈ π×14
NUM_FRAMES: int = 4

# Color palette
_WH = (255, 255, 255)  # white (ball)
_RD = (220, 40, 40)  # red (stitches)
_OL = (40, 40, 40)  # outline (dark gray)
_SH = (220, 220, 220)  # shadow/off-white


def _circle_mask() -> set[tuple[int, int]]:
    """Pre-compute which (dx, dy) are inside a 14px diameter circle."""
    cx, cy = 6.5, 6.5
    r = 6.5
    mask: set[tuple[int, int]] = set()
    for dy in range(SPRITE_SIZE):
        for dx in range(SPRITE_SIZE):
            if (dx - cx) ** 2 + (dy - cy) ** 2 <= r * r:
                mask.add((dx, dy))
    return mask


def _outline_mask(interior: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Find pixels on the edge of the circle (have a neighbor outside)."""
    outline: set[tuple[int, int]] = set()
    for dx, dy in interior:
        for ndx, ndy in [(dx - 1, dy), (dx + 1, dy), (dx, dy - 1), (dx, dy + 1)]:
            if (ndx, ndy) not in interior:
                outline.add((dx, dy))
                break
    return outline


def _build_frame_0() -> PixelData:
    """Frame 0: Vertical stitch curves on left and right sides."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    # Stitch positions: S-curves on left (x=3-4) and right (x=9-10)
    stitches: set[tuple[int, int]] = set()
    # Left stitch curve (top-right to bottom-left arc)
    for dx, dy in [
        (4, 2),
        (3, 3),
        (3, 4),
        (2, 5),
        (2, 6),
        (2, 7),
        (3, 8),
        (3, 9),
        (4, 10),
        (4, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Right stitch curve (mirrored)
    for dx, dy in [
        (9, 2),
        (10, 3),
        (10, 4),
        (11, 5),
        (11, 6),
        (11, 7),
        (10, 8),
        (10, 9),
        (9, 10),
        (9, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


def _build_frame_1() -> PixelData:
    """Frame 1: 90° — horizontal stitch curves on top and bottom."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    stitches: set[tuple[int, int]] = set()
    # Top stitch curve
    for dx, dy in [
        (2, 4),
        (3, 3),
        (4, 3),
        (5, 2),
        (6, 2),
        (7, 2),
        (8, 3),
        (9, 3),
        (10, 4),
        (11, 4),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Bottom stitch curve
    for dx, dy in [
        (2, 9),
        (3, 10),
        (4, 10),
        (5, 11),
        (6, 11),
        (7, 11),
        (8, 10),
        (9, 10),
        (10, 9),
        (11, 9),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


def _build_frame_2() -> PixelData:
    """Frame 2: 180° — vertical stitch curves, mirrored from frame 0."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    stitches: set[tuple[int, int]] = set()
    # Left stitch (mirrored vertical from frame 0)
    for dx, dy in [
        (4, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (2, 6),
        (3, 7),
        (3, 8),
        (3, 9),
        (4, 10),
        (5, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Right stitch (mirrored)
    for dx, dy in [
        (9, 2),
        (10, 3),
        (10, 4),
        (10, 5),
        (11, 6),
        (10, 7),
        (10, 8),
        (10, 9),
        (9, 10),
        (8, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


def _build_frame_3() -> PixelData:
    """Frame 3: 270° — horizontal stitch curves, mirrored from frame 1."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    stitches: set[tuple[int, int]] = set()
    # Top stitch curve (mirrored from frame 1)
    for dx, dy in [
        (2, 4),
        (3, 3),
        (4, 3),
        (5, 3),
        (6, 2),
        (7, 3),
        (8, 3),
        (9, 3),
        (10, 4),
        (11, 5),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Bottom stitch curve (mirrored)
    for dx, dy in [
        (2, 9),
        (3, 10),
        (4, 10),
        (5, 10),
        (6, 11),
        (7, 10),
        (8, 10),
        (9, 10),
        (10, 9),
        (11, 8),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


BASEBALL_FRAME_0: PixelData = _build_frame_0()
BASEBALL_FRAME_1: PixelData = _build_frame_1()
BASEBALL_FRAME_2: PixelData = _build_frame_2()
BASEBALL_FRAME_3: PixelData = _build_frame_3()

BASEBALL_FRAMES: list[PixelData] = [
    BASEBALL_FRAME_0,
    BASEBALL_FRAME_1,
    BASEBALL_FRAME_2,
    BASEBALL_FRAME_3,
]


def draw_baseball_frame(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the baseball rolling transition (left-to-right).

    The baseball rolls from off-screen left to off-screen right.
    Everything to its left is blacked out (erased).
    """
    total_travel = width + SPRITE_SIZE
    ball_x = int(-SPRITE_SIZE + progress * total_travel)

    # Select rotation frame based on distance traveled
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES
    frame_idx = (max(0, ball_x) // pixels_per_frame) % NUM_FRAMES
    sprite = BASEBALL_FRAMES[frame_idx]

    # Black out everything to the left of the ball
    blackout_end = min(width, max(0, ball_x))
    if blackout_end > 0:
        canvas.SubFill(0, 0, blackout_end, height, 0, 0, 0)

    # Draw the baseball sprite (clipped to canvas bounds)
    for dx, dy, r, g, b in sprite:
        x = ball_x + dx
        y = SPRITE_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


def draw_baseball_frame_rtl(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the baseball rolling transition (right-to-left).

    Mirror of draw_baseball_frame: ball rolls from right to left,
    blackout is on the right, sprite is horizontally flipped.
    """
    total_travel = width + SPRITE_SIZE
    ball_x = int(width - progress * total_travel)

    # Select rotation frame
    pixels_traveled = int(progress * total_travel)
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES
    frame_idx = (pixels_traveled // pixels_per_frame) % NUM_FRAMES
    sprite = BASEBALL_FRAMES[frame_idx]

    # Black out everything to the right of the ball
    blackout_start = max(0, min(width, ball_x + SPRITE_SIZE))
    if blackout_start < width:
        canvas.SubFill(blackout_start, 0, width - blackout_start, height, 0, 0, 0)

    # Draw the baseball sprite (flipped horizontally)
    for dx, dy, r, g, b in sprite:
        x = ball_x + (SPRITE_SIZE - 1 - dx)
        y = SPRITE_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


# --- Hi-res path (ported from core transitions/_hires_loader.py) ---

# Trail saturates (sprite reaches far edge, trail fills the entire panel)
# at this t. Below SNAP_THRESHOLD so the panel holds a fully-covered
# black field for a beat before the cut to incoming — matches the lowres
# baseball "fill, hold, cut" feel.
TRAIL_SATURATION_T: float = 0.85

# Snap to incoming this fraction of the way through. By this t the trail
# has fully filled the panel (TRAIL_SATURATION_T < SNAP_THRESHOLD).
SNAP_THRESHOLD: float = 0.95


def _normalize_bg(c: Any) -> tuple[int, int, int] | None:
    """Coerce an `(r, g, b)` tuple, a `graphics.Color`, or `None` to
    a tuple/None pair.

    Local copy of core's `transitions._normalize_bg` (an internal not on
    the plugin's public surface) so `_snap_reset` can call it without
    importing a core internal.
    """
    if c is None:
        return None
    if hasattr(c, "red"):
        return (c.red, c.green, c.blue)
    return c


def _snap_reset(canvas: Any, incoming_bg_color: Any) -> None:
    """Reset before drawing incoming at t>=SNAP_THRESHOLD.

    `Clear()` (legacy) wipes any bg fill the run_transition outer
    loop just painted, so the last frame ends up "incoming on black"
    even when the section has a bg color — visible as a one-tick
    flash on bordered widgets. When the run_transition caller
    forwards `incoming_bg_color` here, Fill it instead so the snap
    matches the section's first reset_canvas.

    Accepts None, an `(r, g, b)` tuple, or a `graphics.Color` —
    same shape `run_transition` accepts.
    """
    bg = _normalize_bg(incoming_bg_color)
    if bg is not None:
        canvas.Fill(*bg)
    else:
        canvas.Clear()


# Rotation frames cycled through as the baseball rolls. 8 frames at
# 45° increments — fast 90° steps read as alternating patterns; very
# fast 22.5° steps look chaotic on a small panel. 8 frames combined
# with one full revolution per panel-width of travel gives a slow,
# legible roll closer to the static :baseball: emoji aesthetic.
_BASEBALL_ROTATION_FRAMES: int = 8


@functools.cache
def _baseball_rotation_frames(
    diameter: int,
) -> tuple[tuple[tuple[int, int, int, int, int], ...], ...]:
    """Generate `_BASEBALL_ROTATION_FRAMES` rotated baseball sprites at the
    given diameter. Cached forever — geometry is deterministic.

    Reuses the hi-res emoji baseball generator (`_generate_baseball_hires`)
    and rotates each frame via PIL. Frame 0 is the canonical orientation;
    each subsequent frame is +90° clockwise (negative angle in PIL's CCW
    convention). LTR rolling iterates 0 → 1 → 2 → 3; RTL iterates in reverse.
    """
    from led_ticker_baseball.emoji import _generate_baseball_hires

    base_pixels = _generate_baseball_hires(size=diameter)
    base = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    for x, y, r, g, b in base_pixels:
        base.putpixel((x, y), (r, g, b, 255))

    out: list[tuple[tuple[int, int, int, int, int], ...]] = []
    for i in range(_BASEBALL_ROTATION_FRAMES):
        angle = -i * 360 / _BASEBALL_ROTATION_FRAMES  # negative = clockwise
        rotated = base.rotate(
            angle, resample=Image.Resampling.NEAREST, fillcolor=(0, 0, 0, 0)
        )
        frame: list[tuple[int, int, int, int, int]] = []
        for y in range(diameter):
            for x in range(diameter):
                px = rotated.getpixel((x, y))
                if isinstance(px, tuple) and len(px) == 4 and px[3] > 0:
                    frame.append((x, y, px[0], px[1], px[2]))
        out.append(tuple(frame))
    return tuple(out)


def _paint_procedural_baseball(
    canvas: Any,
    cx: int,
    cy: int,
    radius: int,
    rotation_idx: int,
    panel_w: int,
    panel_h: int,
) -> None:
    """Paint a procedural hi-res baseball at (cx, cy) with the given rotation
    frame index (0..3). Reuses cached rotated frames generated from the
    hi-res emoji baseball."""
    diameter = radius * 2
    frames = _baseball_rotation_frames(diameter)
    pixels = frames[rotation_idx % len(frames)]
    set_px = canvas.SetPixel
    origin_x = cx - radius
    origin_y = cy - radius
    for x, y, r, g, b in pixels:
        rx = origin_x + x
        ry = origin_y + y
        if 0 <= rx < panel_w and 0 <= ry < panel_h:
            set_px(rx, ry, r, g, b)


def render_hires_baseball_frame(
    t: float,
    canvas: Any,
    outgoing: Any,
    incoming: Any,
    *,
    flip_horizontal: bool,
    **kwargs: Any,
) -> Any:
    """Paint one frame of the hi-res baseball transition.

    Mirrors pokeball's structure but uses a procedural baseball (not a
    Pillow-decoded sprite). The ball traverses with a black trail behind
    it, rotating as it rolls. Snaps to incoming at SNAP_THRESHOLD.
    """
    # CAUTION: this function trusts that `canvas` is a `ScaledCanvas` (the
    # dispatch in the transition classes guarantees this).
    # `unwrap_to_real(canvas)` walks any number of nested ScaledCanvas
    # wrappers. If a future caller wraps a ScaledCanvas in some OTHER kind
    # of wrapper, dispatch would still pick lowres but this code would
    # paint to the wrong canvas. Not a concern today; flag here for future
    # reference.
    real = unwrap_to_real(canvas)
    panel_w = real.width
    panel_h = real.height

    outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))

    effective_t = min(1.0, t / TRAIL_SATURATION_T)
    ball_radius = panel_h // 3
    ball_cy = panel_h // 2
    ball_travel = panel_w + 2 * ball_radius
    if flip_horizontal:
        ball_cx = panel_w + ball_radius - int(effective_t * ball_travel)
        leading_x = ball_cx - ball_radius
    else:
        ball_cx = -ball_radius + int(effective_t * ball_travel)
        leading_x = ball_cx + ball_radius

    set_px = real.SetPixel

    # Black trail extending to ball's leading edge.
    if flip_horizontal:
        trail_x_start = min(panel_w, max(0, leading_x))
        trail_x_end = panel_w
    else:
        trail_x_start = 0
        trail_x_end = min(panel_w, max(0, leading_x))
    if trail_x_end > trail_x_start:
        for y in range(panel_h):
            for x in range(trail_x_start, trail_x_end):
                set_px(x, y, 0, 0, 0)

    # Rotation: ball rolls clockwise for LTR, counterclockwise for RTL.
    # `pixels_per_rotation_frame` controls how often the rotation index
    # advances. One full revolution per panel-width of travel — the
    # ball does ~1 rotation crossing the panel. Physically slower than
    # a real ball (which would do ~5-7 rotations) but the small panel
    # and abstract sprite read better with subtle motion.
    pixels_per_rotation_frame = max(1, panel_w // _BASEBALL_ROTATION_FRAMES)
    if flip_horizontal:
        travel_done = max(0, panel_w - ball_cx)
        # negate idx so RTL cycles 0 → 3 → 2 → 1 (counterclockwise)
        rotation_idx = (-(travel_done // pixels_per_rotation_frame)) % (
            _BASEBALL_ROTATION_FRAMES
        )
    else:
        travel_done = max(0, ball_cx)
        rotation_idx = (travel_done // pixels_per_rotation_frame) % (
            _BASEBALL_ROTATION_FRAMES
        )

    _paint_procedural_baseball(
        real, ball_cx, ball_cy, ball_radius, rotation_idx, panel_w, panel_h
    )

    if t >= SNAP_THRESHOLD:
        _snap_reset(canvas, kwargs.get("incoming_bg_color"))
        incoming.draw(canvas)

    return canvas


# --- Transition classes ---


class Baseball:
    """Baseball rolls left-to-right, erasing outgoing content.

    On a `ScaledCanvas` (bigsign), dispatches to the hi-res path which
    paints a procedural baseball at native physical resolution using
    the same geometry as the hi-res `:baseball:` emoji.
    """

    min_frames: int = 40
    scale_switch_at: ClassVar[float] = SNAP_THRESHOLD

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if isinstance(canvas, ScaledCanvas):
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_baseball_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        return render_hires_baseball_frame(
            t, canvas, outgoing, incoming, flip_horizontal=False, **kwargs
        )


class BaseballReverse:
    """Baseball rolls right-to-left, erasing outgoing content."""

    min_frames: int = 40
    scale_switch_at: ClassVar[float] = SNAP_THRESHOLD

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if isinstance(canvas, ScaledCanvas):
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_baseball_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        return render_hires_baseball_frame(
            t, canvas, outgoing, incoming, flip_horizontal=True, **kwargs
        )


class BaseballAlternating:
    """Cycles through baseball -> baseball_reverse."""

    scale_switch_at: ClassVar[float] = SNAP_THRESHOLD

    def __init__(self, **kwargs: Any) -> None:
        self._transitions: list[Transition] = [
            Baseball(**kwargs),
            BaseballReverse(**kwargs),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 40)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
