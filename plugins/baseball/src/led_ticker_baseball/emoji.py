"""Baseball emoji sprites for the led-ticker-baseball plugin.

Ported from core ``led_ticker.pixel_emoji``:

- ``BALL``  — lo-res 8x8 baseball sprite (was ``BASEBALL`` in core).
- ``BALL_HIRES`` — hi-res 32x32 baseball (was ``BASEBALL_HIRES`` in core).
- ``_generate_baseball_hires`` — self-contained hi-res generator.

Imports only from the public ``led_ticker.plugin`` surface.
"""

from led_ticker.plugin import HiResEmoji, PixelData

# ⚾ Baseball — white ball with two vertical red stitch lines
# Inspired by classic pixel baseball sprites: stitches run vertically
# through the center, curving outward at top and bottom.
_W = (240, 240, 240)  # white fill
_B = (255, 255, 255)  # bright white edge
_R = (200, 20, 20)  # red stitching
BALL: PixelData = [
    # Row 0: top of ball
    (2, 0, *_B),
    (3, 0, *_B),
    (4, 0, *_B),
    (5, 0, *_B),
    # Row 1: stitches curve outward at top
    (1, 1, *_B),
    (2, 1, *_R),
    (3, 1, *_W),
    (4, 1, *_W),
    (5, 1, *_R),
    (6, 1, *_B),
    # Row 2: stitches widen
    (0, 2, *_B),
    (1, 2, *_W),
    (2, 2, *_R),
    (3, 2, *_W),
    (4, 2, *_W),
    (5, 2, *_R),
    (6, 2, *_W),
    (7, 2, *_B),
    # Row 3: two vertical stitch lines
    (0, 3, *_B),
    (1, 3, *_W),
    (2, 3, *_R),
    (3, 3, *_W),
    (4, 3, *_W),
    (5, 3, *_R),
    (6, 3, *_W),
    (7, 3, *_B),
    # Row 4: two vertical stitch lines
    (0, 4, *_B),
    (1, 4, *_W),
    (2, 4, *_R),
    (3, 4, *_W),
    (4, 4, *_W),
    (5, 4, *_R),
    (6, 4, *_W),
    (7, 4, *_B),
    # Row 5: stitches widen
    (0, 5, *_B),
    (1, 5, *_W),
    (2, 5, *_R),
    (3, 5, *_W),
    (4, 5, *_W),
    (5, 5, *_R),
    (6, 5, *_W),
    (7, 5, *_B),
    # Row 6: stitches curve outward at bottom
    (1, 6, *_B),
    (2, 6, *_R),
    (3, 6, *_W),
    (4, 6, *_W),
    (5, 6, *_R),
    (6, 6, *_B),
    # Row 7: bottom of ball
    (2, 7, *_B),
    (3, 7, *_B),
    (4, 7, *_B),
    (5, 7, *_B),
]


# ⚾ Hi-res baseball — solid white ball with two parallel red seam arcs
# and cross-stitch hash marks. The seams lean the same way so they read
# as a 3D figure-8 projected onto one face of the ball; an earlier
# version had the seams meeting at top/bottom poles, which read more
# as a flat football than a 3D ball.
_BASEBALL_WHITE = (250, 250, 245)
_BASEBALL_EDGE = (200, 200, 210)
_BASEBALL_RED = (200, 30, 40)


def _generate_baseball_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    import math

    cx = cy = (size - 1) / 2.0
    body_r = size / 2 - 0.5  # use full canvas

    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    # Step 1: solid white ball with subtle 1-px gray edge so the round
    # silhouette reads cleanly against a black panel.
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d > body_r:
                continue
            if d > body_r - 1.0:
                pixels[(x, y)] = _BASEBALL_EDGE
            else:
                pixels[(x, y)] = _BASEBALL_WHITE

    # Step 2: two seam curves traced as quadratic Béziers. Together they
    # form an offset figure-8: the upper seam sweeps from upper-right
    # down toward mid-left, and the lower seam sweeps from mid-right
    # down toward lower-left. The control points sit just past center
    # so each curve has a gentle S-shape rather than a tight arc.
    def bezier(
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        t: float,
    ) -> tuple[float, float]:
        u = 1 - t
        return (
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        )

    def trace_seam(
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        n: int = 64,
    ) -> list[tuple[float, float]]:
        path: list[tuple[float, float]] = []
        for i in range(n + 1):
            t = i / n
            sx, sy = bezier(p0, p1, p2, t)
            path.append((sx, sy))
            ix, iy = int(round(sx)), int(round(sy))
            if (ix, iy) in pixels and pixels[(ix, iy)] != _BASEBALL_EDGE:
                pixels[(ix, iy)] = _BASEBALL_RED
        return path

    # Upper seam: top-left → mid-right (leans /). Top stitches sit in
    # the upper-right quadrant of the ball.
    seam1 = trace_seam(
        p0=(cx - 2, cy - body_r * 0.92),  # near top, slightly left of center
        p1=(cx + 0, cy - body_r * 0.20),  # control: above center
        p2=(cx + body_r * 0.92, cy + 2),  # mid-right, slightly below center
    )
    # Lower seam: mid-left → bottom-right (also leans /). Both seams
    # lean the same way — two parallel diagonal stripes — matching the
    # reference baseball where the seams trace a 3D figure-8 that
    # projects to two parallel arcs on one side of the ball.
    seam2 = trace_seam(
        p0=(cx - body_r * 0.92, cy - 2),  # mid-left, slightly above center
        p1=(cx + 0, cy + body_r * 0.20),  # control: below center
        p2=(cx + 2, cy + body_r * 0.92),  # near bottom, slightly right of center
    )

    # Step 3: hash stitches — small red squares offset perpendicular to
    # each seam at evenly-spaced points along the curve. Reads as the
    # cross-stitch threads visible on a real baseball.
    n_stitches = 9
    for path in (seam1, seam2):
        for i in range(n_stitches):
            t_idx = int((i + 0.5) / n_stitches * (len(path) - 1))
            if t_idx >= len(path) - 1:
                continue
            sx, sy = path[t_idx]
            sx_next, sy_next = path[t_idx + 1]
            tx, ty = sx_next - sx, sy_next - sy
            tlen = math.sqrt(tx * tx + ty * ty)
            if tlen == 0:
                continue
            tx, ty = tx / tlen, ty / tlen
            # Drop a 1-px stitch on each side of the seam, perpendicular
            # to the local tangent (rotate tangent by ±90°).
            for sign in (-1, 1):
                px = sx + sign * 1.5 * ty
                py = sy - sign * 1.5 * tx
                ix, iy = int(round(px)), int(round(py))
                if (ix, iy) in pixels and pixels[(ix, iy)] != _BASEBALL_EDGE:
                    pixels[(ix, iy)] = _BASEBALL_RED

    return tuple((x, y, *c) for (x, y), c in pixels.items())


BALL_HIRES = HiResEmoji(
    pixels=_generate_baseball_hires(size=32),
    physical_size=32,
)
