"""MLBTwoRowMessage and its builder helpers."""

from typing import Any
from zoneinfo import ZoneInfo

import attrs
from led_ticker.plugin import (
    FONT_SMALL,
    Canvas,
    Color,
    ColorProvider,
    DrawResult,
    Font,
    FrameAwareBase,
    colors,
    make_color,
)

from led_ticker_baseball._models import (
    GameInfo,
    SeriesInfo,
    _format_game_time,
)
from led_ticker_baseball.teams import (
    MLB_TEAM_NAMES,
    _team_color,
    _team_palette,
)


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
                x = draw_text(canvas, seg_font, seg[0], x, baseline + y_offset, seg[1])

        top_segs = self.top_segments
        if self.matchup is not None:
            top_segs = _expand_matchup_if_fits(top_segs, self.matchup, top_font, canvas)

        _render_segments(top_segs, top_baseline, top_font)
        _render_segments(self.bottom_segments, bot_baseline, bot_font)

        return canvas, cursor_pos + canvas.width


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
    tz: ZoneInfo,  # uniform signature — unused here
    series_wins: int,  # uniform signature — unused here
    series_losses: int,  # uniform signature — unused here
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
    ball_c = make_color(80, 255, 80)  # green — balls
    strike_c = make_color(255, 255, 80)  # yellow — strikes
    out_c = make_color(255, 80, 80)  # red — outs
    occupied_c = make_color(255, 220, 50)  # yellow — occupied base
    empty_c = make_color(50, 50, 50)  # dim — empty base

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
    team_abbr: str,  # uniform signature — unused here
    tz: ZoneInfo,  # uniform signature — unused here
    series_wins: int,  # uniform signature — unused here
    series_losses: int,  # uniform signature — unused here
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
            game,
            team_abbr,
            tz,
            series_wins,
            series_losses,
            series_total_games,
            small_font=_small_font,
        )
    elif game.state == "live":
        top_segs, bot_segs = _compute_live_two_row(
            game,
            team_abbr,
            tz,
            series_wins,
            series_losses,
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
            bot.append(
                (f"Tied {series.team_wins}-{series.team_losses}", colors.RGB_WHITE)
            )
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
