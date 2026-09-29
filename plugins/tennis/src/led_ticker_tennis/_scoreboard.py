"""Legacy scale-1 (smallsign) renderers: the two-band `TennisScoreboardMessage`
and the `_build_match_message` ticker line. Both are BDF text-glyph paths
(`draw_text` on the logical canvas); scale>1 signs never reach them —
`TennisMatchCard` dispatches those to `layouts/`.

The board lays its numbers out right-to-left from measured `measure_width`
extents (same construction as the physical board), so the name zone is the
measured remainder and names are truncated, never overlapped. The serve
marker is the tennis-notation "*" after the server's name (present in every
bundled BDF font, unlike a disc glyph).
"""

from typing import Any
from zoneinfo import ZoneInfo

import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    FONT_SMALL,
    Color,
    ColorProvider,
    DrawResult,
    Font,
    FrameAwareBase,
    SegmentMessage,
)

from led_ticker_tennis import _palette as pal
from led_ticker_tennis._models import (
    MatchInfo,
    format_points,
    format_start_time,
    is_break_point,
    receiver,
    status_label,
)
from led_ticker_tennis.layouts.crawl import segments

_GAP = 2  # logical px between measured zones
_SHORT_STATUS: dict[str, str] = {"FINAL": "F", "SUSP": "SUSP"}


def _short_status(label: str) -> str:
    if label.startswith("SET "):
        return "S" + label[4:]
    return _SHORT_STATUS.get(label, label)


@attrs.define
class TennisScoreboardMessage(FrameAwareBase):
    """Two bands: player 1 on top, player 2 below. Each band: name(*) |
    games per set | points | BP | status (band 1) / round or time (band 2)."""

    match: MatchInfo
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_SMALL, kw_only=True)

    def _rows(self) -> list[list[tuple[str, Color]]]:
        """Left-to-right (text, color) cells per band, right cell last."""
        m = self.match
        tz = self.tz or ZoneInfo("UTC")
        bp = (
            is_break_point(m.points, m.server, m.is_tiebreak)
            if m.state == "live"
            else False
        )
        rcv = receiver(m.server)
        rows: list[list[tuple[str, Color]]] = []
        for side in (1, 2):
            name = (m.p1 if side == 1 else m.p2).upper() or "?"
            if m.state == "live" and m.server == side:
                name += "*"
            name_c = pal.IDENT
            num_c = pal.AMBER
            if m.state == "final" and m.winner in (1, 2):
                name_c = num_c = pal.WIN if m.winner == side else pal.LABEL_HI
            cells: list[tuple[str, Color]] = [(name, name_c)]
            if m.state != "upcoming":
                if not m.games:
                    cells.append((str(m.sets[side - 1]), num_c))
                for a, b in m.games:
                    cells.append((str(a if side == 1 else b), num_c))
                pts = (
                    format_points(m.points, m.is_tiebreak) if m.state == "live" else ""
                )
                if pts:
                    a, b = m.points
                    cells.append((str(a if side == 1 else b), pal.CYAN))
                if bp and rcv == side:
                    cells.append(("BP", pal.LOSS))
            rows.append(cells)
        # right-most cell: status on band 1, round/time on band 2
        if m.state == "upcoming":
            day, clock = format_start_time(m.start_time, tz)
            rows[0].append(("STALE" if m.stale else day or "NEXT", pal.AMBER))
            rows[1].append((clock, pal.AMBER))
        else:
            label = status_label(m)
            rows[0].append(
                (_short_status(label), pal.WIN if m.state == "live" else pal.LABEL_HI)
            )
            second = "TB" if (m.state == "live" and m.is_tiebreak) else m.round_code
            if second:
                rows[1].append((second, pal.TB if second == "TB" else pal.LABEL_HI))
        return rows

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.plugin import (
            compute_baseline_for_band,
            draw_text,
            measure_width,
            safe_scale,
        )

        if self.bg_color is not None:
            canvas.Fill(self.bg_color.red, self.bg_color.green, self.bg_color.blue)
        scale = safe_scale(canvas)
        half_h = canvas.height // 2
        baseline = compute_baseline_for_band(self.font, half_h, scale, valign="center")
        font = self.font

        for band, cells in enumerate(self._rows()):
            y = band * half_h + baseline + y_offset
            name, name_c = cells[0]
            rest = cells[1:]
            # right-to-left placement of the fixed cells
            x_right = canvas.width - 1
            placed: list[tuple[str, Color, int]] = []
            for text, color in reversed(rest):
                w = measure_width(font, text, canvas)
                x = x_right - w
                placed.append((text, color, x))
                x_right = x - _GAP - 1
            name_zone = max(0, x_right - _GAP)
            while name and measure_width(font, name, canvas) > name_zone:
                name = name[:-1]
            draw_text(canvas, font, name, 0, y, name_c)
            for text, color, x in placed:
                draw_text(canvas, font, text, x, y, color)
        return canvas, cursor_pos + canvas.width


def _build_match_message(
    m: MatchInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
    show_ranking: bool = False,
) -> SegmentMessage:
    """One scrolling line per match — the SAME segments the hi-res crawl
    paints, joined with spaces (the "*" serve marker hugs its name)."""
    segs: list[tuple[str, Color]] = []
    for i, (text, color) in enumerate(segments(m, tz, show_ranking=show_ranking)):
        if i and text != "*":
            segs.append((" ", pal.IDENT))
        segs.append((text, color))
    return SegmentMessage(
        segs,
        center=True,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        font_color=font_color,
    )


def _build_scoreboard_message(
    m: MatchInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> TennisScoreboardMessage:
    return TennisScoreboardMessage(
        match=m,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_SMALL,
        font_color=font_color,
    )
