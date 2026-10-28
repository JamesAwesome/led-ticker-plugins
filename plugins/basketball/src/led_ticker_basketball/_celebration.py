"""Final-score celebration: the frame timeline (renderers land in Task 7).

Timeline (engine tick = 50 ms): each final gets `CELEBRATION_FRAMES` (4 s).
The first `FLASH_FRAMES` are three on/off flashes of the full panel in the
winner's colour; the rest is the detail card.
"""

import math

FLASH_FRAMES = 12
CELEBRATION_FRAMES = 80
CELEBRATION_SECONDS = CELEBRATION_FRAMES * 0.05  # 4 s at the 50 ms tick
MAX_QUEUED = 1
HIGHLIGHT_FRAMES = 30


def phase_at(frame: int, n: int) -> tuple[int, str, int] | None:
    """`(index, phase, frame_in_event)`; None once the run is over."""
    if frame < 0 or frame >= n * CELEBRATION_FRAMES:
        return None
    idx, f = divmod(frame, CELEBRATION_FRAMES)
    if f < FLASH_FRAMES:
        return idx, ("flash_on" if (f // 2) % 2 == 0 else "flash_off"), f
    return idx, "detail", f


def pulse(frame: int) -> float:
    """The score pulse, 0.55-1.0."""
    return 0.55 + 0.45 * (0.5 + 0.5 * math.cos(frame * 50 / 180))


# --- temporary stubs: Task 7 replaces these ---------------------------------


def win_word(ev, max_w, size):  # Task 7 replaces this stub
    return f"{ev.winner} WIN"


def render_flash(canvas, color, on, word, *, y_offset=0):  # Task 7 replaces this stub
    pass


def render_detail(  # Task 7 replaces this stub
    canvas, game, ev, frame, *, y_offset=0, font=None, logos=True
):
    pass
