"""flair.poker visual-gate prototype (throwaway, design phase).

Simulates the transition on a 256x64 'panel': outgoing = amber menu-ish text
bars, incoming = cyan bars. Suit glyphs fade in as a repeating rainbow grid,
then emit suit-SHAPED rainbow ripple rings; inside each ripple's wake the
incoming content is revealed. Renders variants:
  A: one staggered ripple per glyph
  B: repeating pulses (2.5 rings per glyph)
  diamonds: single-suit config, variant A
"""
import colorsys
import math
import random
import sys

from PIL import Image

W, H = 256, 64
SCALE = 4  # display upscale
FRAMES = 72          # ~3.6s at 20fps
GRID = 32            # glyph cell size (real px)
GLYPH_R = 7.0        # glyph half-size at rest
SUITS = ["heart", "diamond", "club", "spade"]


def in_heart(x, y, r):
    if r <= 0:
        return False
    # classic implicit heart, y up; normalize to radius r
    nx, ny = x / r, -y / r
    v = (nx * nx + ny * ny - 1) ** 3 - nx * nx * ny * ny * ny
    return v <= 0


def in_diamond(x, y, r):
    return r > 0 and abs(x) + abs(y) <= r


def in_club(x, y, r):
    if r <= 0:
        return False
    lr = 0.45 * r
    for ang in (90, 210, 330):
        a = math.radians(ang)
        cx, cy = 0.5 * r * math.cos(a), -0.5 * r * math.sin(a)
        if (x - cx) ** 2 + (y - cy) ** 2 <= lr * lr:
            return True
    return abs(x) <= 0.16 * r and 0 <= y <= r  # stem (y down = below center)


def in_spade(x, y, r):
    if r <= 0:
        return False
    if in_heart(x, -y * 0.95, r * 0.92):  # flipped heart body
        return True
    return abs(x) <= 0.16 * r and 0 <= y <= r  # stem


IN = {"heart": in_heart, "diamond": in_diamond, "club": in_club, "spade": in_spade}


def hue_rgb(h, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, v)
    return int(r * 255), int(g * 255), int(b * 255)


def content(x, y, incoming):
    """Fake widget content: horizontal text-ish bars."""
    if incoming:
        on = (y // 8) % 2 == 0 and (x // 6) % 5 != 4
        return (0, 190, 210) if on else (0, 0, 30)
    on = (y // 8) % 2 == 1 and (x // 7) % 4 != 3
    return (255, 160, 0) if on else (25, 8, 0)


def render(variant, suits, out_name, seed=5):
    rng = random.Random(seed)
    cols = math.ceil(W / GRID)
    rows = math.ceil(H / GRID)
    glyphs = []
    for i in range(cols * rows):
        gx, gy = i % cols, i // cols
        glyphs.append({
            "cx": gx * GRID + GRID / 2 + rng.uniform(-3, 3),
            "cy": gy * GRID + GRID / 2 + rng.uniform(-2, 2),
            "suit": suits[i % len(suits)],
            "hue": rng.random(),
            "stagger": rng.uniform(0.0, 0.25),
        })
    max_r = math.hypot(GRID, GRID) * 1.2  # covers neighbors -> full reveal

    frames = []
    for f in range(FRAMES):
        t = f / (FRAMES - 1)
        img = Image.new("RGB", (W, H))
        px = img.load()
        for y in range(H):
            for x in range(W):
                base = content(x, y, incoming=False)
                # nearest glyph dominates this pixel's ripple state
                revealed = False
                ring = None
                glyph_on = False
                for g in glyphs:
                    dx, dy = x - g["cx"], y - g["cy"]
                    if abs(dx) > max_r or abs(dy) > max_r:
                        continue
                    inside = IN[g["suit"]]
                    # ripple radius timeline for this glyph
                    p = (t - 0.25 - g["stagger"]) / (0.75 - g["stagger"])
                    if variant == "B":
                        # repeating pulses: 2.5 waves, each expands to max_r
                        if p > 0:
                            phase = (p * 2.5) % 1.0
                            wave_n = int(p * 2.5)
                            r_rip = phase * max_r
                            # final wave reveals permanently
                            if wave_n >= 2 and inside(dx, dy, r_rip):
                                revealed = True
                            if inside(dx, dy, r_rip) and not inside(dx, dy, r_rip - 3.5):
                                ring = hue_rgb(g["hue"] + phase * 0.7)
                            if wave_n >= 1 and inside(dx, dy, max_r) and wave_n == 1 and inside(dx, dy, (phase) * max_r):
                                revealed = True
                    else:
                        # A: single staggered ripple; wake reveals
                        if p > 0:
                            r_rip = p * max_r
                            if inside(dx, dy, r_rip):
                                revealed = True
                            if inside(dx, dy, r_rip) and not inside(dx, dy, r_rip - 3.5):
                                ring = hue_rgb(g["hue"] + p * 0.7)
                    # the resting glyph itself (pre/early ripple)
                    gr = GLYPH_R * min(1.0, t / 0.2)  # fade/scale in
                    if t < 0.45 and inside(dx, dy, gr):
                        glyph_on = True
                        glyph_hue = g["hue"] + t * 0.5
                if revealed:
                    base = content(x, y, incoming=True)
                if glyph_on and not revealed:
                    base = hue_rgb(glyph_hue)
                if ring is not None:
                    base = ring
                px[x, y] = base
        if t >= 0.995:
            img = Image.new("RGB", (W, H))
            p2 = img.load()
            for y in range(H):
                for x in range(W):
                    p2[x, y] = content(x, y, incoming=True)
        frames.append(img.resize((W * SCALE, H * SCALE), Image.NEAREST))
    frames[0].save(out_name, save_all=True, append_images=frames[1:],
                   duration=50, loop=0)
    print("wrote", out_name)


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "A":
        render("A", SUITS, "poker-A-staggered.gif")
    elif which == "B":
        render("B", SUITS, "poker-B-pulses.gif")
    else:
        render("A", ["diamond"], "poker-diamonds.gif")
