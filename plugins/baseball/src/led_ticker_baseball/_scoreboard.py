"""MLBScoreboardMessage and its builder helpers.

Layout-collision audit 2026-07-16 (survey: tests/survey_layout_gaps.py):
- On >=~128-logical-px canvases (smallsign 160): collision-safe. Labels go
  through ``_fit_team_name`` (measured fallback), everything else is
  measured-and-centered in its zone or fixed-vocabulary.
- On NARROW logical canvases (bigsign at scale 4 = logical 64): the LIVE
  center zone is genuinely broken — the design assumes >=128 logical px
  (see the half_h comment), and at width 64 the center zone (26px, halves
  of 13px) cannot hold inning+outs / B/S / the diamond cluster: the outs
  dots overlap the 2B diamond and reach the home team name, and the
  diamonds overlap the B/S row, with TYPICAL data. GUARDED: ``draw()``
  raises below ``_MIN_LOGICAL_WIDTH`` (measured floor 128 — worst case is
  clean at 128/160, overlaps at 112, piles up at 64), steering narrow
  scale-1 canvases to ``layout = "two_row"``/``"ticker"`` — the two_row
  band-guard precedent (core's render breaker surfaces the message; the
  panel keeps running).

POST-UPLIFT NOTE (baseball design uplift, 2026-07): this class is now the
LEGACY scale-1 renderer only. ``MLBGameCard`` (see ``_card.py``) dispatches
scale>1 canvases to the physical ``layouts.scoreboard.render_scoreboard``
instead — a separate coordinate-authored renderer with no shared geometry
or floor. A bigsign/longboi sign running ``layout = "scoreboard"`` never
reaches this class or this guard; it gets the new physical scoreboard
automatically. This guard is retained as defense-in-depth for any scale-1
canvas narrower than the measured floor (this module is otherwise
untouched by the uplift).
"""

from datetime import datetime, timedelta
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
    colors,
    make_color,
)

from led_ticker_baseball._hires_line import HiresLine
from led_ticker_baseball._models import (
    GameInfo,
    SeriesInfo,
    _fit_team_name,
    _format_game_time,
)
from led_ticker_baseball.teams import (
    MLB_TEAM_NAMES,
    _team_color,
    _team_palette,
)

# Measured floor for the scoreboard layout (survey: tests/survey_layout_gaps.py):
# the worst-case live center zone (extra innings "▼15" + outs dots + full count
# + the base diamond) is collision-free at >=128 logical px (longboi 512/4 and
# smallsign 160 both clear), overlaps at 112 (extra innings), and piles up at
# 96 (typical data) and 64 (bigsign at scale 4). 128 is also the design's own
# stated assumption (the half_h comment below).
_MIN_LOGICAL_WIDTH = 128


@attrs.define
class MLBScoreboardMessage(FrameAwareBase):
    """Scoreboard-style two-column game display.

    Renders: [away team + score] [center: inning/BSO/diamond] [home team + score]
    with ABS challenge pips beside each team name.
    """

    game: GameInfo
    team_abbr: str
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)

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

        # Geometry guard (layout-collision audit 2026-07-16): below the
        # measured floor the live center zone collides (see module docstring).
        # Raise with the fix in the message — the two_row band-guard precedent:
        # core's render breaker trips this widget and surfaces the error
        # (status board / logs) while the rest of the rotation keeps running.
        # This class only ever runs at scale<=1 post-uplift (MLBGameCard
        # dispatches scale>1 to the physical layouts.scoreboard renderer), so
        # the message says so — a scale>1 sign is never affected by this raise.
        if canvas.width < _MIN_LOGICAL_WIDTH:
            raise ValueError(
                f"baseball.scores: layout='scoreboard' needs a canvas >= "
                f"{_MIN_LOGICAL_WIDTH} logical px wide (this canvas: "
                f"{canvas.width}) — the live center zone (inning/outs/count/"
                f"diamond) collides below that on this legacy scale-1 "
                f"renderer. Use layout='two_row' or 'ticker' on this sign. "
                f"(scale>1 signs get the new physical scoreboard "
                f"automatically and are unaffected by this guard.)"
            )

        scale = safe_scale(canvas)
        half_h = canvas.height // 2  # logical rows per band (8 on 128×16 canvas)

        # Zone widths (logical pixels)
        left_w = canvas.width * 30 // 100
        right_w = canvas.width * 30 // 100
        right_start = canvas.width - right_w

        # Baselines: top half (team names), bottom half (scores)
        top_baseline = compute_baseline_for_band(
            self.font, half_h, scale, valign="center"
        )
        bottom_baseline = half_h + compute_baseline_for_band(
            self.font, half_h, scale, valign="center"
        )

        game = self.game

        # Determine colors
        away_c = _team_color(game.away_abbr)
        home_c = _team_color(game.home_abbr)

        if game.state == "final":
            away_won = (game.away_score or 0) > (game.home_score or 0)
            win_c = _team_palette("WIN_COLOR")
            loss_c = _team_palette("LOSS_COLOR")
            away_score_c = win_c if away_won else loss_c
            home_score_c = loss_c if away_won else win_c
        else:
            away_score_c = colors.RGB_WHITE
            home_score_c = colors.RGB_WHITE

        def _draw_centered(
            text: str, zone_start: int, zone_w: int, y: int, color: Color
        ) -> None:
            w = measure_width(self.font, text, canvas)
            x = zone_start + max(0, (zone_w - w) // 2)
            draw_text(canvas, self.font, text, x, y + y_offset, color)

        away_abbr = game.away_abbr
        home_abbr = game.home_abbr

        # Use the full team name when it fits in the column; fall back to abbreviation.
        away_label = _fit_team_name(away_abbr, left_w, self.font, canvas)
        home_label = _fit_team_name(home_abbr, right_w, self.font, canvas)

        # Away team (left column)
        _draw_centered(away_label, 0, left_w, top_baseline, away_c)
        away_score_str = str(game.away_score) if game.away_score is not None else "–"
        _draw_centered(away_score_str, 0, left_w, bottom_baseline, away_score_c)

        # Home team (right column)
        _draw_centered(home_label, right_start, right_w, top_baseline, home_c)
        home_score_str = str(game.home_score) if game.home_score is not None else "–"
        _draw_centered(
            home_score_str, right_start, right_w, bottom_baseline, home_score_c
        )

        # ABS challenge dashes — two "-" stacked vertically, centered in the
        # gap between the score number and the outer edge of each zone.
        # Orange = remaining (unused), grey = used.
        # 5/8 and 7/8 through the bottom band → ~6px physical gap between
        # dashes at scale=4, matching the colon character's dot spacing.
        def _draw_dash_pips(count: int | None, align_right: bool) -> None:
            if count is None:
                return
            n = min(count, 2)
            dash_w = measure_width(self.small_font, "-", canvas)
            if align_right:
                score_w = measure_width(self.font, home_score_str, canvas)
                score_inner = right_start + max(0, (right_w - score_w) // 2) + score_w
                x = score_inner + max(0, (canvas.width - score_inner - dash_w) // 2)
            else:
                score_w = measure_width(self.font, away_score_str, canvas)
                score_inner = max(0, (left_w - score_w) // 2)
                x = max(0, (score_inner - dash_w) // 2)
            y1 = half_h + (5 * half_h) // 8
            y2 = half_h + (7 * half_h) // 8
            for i, y in enumerate((y1, y2)):
                color = (
                    _team_palette("CHALLENGE_COLOR")
                    if i < n
                    else _team_palette("CHALLENGE_USED")
                )
                draw_text(canvas, self.small_font, "-", x, y=y + y_offset, color=color)

        _draw_dash_pips(game.away_challenges, align_right=False)
        _draw_dash_pips(game.home_challenges, align_right=True)

        # --- Center zone ---
        center_total = canvas.width - left_w - right_w
        center_half = center_total // 2
        cl_start = left_w  # center-left x start
        cr_start = left_w + center_half  # center-right x start

        small_top = compute_baseline_for_band(
            self.small_font, half_h, scale, valign="center"
        )
        small_bottom = half_h + compute_baseline_for_band(
            self.small_font, half_h, scale, valign="center"
        )

        def _draw_small(text: str, x: int, y: int, color: Color) -> None:
            draw_text(canvas, self.small_font, text, x, y=y + y_offset, color=color)

        # Helper: draw primary-font text horizontally centered in the full
        # center zone (cl_start → right_start).
        def _draw_center(text: str, y: int, color: Color) -> None:
            w = measure_width(self.font, text, canvas)
            x = cl_start + max(0, (center_total - w) // 2)
            draw_text(canvas, self.font, text, x, y=y + y_offset, color=color)

        if game.state == "live":
            # Row 0: inning + outs dots
            inning_str = game.inning or "–"
            out_c = make_color(255, 80, 80)
            outs = game.outs or 0
            outs_str = "●" * outs + "○" * (3 - outs)
            _draw_small(inning_str, cl_start, small_top, colors.RGB_WHITE)
            inning_w = measure_width(self.small_font, inning_str, canvas)
            _draw_small(outs_str, cl_start + inning_w + 2, small_top, out_c)

            # Row 1: B/S count
            ball_c = make_color(80, 255, 80)
            strike_c = make_color(255, 255, 80)
            _draw_small(str(game.balls), cl_start, small_bottom, ball_c)
            b_w = measure_width(self.small_font, str(game.balls), canvas)
            _draw_small("B ", cl_start + b_w, small_bottom, colors.RGB_WHITE)
            bs_w = b_w + measure_width(self.small_font, "B ", canvas)
            _draw_small(str(game.strikes), cl_start + bs_w, small_bottom, strike_c)
            s_w = measure_width(self.small_font, str(game.strikes), canvas)
            _draw_small("S", cl_start + bs_w + s_w, small_bottom, colors.RGB_WHITE)

            # Diamond: center-right zone — use main font for larger glyphs.
            # Pack 3B/1B with a 2px gap, cluster centered in the zone.
            # 2B centered horizontally above the midpoint.
            occupied_c = make_color(255, 220, 50)  # yellow
            empty_c = make_color(50, 50, 50)  # dim
            b2 = "◆" if game.on_second else "◇"
            b3 = "◆" if game.on_third else "◇"
            b1 = "◆" if game.on_first else "◇"

            b2_c = occupied_c if game.on_second else empty_c
            b3_c = occupied_c if game.on_third else empty_c
            b1_c = occupied_c if game.on_first else empty_c

            dw = measure_width(self.font, b2, canvas)
            diamond_gap = 2
            cluster_w = 2 * dw + diamond_gap
            cluster_x = cr_start + max(0, (center_half - cluster_w) // 2)
            b3_x = cluster_x
            b1_x = cluster_x + dw + diamond_gap
            b2_x = cluster_x + dw + diamond_gap // 2 - dw // 2

            # 2B uses top-band center baseline; 3B/1B use bottom-band
            # bottom-aligned so the glyphs sit inside the band without clip.
            diamond_top_y = compute_baseline_for_band(
                self.font, half_h, scale, valign="center"
            )
            diamond_bot_y = half_h + compute_baseline_for_band(
                self.font, half_h, scale, valign="bottom"
            )
            draw_text(
                canvas, self.font, b2, b2_x, y=diamond_top_y + y_offset, color=b2_c
            )
            draw_text(
                canvas, self.font, b3, b3_x, y=diamond_bot_y + y_offset, color=b3_c
            )
            draw_text(
                canvas, self.font, b1, b1_x, y=diamond_bot_y + y_offset, color=b1_c
            )

        elif game.state == "final":
            full_baseline = compute_baseline_for_band(
                self.font, canvas.height, scale, valign="center"
            )
            _draw_center("FINAL", full_baseline, make_color(180, 180, 180))

        elif game.state == "preview":
            _tz = self.tz or ZoneInfo("UTC")
            if game.start_time:
                local = game.start_time.astimezone(_tz)
                now = datetime.now(_tz)
                if local.date() == now.date():
                    date_str = "Today"
                elif local.date() == (now + timedelta(days=1)).date():
                    date_str = "Tmrw"
                else:
                    date_str = local.strftime("%a")
                time_str = local.strftime("%-I:%M %p")
            else:
                date_str = ""
                time_str = "TBD"
            _draw_center(date_str, top_baseline, make_color(160, 160, 160))
            _draw_center(time_str, bottom_baseline, colors.RGB_WHITE)

        elif game.state == "postponed":
            tag_c = make_color(255, 200, 60)
            _draw_center(game.postpone_tag, top_baseline, tag_c)
            if game.postpone_reason:
                _draw_center(game.postpone_reason[:6], bottom_baseline, tag_c)

        elif game.state == "off_day":
            _draw_center("–", top_baseline, make_color(120, 120, 120))

        return canvas, cursor_pos + canvas.width


def _build_series_title(
    team_abbr: str,
    series: SeriesInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> HiresLine:
    """Build the title message for a series.

    Uses AWAY @ HOME when all games share the same home team,
    otherwise falls back to neutral 'vs' separator.

    Returns a ``HiresLine``: hi-res Inter on a scale>1 sign (bigsign /
    longboi), byte-identical BDF ``SegmentMessage`` fallback at scale<=1
    (smallsign) — this is the series-record line shown at the top of
    every scores rotation, so it's the highest-visibility non-hero line
    in the widget.
    """
    team_c = _team_color(team_abbr)
    opp_c = _team_color(series.opponent_abbr)

    # Determine if all games share the same home team
    home_teams = {g.home_abbr for g in series.games}
    all_same_home = len(home_teams) == 1

    if all_same_home:
        home = next(iter(home_teams))
        away = team_abbr if home != team_abbr else series.opponent_abbr
        away_c = _team_color(away)
        home_c = _team_color(home)
        away_name = MLB_TEAM_NAMES.get(away, away)
        home_name = MLB_TEAM_NAMES.get(home, home)
        segments: list[tuple[str, Color]] = [
            (away_name, away_c),
            (" @ ", colors.RGB_WHITE),
            (home_name, home_c),
        ]
        # First listed team is away, second is home
        first_is_team = away == team_abbr
    else:
        team_name = MLB_TEAM_NAMES.get(team_abbr, team_abbr)
        opp_name = MLB_TEAM_NAMES.get(series.opponent_abbr, series.opponent_abbr)
        segments = [
            (team_name, team_c),
            (" vs ", colors.RGB_WHITE),
            (opp_name, opp_c),
        ]
        # First listed team is always team_abbr
        first_is_team = True

    # Show (ST) / (ASG) with inline emoji slug for special game types.
    # The slug renders as an 8×8 pixel-art icon via the standard emoji
    # path (or 32×32 hi-res on the bigsign — free upgrade vs the
    # previous 5×5 mlb_icons sprites).
    is_spring = any(g.game_type == "S" for g in series.games)
    is_allstar = any(g.game_type == "A" for g in series.games)
    if is_spring:
        segments.append((" (ST) :flower:", colors.RGB_WHITE))
    elif is_allstar:
        segments.append((" (ASG) :star:", colors.RGB_WHITE))

    # Show series record ordered to match team name positions
    total_games = len(series.games)
    total_decided = series.team_wins + series.team_losses
    if total_games > 1 and total_decided > 0:
        if first_is_team:
            record = f" {series.team_wins}-{series.team_losses}"
        else:
            record = f" {series.team_losses}-{series.team_wins}"
        segments.append((record, colors.RGB_WHITE))

    # Center the title if it fits on screen. HiresLine forwards to this same
    # SegmentMessage (byte-identical) at scale<=1; at scale>1 it draws
    # `segments` itself in hi-res, so wording/colors can't drift between the
    # two paths.
    legacy = SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )
    return HiresLine(segments, legacy=legacy, center=True)


def _build_game_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
    """Build a message for a single game.

    Uses standard baseball convention: away team listed first.
    """
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)

    if game.state == "final":
        away_won = (game.away_score or 0) > (game.home_score or 0)
        win_color = _team_palette("WIN_COLOR")
        loss_color = _team_palette("LOSS_COLOR")
        away_score_color = win_color if away_won else loss_color
        home_score_color = loss_color if away_won else win_color

        segments: list[tuple[str, Color]] = [
            (game.away_abbr, away_c),
            (f" {game.away_score}", away_score_color),
            (" ", colors.RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {game.home_score}", home_score_color),
            (" (Final)", colors.RGB_WHITE),
        ]

    elif game.state == "live":
        inning_str = f" {game.inning}" if game.inning else ""

        # Base diamonds: ◇ = empty, ◆ = occupied (3rd-2nd-1st)
        b3 = "◆" if game.on_third else "◇"
        b2 = "◆" if game.on_second else "◇"
        b1 = "◆" if game.on_first else "◇"

        # BSO in color: B|S|O
        ball_c = make_color(80, 255, 80)  # green
        strike_c = make_color(255, 255, 80)  # yellow
        out_c = make_color(255, 80, 80)  # red

        segments = [
            (game.away_abbr, away_c),
            (f" {game.away_score}", colors.RGB_WHITE),
            (" ", colors.RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {game.home_score}", colors.RGB_WHITE),
            (inning_str, colors.RGB_WHITE),
            (f" {b3}{b2}{b1}", colors.RGB_WHITE),
            (f" {game.balls}", ball_c),
            ("·", colors.RGB_WHITE),
            (f"{game.strikes}", strike_c),
            ("·", colors.RGB_WHITE),
            (f"{game.outs}", out_c),
        ]

    elif game.state == "postponed":
        # Rain delay / cancelled / suspended / completed early. Show team
        # vs team with a short tag and reason if available, instead of
        # "(Final)" + None scores.
        tag_color = make_color(255, 200, 60)  # amber — distinct from win/loss/white
        if game.postpone_reason:
            tag = f" ({game.postpone_tag}: {game.postpone_reason})"
        else:
            tag = f" ({game.postpone_tag})"
        segments = [
            (game.away_abbr, away_c),
            (" @ ", colors.RGB_WHITE),
            (game.home_abbr, home_c),
            (tag, tag_color),
        ]

    else:  # preview
        time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
        segments = [
            (game.away_abbr, away_c),
            (" @ ", colors.RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {time_str}", colors.RGB_WHITE),
        ]

    return SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


def _build_scoreboard_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBScoreboardMessage:
    """Build a scoreboard-layout message for a single game."""
    return MLBScoreboardMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        small_font=small_font if small_font is not None else FONT_SMALL,
        font_color=font_color,
    )
