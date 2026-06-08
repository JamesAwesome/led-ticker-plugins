"""MLB score monitor widget using the free MLB Stats API."""

import asyncio
import contextlib
import difflib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

import aiohttp
import attrs

from led_ticker.plugin import (
    Canvas,
    Color,
    ColorProvider,
    DrawResult,
    FONT_DEFAULT,
    FONT_SMALL,
    Font,
    FrameAwareBase,
    SegmentMessage,
    TickerMessage,
    colors,
    make_color,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_baseball.teams import (
    MLB_API,
    MLB_TEAM_NAMES,
    _MLB_LIVE_API,
    _team_color,
    _team_palette,
)

logger: logging.Logger = logging.getLogger(__name__)

# Supported layouts and the per-row knobs that only apply to "two_row".
# Mirrors core's _MLB_VALID_LAYOUTS / _TWO_ROW_ONLY (formerly checked in
# led_ticker.app.factories for type == "mlb"); restored here as a
# validate_config classmethod now that baseball.scores owns the widget.
_MLB_VALID_LAYOUTS: tuple[str, ...] = ("ticker", "scoreboard", "two_row")
_TWO_ROW_ONLY: tuple[str, ...] = (
    "top_font",
    "top_font_size",
    "top_font_threshold",
    "top_row_height",
)


def _fit_team_name(abbr: str, zone_w: int, font: Font, canvas: Canvas) -> str:
    """Return the short team name if it fits in zone_w logical pixels, else abbr."""
    from led_ticker.plugin import measure_width

    name = MLB_TEAM_NAMES.get(abbr, abbr)
    return name if measure_width(font, name, canvas) <= zone_w else abbr


@dataclass
class GameInfo:
    home_abbr: str
    away_abbr: str
    home_score: int | None = None
    away_score: int | None = None
    state: str = "preview"  # "final", "live", "preview", "postponed"
    game_type: str = "R"  # R=regular, S=spring, A=all-star, P+=postseason
    inning: str | None = None
    balls: int = 0
    strikes: int = 0
    outs: int = 0
    on_first: bool = False
    on_second: bool = False
    on_third: bool = False
    start_time: datetime | None = None
    game_pk: int = 0
    # For state="postponed": short reason like "Rain" or "" if unknown
    postpone_reason: str = ""
    # For state="postponed": short tag like "PPD", "SUSP", "CANC"
    postpone_tag: str = "PPD"
    # ABS challenge counts (None = system not in effect / data unavailable)
    home_challenges: int | None = None
    away_challenges: int | None = None


@dataclass
class SeriesInfo:
    opponent_abbr: str
    games: list[GameInfo] = field(default_factory=list)
    team_wins: int = 0
    team_losses: int = 0


def _ordinal(n: int) -> str:
    """Convert integer to ordinal string: 1st, 2nd, 3rd, etc."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd'][min(n % 10, 4)] if n % 10 < 4 else 'th'}"


def _format_inning(inning_num: int, half: str) -> str:
    """Format inning display: '▲5', '▼7'."""
    arrow = "\u25b2" if half == "top" else "\u25bc"
    return f"{arrow}{inning_num}"


def _format_game_time(dt: datetime, tz: ZoneInfo) -> str:
    """Format game time relative to now."""
    now = datetime.now(tz)
    local = dt.astimezone(tz)

    if local.date() == now.date():
        return f"Today {local.strftime('%-I:%M %p')}"
    if local.date() == (now + timedelta(days=1)).date():
        return f"Tmrw {local.strftime('%-I:%M %p')}"
    days_out = (local.date() - now.date()).days
    if days_out <= 6:
        return local.strftime("%a %-I:%M %p")
    return local.strftime("%b %-d %-I:%M %p")


def _classify_postponement(detailed_state: str) -> tuple[str | None, str]:
    """Map a `status.detailedState` string to (game_state, short_tag).

    Returns (None, "PPD") for non-postponement states; the caller should
    fall back to abstractGameState in that case.

    Examples of detailedState values from the MLB API:
      "Postponed"                  → ("postponed", "PPD")
      "Cancelled"                  → ("postponed", "CANC")
      "Suspended"                  → ("postponed", "SUSP")
      "Suspended: Rain"            → ("postponed", "SUSP")
      "Completed Early"            → ("postponed", "EARLY")
      "Completed Early: Rain"      → ("postponed", "EARLY")
    """
    s = detailed_state.lower()
    if "postponed" in s:
        return "postponed", "PPD"
    if "cancelled" in s or "canceled" in s:
        return "postponed", "CANC"
    if "suspended" in s:
        return "postponed", "SUSP"
    if "completed early" in s:
        return "postponed", "EARLY"
    return None, "PPD"


def _parse_team_abbr(team_data: dict[str, Any]) -> str:
    """Extract team abbreviation from MLB API team data."""
    return team_data.get("abbreviation", "???")


def _build_series_title(
    team_abbr: str,
    series: SeriesInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
    """Build the title message for a series.

    Uses AWAY @ HOME when all games share the same home team,
    otherwise falls back to neutral 'vs' separator.
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

    # Center the title if it fits on screen
    return SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


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
        b3 = "\u25c6" if game.on_third else "\u25c7"
        b2 = "\u25c6" if game.on_second else "\u25c7"
        b1 = "\u25c6" if game.on_first else "\u25c7"

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
            ("\u00b7", colors.RGB_WHITE),
            (f"{game.strikes}", strike_c),
            ("\u00b7", colors.RGB_WHITE),
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
        canvas: Canvas,
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
                draw_text(
                    canvas, self.small_font, "-", x, y=y + y_offset, color=color
                )

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
            draw_text(
                canvas, self.small_font, text, x, y=y + y_offset, color=color
            )

        # Helper: draw primary-font text horizontally centered in the full
        # center zone (cl_start → right_start).
        def _draw_center(text: str, y: int, color: Color) -> None:
            w = measure_width(self.font, text, canvas)
            x = cl_start + max(0, (center_total - w) // 2)
            draw_text(
                canvas, self.font, text, x, y=y + y_offset, color=color
            )

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


def _compute_preview_two_row(
    game: GameInfo,
    team_abbr: str,  # uniform signature — used by final/live/postponed helpers
    tz: ZoneInfo,
    series_wins: int,
    series_losses: int,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    """Compute top/bottom segment lists for a preview-state game."""
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (" @ ", colors.RGB_WHITE),
        (game.home_abbr, home_c),
    ]
    if series_wins + series_losses > 0:
        grey_record = make_color(150, 150, 150)  # grey — series record
        top.append((f" ({series_wins}-{series_losses})", grey_record))
    time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
    bot: list[tuple[str, Color]] = [(time_str, colors.RGB_WHITE)]
    return top, bot


def _pip_segments(count: int | None, small_font: Font) -> list[tuple[str, Color, Font]]:
    """ABS challenge pip dashes for one team's score.

    Returns empty list when count is None (ABS not in effect).
    Orange dashes for remaining challenges, grey for used (max 2 shown).
    Pips use small_font so they render smaller than the main score text.
    """
    if count is None:
        return []
    chal_c = _team_palette("CHALLENGE_COLOR")
    used_c = _team_palette("CHALLENGE_USED")
    n = min(count, 2)
    return [("-", chal_c if i < n else used_c, small_font) for i in range(2)]


def _compute_final_two_row(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,  # uniform signature — unused here
    series_wins: int,
    series_losses: int,
    series_total_games: int = 1,
    small_font: Font | None = None,
) -> tuple[list, list]:
    """Compute top/bottom segment lists for a final-state game."""
    _small_font = small_font if small_font is not None else FONT_SMALL
    win_c = _team_palette("WIN_COLOR")
    loss_c = _team_palette("LOSS_COLOR")
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    away_won = (game.away_score or 0) > (game.home_score or 0)
    away_score_c = win_c if away_won else loss_c
    home_score_c = loss_c if away_won else win_c

    away_score_str = str(game.away_score) if game.away_score is not None else "–"
    home_score_str = str(game.home_score) if game.home_score is not None else "–"

    top: list = []
    top.append((game.away_abbr, away_c))
    top.append((f" {away_score_str}", away_score_c))
    top.extend(_pip_segments(game.away_challenges, _small_font))
    top.append(("  ", colors.RGB_WHITE))
    top.append((game.home_abbr, home_c))
    top.append((f" {home_score_str}", home_score_c))
    top.extend(_pip_segments(game.home_challenges, _small_font))

    grey = make_color(180, 180, 180)  # grey — FINAL label
    bot: list[tuple[str, Color]] = [("FINAL", grey)]

    if series_total_games > 1 and (series_wins + series_losses) > 0:
        bot.append((" · ", grey))
        if series_wins > series_losses:
            leader_abbr = team_abbr
        elif series_losses > series_wins:
            opp = game.home_abbr if game.away_abbr == team_abbr else game.away_abbr
            leader_abbr = opp
        else:
            leader_abbr = None

        if leader_abbr is None:
            bot.append((f"Tied {series_wins}-{series_losses}", colors.RGB_WHITE))
        else:
            bot.append((leader_abbr, _team_color(leader_abbr)))
            bot.append((f" leads {series_wins}-{series_losses}", colors.RGB_WHITE))

    return top, bot


def _compute_live_two_row(
    game: GameInfo,
    team_abbr: str,  # uniform signature — unused here
    tz: ZoneInfo,    # uniform signature — unused here
    series_wins: int,   # uniform signature — unused here
    series_losses: int, # uniform signature — unused here
    small_font: Font | None = None,
) -> tuple[list, list]:
    """Compute top/bottom segment lists for a live-state game."""
    _small_font = small_font if small_font is not None else FONT_SMALL
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    away_score_str = str(game.away_score) if game.away_score is not None else "–"
    home_score_str = str(game.home_score) if game.home_score is not None else "–"

    top: list = []
    top.append((game.away_abbr, away_c))
    top.append((f" {away_score_str}", colors.RGB_WHITE))
    top.extend(_pip_segments(game.away_challenges, _small_font))
    top.append(("  ", colors.RGB_WHITE))
    top.append((game.home_abbr, home_c))
    top.append((f" {home_score_str}", colors.RGB_WHITE))
    top.extend(_pip_segments(game.home_challenges, _small_font))

    live_c = _team_palette("LIVE_COLOR")
    ball_c = make_color(80, 255, 80)    # green — balls
    strike_c = make_color(255, 255, 80)  # yellow — strikes
    out_c = make_color(255, 80, 80)     # red — outs
    occupied_c = make_color(255, 220, 50)  # yellow — occupied base
    empty_c = make_color(50, 50, 50)       # dim — empty base

    inning_str = game.inning or "–"
    b3 = "◆" if game.on_third else "◇"
    b2 = "◆" if game.on_second else "◇"
    b1 = "◆" if game.on_first else "◇"
    b3_c = occupied_c if game.on_third else empty_c
    b2_c = occupied_c if game.on_second else empty_c
    b1_c = occupied_c if game.on_first else empty_c

    bot: list[tuple[str, Color]] = [
        (inning_str, live_c),
        ("  ", colors.RGB_WHITE),
        (b3, b3_c),
        (b2, b2_c),
        (b1, b1_c),
        ("  ", colors.RGB_WHITE),
        (str(game.balls), ball_c),
        ("·", colors.RGB_WHITE),
        (str(game.strikes), strike_c),
        ("·", colors.RGB_WHITE),
        (str(game.outs), out_c),
    ]
    return top, bot


def _compute_postponed_two_row(
    game: GameInfo,
    team_abbr: str,    # uniform signature — unused here
    tz: ZoneInfo,      # uniform signature — unused here
    series_wins: int,  # uniform signature — unused here
    series_losses: int, # uniform signature — unused here
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    """Compute top/bottom segment lists for a postponed-state game."""
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (" @ ", colors.RGB_WHITE),
        (game.home_abbr, home_c),
    ]
    tag_color = make_color(255, 200, 60)  # amber — postponed/cancelled tag
    if game.postpone_reason:
        tag = f"{game.postpone_tag}: {game.postpone_reason}"
    else:
        tag = game.postpone_tag
    bot: list[tuple[str, Color]] = [(tag, tag_color)]
    return top, bot


def _build_two_row_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    top_font: Font | None = None,
    top_row_height: int | None = None,
    font_color: Color | ColorProvider | None = None,
    series_wins: int = 0,
    series_losses: int = 0,
    series_total_games: int = 1,
) -> MLBTwoRowMessage:
    """Build a two-row layout message for a single game."""
    _small_font = small_font if small_font is not None else FONT_SMALL
    if game.state == "preview":
        top_segs, bot_segs = _compute_preview_two_row(
            game, team_abbr, tz, series_wins, series_losses
        )
    elif game.state == "final":
        top_segs, bot_segs = _compute_final_two_row(
            game, team_abbr, tz, series_wins, series_losses, series_total_games,
            small_font=_small_font,
        )
    elif game.state == "live":
        top_segs, bot_segs = _compute_live_two_row(
            game, team_abbr, tz, series_wins, series_losses,
            small_font=_small_font,
        )
    elif game.state == "postponed":
        top_segs, bot_segs = _compute_postponed_two_row(
            game, team_abbr, tz, series_wins, series_losses
        )
    else:
        top_segs, bot_segs = [], []
    # Preview / postponed lead with an "AWAY @ HOME" matchup that draw() can
    # expand to full team names when it fits. Score screens (final / live)
    # use the abbr+score format and aren't expanded.
    matchup = (
        (game.away_abbr, game.home_abbr)
        if game.state in ("preview", "postponed")
        else None
    )
    return MLBTwoRowMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_SMALL,
        small_font=small_font if small_font is not None else FONT_SMALL,
        top_font=top_font,
        top_row_height=top_row_height,
        font_color=font_color,
        top_segments=top_segs,
        bottom_segments=bot_segs,
        matchup=matchup,
    )


def _build_two_row_series_title(
    team_abbr: str,
    series: SeriesInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    top_font: Font | None = None,
    top_row_height: int | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBTwoRowMessage:
    """Two-band series title for two_row layout.

    Top band carries the matchup (`Away @ Home`, or `team vs opp` for a
    split-home series) in team colors. Bottom band carries the series
    record (`PHI leads 2-1` / `Tied 1-1`, same form as the FINAL card) and
    any (ST)/(ASG) special-game badge. Mirrors `_build_series_title`'s
    matchup/badge logic; only the layout differs.
    """
    team_c = _team_color(team_abbr)
    opp_c = _team_color(series.opponent_abbr)

    home_teams = {g.home_abbr for g in series.games}
    all_same_home = len(home_teams) == 1

    if all_same_home:
        home = next(iter(home_teams))
        away = team_abbr if home != team_abbr else series.opponent_abbr
        away_name = MLB_TEAM_NAMES.get(away, away)
        home_name = MLB_TEAM_NAMES.get(home, home)
        top: list[tuple[str, Color]] = [
            (away_name, _team_color(away)),
            (" @ ", colors.RGB_WHITE),
            (home_name, _team_color(home)),
        ]
    else:
        team_name = MLB_TEAM_NAMES.get(team_abbr, team_abbr)
        opp_name = MLB_TEAM_NAMES.get(series.opponent_abbr, series.opponent_abbr)
        top = [
            (team_name, team_c),
            (" vs ", colors.RGB_WHITE),
            (opp_name, opp_c),
        ]

    # Bottom band: series record (leader-relative, like the FINAL card).
    bot: list[tuple[str, Color]] = []
    total_games = len(series.games)
    total_decided = series.team_wins + series.team_losses
    if total_games > 1 and total_decided > 0:
        leader_abbr: str | None = None
        w = lo = 0
        if series.team_wins > series.team_losses:
            leader_abbr = team_abbr
            w, lo = series.team_wins, series.team_losses
        elif series.team_losses > series.team_wins:
            leader_abbr = series.opponent_abbr
            w, lo = series.team_losses, series.team_wins
        if leader_abbr is None:
            bot.append((f"Tied {series.team_wins}-{series.team_losses}", colors.RGB_WHITE))
        else:
            bot.append((leader_abbr, _team_color(leader_abbr)))
            bot.append((f" leads {w}-{lo}", colors.RGB_WHITE))

    # Special-game badge on the bottom band, after any record.
    is_spring = any(g.game_type == "S" for g in series.games)
    is_allstar = any(g.game_type == "A" for g in series.games)
    badge = ""
    if is_spring:
        badge = "(ST) :flower:"
    elif is_allstar:
        badge = "(ASG) :star:"
    if badge:
        if bot:
            bot.append(("  ", colors.RGB_WHITE))
        bot.append((badge, colors.RGB_WHITE))

    return MLBTwoRowMessage(
        game=series.games[0],
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_SMALL,
        small_font=small_font if small_font is not None else FONT_SMALL,
        top_font=top_font,
        top_row_height=top_row_height,
        font_color=font_color,
        top_segments=top,
        bottom_segments=bot,
    )


def _expand_matchup_if_fits(
    top_segments: list[tuple[str, Color]],
    matchup: tuple[str, str],
    font: Font,
    canvas: Canvas,
) -> list[tuple[str, Color]]:
    """Expand the leading ``AWAY @ HOME`` matchup to full team names when the
    whole top band still fits ``canvas.width``; otherwise keep abbreviations.

    The matchup is always the first three top segments (away, " @ ", home);
    segments [0] and [2] are rebuilt from ``matchup``'s abbreviations via
    ``MLB_TEAM_NAMES`` so we never string-match the existing segment text.
    Both names expand together or neither does — matching the series-title
    aesthetic and the per-team fit-or-fallback of ``_fit_team_name``.
    """
    from led_ticker.plugin import measure_width

    if len(top_segments) < 3:
        return top_segments
    away_abbr, home_abbr = matchup
    away_full = MLB_TEAM_NAMES.get(away_abbr, away_abbr)
    home_full = MLB_TEAM_NAMES.get(home_abbr, home_abbr)
    if away_full == away_abbr and home_full == home_abbr:
        return top_segments  # no fuller form available for either team

    candidate = list(top_segments)
    candidate[0] = (away_full, top_segments[0][1])
    candidate[2] = (home_full, top_segments[2][1])
    total = sum(measure_width(font, seg[0], canvas) for seg in candidate)
    return candidate if total <= canvas.width else top_segments


@attrs.define
class MLBTwoRowMessage(FrameAwareBase):
    """Two-band game display: score/matchup on top, status on bottom."""

    game: GameInfo
    team_abbr: str
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    # Default FONT_SMALL (line-height 8) so the default 8-row band fits — same
    # default as TwoRowMessage, and what the band-overflow guard in draw()
    # assumes for the no-font-configured case.
    font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    top_segments: list[tuple[str, Color]] = attrs.field(factory=list)
    bottom_segments: list[tuple[str, Color]] = attrs.field(factory=list)
    # (away_abbr, home_abbr) when the top band leads with an "AWAY @ HOME"
    # matchup (preview / postponed). draw() expands these to full team names
    # when they fit the canvas width, else keeps the abbreviations.
    matchup: tuple[str, str] | None = attrs.field(default=None, kw_only=True)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.plugin import (
            compute_baseline_for_band,
            draw_text,
            font_line_height_logical,
            measure_width,
            resolve_band_heights,
            safe_scale,
        )

        scale = safe_scale(canvas)
        top_h, bot_h = resolve_band_heights(canvas.height, self.top_row_height)
        top_font = self.top_font if self.top_font is not None else self.font
        bot_font = self.font

        # Validate each row's font fits within its band (logical units).
        # `font_line_height_logical` handles the BDF-vs-HiresFont branch
        # (BDF returns logical px, HiresFont ceil-divs by scale). Mirrors
        # TwoRowMessage.draw's guard: any font (BDF or hires) whose line-height
        # exceeds its band raises with the offending row named, rather than
        # silently clipping. The widget's default font is FONT_SMALL
        # (line-height 8) so the default 8-row band fits without overriding.
        for row_label, row_font, band_h in (
            ("top", top_font, top_h),
            ("bottom", bot_font, bot_h),
        ):
            font_lh_logical = font_line_height_logical(row_font, scale)
            if font_lh_logical > band_h:
                raise ValueError(
                    f"{row_label} font line-height ({font_lh_logical} logical "
                    f"rows) exceeds the per-row band ({band_h} rows on a "
                    f"{canvas.height}-tall canvas). Pick a smaller font_size, "
                    f"increase the section's content_height, adjust "
                    f"top_row_height for an asymmetric split, or use a BDF "
                    f"alias (5x8, 6x12)."
                )

        top_baseline = compute_baseline_for_band(
            top_font, top_h, scale, valign="center"
        )
        bot_baseline = top_h + compute_baseline_for_band(
            bot_font, bot_h, scale, valign="center"
        )

        def _render_segments(
            segments: list,
            baseline: int,
            default_font: Font,
        ) -> None:
            if not segments:
                return
            # Measure total width using per-segment font override when present
            total_w = 0
            for seg in segments:
                seg_font = seg[2] if len(seg) == 3 else default_font
                total_w += measure_width(seg_font, seg[0], canvas)
            x = max(0, (canvas.width - total_w) // 2)
            for seg in segments:
                seg_font = seg[2] if len(seg) == 3 else default_font
                x = draw_text(
                    canvas, seg_font, seg[0], x, baseline + y_offset, seg[1]
                )

        top_segs = self.top_segments
        if self.matchup is not None:
            top_segs = _expand_matchup_if_fits(
                top_segs, self.matchup, top_font, canvas
            )

        _render_segments(top_segs, top_baseline, top_font)
        _render_segments(self.bottom_segments, bot_baseline, bot_font)

        return canvas, cursor_pos + canvas.width


_MLBStoryT = TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage


@attrs.define
class MLBScoreMonitor:
    """MLB scores for a single team's current series."""

    session: aiohttp.ClientSession
    team: str
    timezone: str = "America/New_York"
    padding: int = 6
    final_hold_hours: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    # None when the config omits `font`. Resolved per-layout at draw-build time:
    # two_row falls back to FONT_SMALL (fits an 8-row band), ticker / scoreboard
    # fall back to FONT_DEFAULT. See the `display_font` resolution in update().
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    layout: str = attrs.field(default="ticker", kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    feed_title: _MLBStoryT | None = attrs.field(init=False, default=None)
    feed_stories: list[_MLBStoryT] = attrs.field(init=False, factory=list)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Reproduces the two guardrails core formerly applied to ``type =
        "mlb"`` in ``led_ticker.app.factories`` (now dead under the
        ``baseball.scores`` plugin): a valid ``layout`` value, and the
        per-row ``top_*`` knobs only being meaningful with
        ``layout = "two_row"``. Returns message strings (does NOT raise);
        the engine turns any returned messages into a pre-flight ValueError.
        """
        msgs: list[str] = []

        layout = cfg.get("layout", "ticker")
        if layout not in _MLB_VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), _MLB_VALID_LAYOUTS, n=1, cutoff=0.5
            )
            suggestion = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in _MLB_VALID_LAYOUTS)
            msgs.append(
                f"mlb layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{suggestion}"
            )

        # Per-row knobs only apply under two_row. Naming the offending
        # field(s) instead of silently ignoring them catches stale configs.
        if layout != "two_row":
            dead = [k for k in _TWO_ROW_ONLY if k in cfg]
            if dead:
                fields = ", ".join(repr(k) for k in dead)
                msgs.append(
                    f"{fields} only applies when layout='two_row'; "
                    f"remove the field(s) or set layout='two_row'."
                )

        return msgs

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        team: str,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBScoreMonitor.start: team=%s", team)
        widget = cls(session=session, team=team.upper(), **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        await widget._resolve_team_id()
        await widget.update()
        logger.info(
            "MLB %s: %d stories",
            team,
            len(widget.feed_stories),
        )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def _resolve_team_id(self) -> None:
        """Fetch team ID from MLB API."""
        url = f"{MLB_API}/teams?sportId=1"
        logger.debug("MLB: resolving team ID for %s", self.team)
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
                for t in data.get("teams", []):
                    if t.get("abbreviation") == self.team:
                        self._team_id = t["id"]
                        logger.debug("MLB: %s → id %d", self.team, self._team_id)
                        return
            logger.warning("Team %s not found in MLB API", self.team)
        except Exception:
            logger.exception("Failed to resolve team ID for %s", self.team)

    async def update(self) -> None:
        """Fetch schedule and build display messages."""
        team_name = MLB_TEAM_NAMES.get(self.team, self.team)
        tz = self._tz or ZoneInfo(self.timezone)

        # Resolve effective colors: honour explicit font_color override,
        # else fall back to the per-widget defaults.
        title_color = (
            self.font_color if self.font_color is not None else _team_color(self.team)
        )
        body_color = self.font_color if self.font_color is not None else colors.RGB_WHITE

        if not self._team_id:
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        now = datetime.now(tz)
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=7)).strftime("%Y-%m-%d")

        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            f"&hydrate=team,linescore"
        )

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("MLB API error for %s", self.team)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        try:
            games = self._parse_games(data, tz)
        except Exception:
            logger.exception("MLB parse error for %s", self.team)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        # Concurrently hydrate ABS challenge counts for live games.
        live_games = [g for g in games if g.state == "live" and g.game_pk]
        if live_games:
            results = await asyncio.gather(
                *(self._fetch_abs_challenges(g.game_pk) for g in live_games)
            )
            for g, (home_ch, away_ch) in zip(live_games, results, strict=False):
                g.home_challenges = home_ch
                g.away_challenges = away_ch

        if not games:
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage(
                    "Season Over", font_color=body_color, bg_color=self.bg_color
                ),
            ]
            logger.info(
                "MLB %s updated: %d stories (season over)",
                self.team,
                len(self.feed_stories),
            )
            return

        series = self._group_into_series(games)
        current = self._find_current_series(series, now)

        if current is None:
            # No current series — find next
            next_game = self._find_next_game(games, now)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            next_label = "season over"
            if next_game:
                opp = (
                    next_game.away_abbr
                    if next_game.home_abbr == self.team
                    else next_game.home_abbr
                )
                opp_name = MLB_TEAM_NAMES.get(opp, opp)
                next_label = opp_name
                if next_game.start_time:
                    time_str = _format_game_time(next_game.start_time, tz)
                else:
                    time_str = "TBD"
                self.feed_stories = [
                    title,
                    TickerMessage(
                        f"Next: vs {opp_name}, {time_str}",
                        font_color=body_color,
                        bg_color=self.bg_color,
                    ),
                ]
            else:
                self.feed_stories = [
                    title,
                    TickerMessage(
                        "Season Over", font_color=body_color, bg_color=self.bg_color
                    ),
                ]
            logger.info(
                "MLB %s updated: %d stories (next: %s)",
                self.team,
                len(self.feed_stories),
                next_label,
            )
            return

        # Build display from current series.
        # Resolve the effective font: two_row falls back to FONT_SMALL (fits an
        # 8-row band under the band-overflow guard), ticker / scoreboard fall
        # back to FONT_DEFAULT. A configured font is used as-is for all layouts.
        if self.font is not None:
            display_font = self.font
        elif self.layout == "two_row":
            display_font = FONT_SMALL
        else:
            display_font = FONT_DEFAULT

        if self.layout == "two_row":
            series_title: _MLBStoryT = _build_two_row_series_title(
                self.team,
                current,
                tz,
                bg_color=self.bg_color,
                font=display_font,
                small_font=self.small_font,
                top_font=self.top_font,
                top_row_height=self.top_row_height,
                font_color=self.font_color,
            )
        else:
            series_title = _build_series_title(
                self.team,
                current,
                tz,
                bg_color=self.bg_color,
                font=display_font,
                font_color=self.font_color,
            )
        self.feed_title = series_title
        stories: list[_MLBStoryT] = [series_title]
        if self.layout == "scoreboard":
            stories.extend(
                _build_scoreboard_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=display_font,
                    small_font=self.small_font,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        elif self.layout == "two_row":
            stories.extend(
                _build_two_row_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=display_font,
                    small_font=self.small_font,
                    top_font=self.top_font,
                    top_row_height=self.top_row_height,
                    font_color=self.font_color,
                    series_wins=current.team_wins,
                    series_losses=current.team_losses,
                    series_total_games=len(current.games),
                )
                for g in current.games
            )
        else:
            stories.extend(
                _build_game_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=display_font,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        self.feed_stories = stories
        n_live = sum(1 for g in current.games if g.state == "live")
        logger.info(
            "MLB %s updated: %d stories (live: %d)",
            self.team,
            len(self.feed_stories),
            n_live,
        )

    def _parse_games(
        self, schedule_data: dict[str, Any], tz: ZoneInfo
    ) -> list[GameInfo]:
        """Parse MLB API schedule response into GameInfo list."""
        games: list[GameInfo] = []
        for date_entry in schedule_data.get("dates", []):
            for g in date_entry.get("games", []):
                status = g.get("status", {})
                abstract = status.get("abstractGameState", "Preview")
                detailed = status.get("detailedState", "")
                reason = status.get("reason", "") or ""

                # Postponed / cancelled / suspended games come through with
                # abstractGameState="Final" but detailedState like
                # "Postponed", "Cancelled", "Suspended: Rain", etc. Detect
                # those before treating the game as completed (which would
                # render None scores as if the game ended 0-0).
                postponed_state, postpone_tag = _classify_postponement(detailed)

                home_team = g.get("teams", {}).get("home", {})
                away_team = g.get("teams", {}).get("away", {})
                home_abbr = _parse_team_abbr(home_team.get("team", {}))
                away_abbr = _parse_team_abbr(away_team.get("team", {}))

                home_score = home_team.get("score")
                away_score = away_team.get("score")

                inning: str | None = None
                balls = strikes = outs = 0
                on_first = on_second = on_third = False
                if abstract == "Live" and not postponed_state:
                    linescore = g.get("linescore", {})
                    inning_num = linescore.get("currentInning", 0)
                    half = linescore.get("inningHalf", "top").lower()
                    if inning_num:
                        inning = _format_inning(inning_num, half)

                    # At-bat data
                    offense = linescore.get("offense", {})
                    balls = linescore.get("balls", 0) or 0
                    strikes = linescore.get("strikes", 0) or 0
                    outs = linescore.get("outs", 0) or 0
                    on_first = "first" in offense
                    on_second = "second" in offense
                    on_third = "third" in offense

                # ABS challenges — hydrated separately for live games
                # via _fetch_abs_challenges.
                home_challenges: int | None = None
                away_challenges: int | None = None

                start_time: datetime | None = None
                game_date = g.get("gameDate")
                if game_date:
                    with contextlib.suppress(ValueError, TypeError):
                        start_time = datetime.fromisoformat(
                            game_date.replace("Z", "+00:00")
                        )

                state_map: dict[str, str] = {
                    "Final": "final",
                    "Live": "live",
                    "Preview": "preview",
                }

                resolved_state = (
                    postponed_state
                    if postponed_state is not None
                    else state_map.get(abstract, "preview")
                )

                games.append(
                    GameInfo(
                        home_abbr=home_abbr,
                        away_abbr=away_abbr,
                        home_score=home_score,
                        away_score=away_score,
                        state=resolved_state,
                        inning=inning,
                        start_time=start_time,
                        game_type=g.get("gameType", "R"),
                        game_pk=g.get("gamePk", 0),
                        balls=balls,
                        strikes=strikes,
                        outs=outs,
                        on_first=on_first,
                        on_second=on_second,
                        on_third=on_third,
                        postpone_reason=reason if postponed_state else "",
                        postpone_tag=postpone_tag if postponed_state else "PPD",
                        home_challenges=home_challenges,
                        away_challenges=away_challenges,
                    )
                )

        games.sort(
            key=lambda g: (
                g.start_time
                or datetime.min.replace(
                    tzinfo=tz,
                )
            )
        )
        return games

    def _group_into_series(self, games: list[GameInfo]) -> list[SeriesInfo]:
        """Group games into series by consecutive opponent."""
        if not games:
            return []

        series_list: list[SeriesInfo] = []
        current_opp: str | None = None
        current_games: list[GameInfo] = []

        for g in games:
            opp = g.away_abbr if g.home_abbr == self.team else g.home_abbr
            if opp != current_opp:
                if current_games:
                    assert current_opp is not None
                    series_list.append(self._make_series(current_opp, current_games))
                current_opp = opp
                current_games = [g]
            else:
                current_games.append(g)

        if current_games:
            assert current_opp is not None
            series_list.append(self._make_series(current_opp, current_games))

        return series_list

    def _make_series(self, opponent_abbr: str, games: list[GameInfo]) -> SeriesInfo:
        """Create a SeriesInfo with win/loss record."""
        wins = 0
        losses = 0
        for g in games:
            if g.state != "final":
                continue
            is_home = g.home_abbr == self.team
            team_score = g.home_score if is_home else g.away_score
            opp_score = g.away_score if is_home else g.home_score
            if team_score is not None and opp_score is not None:
                if team_score > opp_score:
                    wins += 1
                else:
                    losses += 1
        return SeriesInfo(
            opponent_abbr=opponent_abbr,
            games=games,
            team_wins=wins,
            team_losses=losses,
        )

    def _find_current_series(
        self, series_list: list[SeriesInfo], now: datetime
    ) -> SeriesInfo | None:
        """Find series that is live or most recently played."""
        for s in reversed(series_list):
            # "Final" + "postponed" both count as "this game is done for now"
            # for the purpose of locating the current series.
            has_final = any(g.state in ("final", "postponed") for g in s.games)
            has_live = any(g.state == "live" for g in s.games)
            has_upcoming = any(g.state == "preview" for g in s.games)
            if has_live:
                return s
            if has_final and has_upcoming:
                return s  # series in progress
            if has_final:
                # Check if this series ended recently (within 24h)
                last_game_time = max(
                    (g.start_time for g in s.games if g.start_time),
                    default=None,
                )
                if last_game_time:
                    hours_ago = (
                        now - last_game_time.astimezone(self._tz)
                    ).total_seconds() / 3600
                    if hours_ago < self.final_hold_hours:
                        return s
        # No current series — check for upcoming
        for s in series_list:
            if any(g.state == "preview" for g in s.games):
                return s
        return None

    def _find_next_game(self, games: list[GameInfo], now: datetime) -> GameInfo | None:
        """Find the next upcoming game."""
        for g in games:
            if (
                g.state == "preview"
                and g.start_time
                and g.start_time.astimezone(self._tz) > now
            ):
                return g
        return None

    async def _fetch_abs_challenges(
        self, game_pk: int
    ) -> tuple[int | None, int | None]:
        """Fetch ABS challenge remaining counts from the live game feed.

        Returns (home_remaining, away_remaining), or (None, None) when ABS is
        not active for this game or the request fails.
        """
        url = f"{_MLB_LIVE_API}/game/{game_pk}/feed/live"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("ABS challenge fetch failed for gamePk=%s", game_pk)
            return None, None

        abs_ch = data.get("gameData", {}).get("absChallenges", {})
        # Empty dict means ABS is not active at this park. Non-empty means ABS
        # is equipped; hasChallenges is false until the first challenge is made,
        # so we gate on the dict being non-empty rather than on hasChallenges.
        if not abs_ch or "home" not in abs_ch:
            return None, None

        home = abs_ch.get("home") or {}
        away = abs_ch.get("away") or {}
        with contextlib.suppress(TypeError, ValueError):
            return int(home.get("remaining", 0)), int(away.get("remaining", 0))
        return None, None
