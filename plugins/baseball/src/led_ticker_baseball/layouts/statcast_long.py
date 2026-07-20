"""Held statcast hero card, 512px — port of `statcastLong` (dc.html
~574-598), with the redesigned animated trajectory panel (trajectory.py)
in place of the prototype's `traj()`. A pitch superlative (no launch
angle / distance) replaces the arc panel with pitch emphasis (no arc).

Uppercasing: the result / player name / pitch name are upper()'d at RENDER
time here (never persisted upstream on `StatRecord`) — same rationale as
the sibling `layouts/statcast_big.py`.
"""

from led_ticker.plugin import safe_scale, unwrap_to_real

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import (
    cap_top,
    fit_text,
    hires,
    paging_dots,
    phys_wrap,
)
from led_ticker_baseball.trajectory import draw_trajectory, plan_arc, res_color

_TRAJ_BOX = (396, 20, 106, 24)

# PITCH column origin (cx=320) to a 6px safe margin before the distance
# panel (px0=396): 396 - 320 - 6. Even the abbreviation-based sec text is
# fit_text-clamped to this width so an unexpectedly long value can never
# overlap the trajectory/distance panel.
_PITCH_SEC_MAX_W = 70

# panel slot x=396 to a 6px right margin (512-6-396); the big pitch element
# fit_text-clamped to this so a long name can't run off the panel edge.
_PITCH_PANEL_MAX_W = 110


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, cap_top(y_target, size), color, size, bold=bold)


def _num(v, suffix=""):
    """Guard a possibly-missing numeric field to an em-dash placeholder
    (never raises on `None` — the empty-context contract)."""
    return f"{v:g}{suffix}" if v is not None else "—"


def render_statcast_long(
    canvas,
    record,
    player_name: str,
    progress: float,
    *,
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
) -> None:
    """Draw one statcast hero card with the animated trajectory panel
    (held layout; `progress` drives the arc's flight fraction — the
    caller's rotation owns the animation clock)."""
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)

    _t(shim, (player_name or "").upper(), 6, 4 + yo, pal.IDENT, 22)
    res = (record.result or "").upper()
    _t(shim, res, 6, 34 + yo, res_color(res), 13)
    _t(shim, "STATCAST", 6, 52 + yo, pal.LABEL, 9)

    pt = (record.pitch_type or record.pitch_name or "").upper()
    pitch_sec = fit_text(f"{pt} MPH" if pt else "MPH", _PITCH_SEC_MAX_W, 9, bold=False)
    cols = [
        ("EXIT VELO", _num(record.exit_velo), "MPH", pal.AMBER),
        ("LAUNCH", _num(record.launch_angle, "°"), "ANGLE", pal.CYAN),
        ("PITCH", _num(record.pitch_velo), pitch_sec, pal.WIN),
    ]
    for i, (lab, val, sec, c) in enumerate(cols):
        cx = 176 + i * 72
        _t(shim, lab, cx, 6 + yo, pal.LABEL, 10)
        _t(shim, val, cx, 20 + yo, c, 22)
        _t(shim, sec, cx, 48 + yo, pal.LABEL, 9, bold=False)

    px0 = 396
    is_batted = record.launch_angle is not None and record.distance is not None
    _t(shim, "DISTANCE" if is_batted else "PITCH TYPE", px0, 6 + yo, pal.LABEL, 10)
    if is_batted:
        bx, by, bw, bh = _TRAJ_BOX
        plan = plan_arc(
            record.launch_angle,
            record.exit_velo,
            record.distance,
            record.bb_type,
            record.result,
            bw,
            bh,
        )
        draw_trajectory(unwrap_to_real(canvas), (bx, by + yo, bw, bh), plan, progress)
        dist_text = f"{int(record.distance)} FT" if record.distance else "—"
        _t(
            shim,
            dist_text,
            px0,
            48 + yo,
            pal.MAGENTA if record.distance else pal.LABEL,
            13,
        )
    else:
        # pitch superlative: no arc — emphasize pitch type in the panel.
        # Use the short Savant abbreviation (can't clip) with a fit_text
        # belt as backstop; fall back to the full name (also belted, so
        # it ellipsizes instead of clipping) only when no abbreviation
        # exists.
        pt_big = (record.pitch_type or record.pitch_name or "—").upper()
        _t(shim, fit_text(pt_big, _PITCH_PANEL_MAX_W, 20), px0, 24 + yo, pal.WIN, 20)
        _t(
            shim,
            fit_text(
                (record.pitch_name or "").upper(), _PITCH_PANEL_MAX_W, 9, bold=False
            ),
            px0,
            48 + yo,
            pal.LABEL,
            9,
            bold=False,
        )

    if story_total > 1:
        paging_dots(
            real,
            story_total,
            story_index,
            real.width - story_total * 8 - 6,
            real.height - 10 + yo,
        )
