"""MLB home-game promotions widget using the free MLB Stats API.

Data comes from the schedule endpoint's ``promotions`` hydration — giveaways
and theme nights attached to each home game (e.g. the Blue Jays' "Loonie Dogs
Night"). The API has no live counter data; this widget shows what's on, not
how many hot dogs were eaten.
"""

import contextlib
import difflib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Self, TypeVar
from zoneinfo import ZoneInfo

import aiohttp
import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    Color,
    ColorProvider,
    Font,
    SegmentMessage,
    TickerMessage,
    colors,
    make_color,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_baseball._promo_card import MLBPromoCard
from led_ticker_baseball.teams import (
    API_TO_CANONICAL_ABBR,
    MLB_API,
    MLB_TEAM_NAMES,
    _team_color,
    resolve_team_id,
)

logger: logging.Logger = logging.getLogger(__name__)

_INTERVAL_SIX_HOURS: int = 21600

# Supported values for MLBPromotionsMonitor.layout — mirrors the
# scores.py/standings.py precedent (each widget keeps its own local
# validate_config tuple rather than importing a shared one; see those
# modules' own comments for why). "auto" resolves per-sign at draw time via
# `layouts.resolve_promo_layout` (bigsign -> held card, longboi -> hires
# crawl); "ticker"/"card" pin one shape explicitly at scale > 1. scale <= 1
# always forwards to the legacy SegmentMessage regardless of this value.
_PROMO_VALID_LAYOUTS: tuple[str, ...] = ("auto", "ticker", "card")

_PromoT = TypeVar("_PromoT")

# "Loonie Dogs Night presented by Schneiders" → "Loonie Dogs Night"
_SPONSOR_RE: re.Pattern[str] = re.compile(
    r"\s+(?:presented by|pres\. by)\s+.*$", re.IGNORECASE
)


def _clean_promo_name(name: str) -> str:
    """Strip sponsor tails: 'X presented by Y' / 'X pres. by Y' → 'X'."""
    return _SPONSOR_RE.sub("", name).strip()


def _dedupe_indices(names: list[str]) -> list[int]:
    """Indices of ``names`` surviving the prefix/exact-duplicate rule below.

    Shared primitive behind both ``_dedupe_promos`` (works on cleaned name
    strings, for the SegmentMessage story path) and ``_parse_promo_infos``
    (works on raw promo dicts, for the structured ``PromoInfo`` path) — one
    definition means the two views can't disagree on what counts as a
    duplicate. Exact duplicates (casefolded) are dropped; when one name is a
    prefix of another (the feed lists both "Dylan Cease Bobblehead Giveaway
    Night" and "Dylan Cease Bobblehead Giveaway"), the shorter name wins.
    Pairwise only: three-way prefix chains within one game's promo list
    aren't fully collapsed — the feed has never produced one.
    """
    kept: list[tuple[int, str]] = []
    for i, name in enumerate(names):
        cf = name.casefold()
        dominated = False
        for k, (_, other) in enumerate(kept):
            ocf = other.casefold()
            if cf.startswith(ocf):
                dominated = True  # a shorter-or-equal name is already kept
                break
            if ocf.startswith(cf):
                kept[k] = (i, name)  # new name is shorter; it wins
                dominated = True
                break
        if not dominated:
            kept.append((i, name))
    return [i for i, _ in kept]


def _dedupe_promos(names: list[str]) -> list[str]:
    """Collapse duplicate promo names, keeping feed order. See ``_dedupe_indices``."""
    idx = _dedupe_indices(names)
    return [names[i] for i in idx]


def _match_any(name: str, keywords: list[str]) -> bool:
    """Case-insensitive substring match against any keyword."""
    n = name.casefold()
    return any(k.casefold() in n for k in keywords)


def _game_local_date(g: dict[str, Any], tz: ZoneInfo) -> date | None:
    """Local calendar date of a schedule game: officialDate, else gameDate."""
    official = g.get("officialDate")
    if official:
        with contextlib.suppress(ValueError, TypeError):
            return date.fromisoformat(official)
    game_date = g.get("gameDate")
    if game_date:
        with contextlib.suppress(ValueError, TypeError):
            return datetime.fromisoformat(game_date).astimezone(tz).date()
    return None


def _game_local_datetime(g: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    """Local start time of a schedule game, from ``gameDate`` (UTC ISO8601).

    Unlike ``_game_local_date`` this has no ``officialDate`` fallback —
    ``officialDate`` is a date-only field with no clock time to offer.
    """
    game_date = g.get("gameDate")
    if not game_date:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(game_date).astimezone(tz)
    return None


def _resolve_opponent_abbr(team_data: dict[str, Any]) -> str:
    """Away-team abbreviation from schedule ``team`` data, canonicalized.

    The schedule endpoint only returns ``abbreviation`` when the request
    hydrates ``team`` (``update()`` requests ``hydrate=game(promotions),team``
    for exactly this). StatsAPI's own spelling ("ATH"/"AZ") is normalized to
    the plugin's canonical code ("OAK"/"ARI") via the same table
    ``resolve_team_id`` uses in the other direction.
    """
    abbr: str = team_data.get("abbreviation") or ""
    return API_TO_CANONICAL_ABBR.get(abbr, abbr)


@dataclass
class GamePromos:
    game_date: date  # local calendar date of the home game
    promos: list[str] = field(default_factory=list)


@dataclass
class PromoInfo:
    """Structured per-promo fields for the upcoming card/crawl layouts.

    Built alongside (not instead of) the ``SegmentMessage`` crawl stories —
    see ``MLBPromotionsMonitor._parse_promo_infos``. ``time_label`` is the
    bare "H:MM" clock reading with no meridiem; ``am_pm`` ("AM"/"PM") is kept
    separate so a renderer can be honest about a rare AM start instead of
    hardcoding " PM" (design README "Promotions": bigsign start time is
    amber "7:05" + " PM" appended at draw). ``date_label`` is "TODAY" or an
    uppercase "FRI JUL 18"; ``game_date`` is the ISO date, for sorting/dedup
    once a later task holds several of these at once.
    """

    name: str
    offer_type: str = ""
    presented_by: str = ""
    opponent_abbr: str = ""
    date_label: str = ""
    time_label: str = ""
    am_pm: str = ""
    game_date: str = ""


@attrs.define
class MLBPromotionsMonitor:
    """Upcoming home-game promotions (giveaways / theme nights) for one team."""

    session: aiohttp.ClientSession
    team: str
    title: str = ""
    timezone: str = "America/New_York"
    lookahead_days: int = 14
    highlight: list[str] = attrs.field(factory=list)
    filter: list[str] = attrs.field(factory=list)
    limit: int = 0
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    layout: str = attrs.field(default="auto", kw_only=True)
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    feed_title: TickerMessage | SegmentMessage | None = attrs.field(
        init=False, default=None
    )
    feed_stories: list[TickerMessage | SegmentMessage | MLBPromoCard] = attrs.field(
        init=False, factory=list
    )
    _promos: list[PromoInfo] = attrs.field(init=False, factory=list)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any
        returned messages into a pre-flight ValueError. Same contract as
        ``MLBScoreMonitor.validate_config``.
        """
        msgs: list[str] = []

        limit = cfg.get("limit", 0)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            msgs.append(f"promotions limit={limit!r} must be a non-negative integer.")

        layout = cfg.get("layout", "auto")
        if layout not in _PROMO_VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), _PROMO_VALID_LAYOUTS, n=1, cutoff=0.5
            )
            suggestion = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in _PROMO_VALID_LAYOUTS)
            msgs.append(
                f"promotions layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{suggestion}"
            )

        for key in ("filter", "highlight"):
            if key not in cfg:
                continue
            val = cfg[key]
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                msgs.append(
                    f"promotions {key}={val!r} must be a list of strings, "
                    f'e.g. {key} = ["Loonie Dogs"].'
                )

        return msgs

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        team: str,
        update_interval: int = _INTERVAL_SIX_HOURS,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBPromotionsMonitor.start: team=%s", team)
        widget = cls(session=session, team=team.upper(), **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        widget._team_id = await resolve_team_id(session, widget.team) or 0
        await widget.update()
        logger.info(
            "MLB Promotions %s: %d stories",
            widget.team,
            len(widget.feed_stories),
        )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        """Fetch the promotions-hydrated schedule and build display messages."""
        tz = self._tz or ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        self._set_title()
        # Reset on every call so a failed/short-circuited fetch below can't
        # leave a previous update's structured promos stale on the widget.
        self._promos = []

        if not self._team_id:
            self._set_error_state()
            return

        start = today.strftime("%Y-%m-%d")
        end = (today + timedelta(days=self.lookahead_days)).strftime("%Y-%m-%d")
        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            # ``,team`` hydrates teams.away.team.abbreviation, needed for
            # PromoInfo.opponent_abbr; kept AFTER "game(promotions)" so the
            # substring "hydrate=game(promotions)" stays intact for anything
            # (tests included) matching on it.
            f"&hydrate=game(promotions),team"
        )
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
            games, had_games = self._parse_home_games(data, tz)
            all_infos = self._parse_promo_infos(data, tz, today)
            self._promos = all_infos
        except Exception:
            logger.exception("MLB Promotions API error for %s", self.team)
            self._set_error_state()
            return

        if not games:
            await self._set_fallback_state(tz, had_games)
            return

        target = self._pick_target(games, today)
        if target is None:
            # games is sorted and the query starts at today, so [0] is the
            # earliest upcoming home game.
            self._set_next_home_state(games[0].game_date, today)
            return

        # Scope the richer structured parse (all_infos, whole lookahead
        # window) down to the SAME date `_pick_target` picked — see
        # `_build_promo_card_stories`'s docstring for why this scoping
        # (rather than a separate re-parse) is what keeps the legacy
        # SegmentMessage story order and the PromoInfo/card order aligned.
        target_infos = [
            p for p in all_infos if p.game_date == target.game_date.isoformat()
        ]
        if not target_infos:
            # Defensive only: _pick_target found this date via the
            # date-merged/deduped name view (_parse_home_games); the
            # per-game view (_parse_promo_infos) filters with the same
            # keyword match, so it should never come up empty here. Degrade
            # the same way an unmatched date would rather than build a
            # zero-story rotation.
            self._set_next_home_state(target.game_date, today)
            return

        label = self._promo_line_date_label(target.game_date, today)
        legacy_msgs, ordered_infos = self._build_promo_card_stories(target_infos, label)
        self._promos = ordered_infos
        story_total = len(ordered_infos)
        self.feed_stories = [
            MLBPromoCard(
                promo=info,
                story_index=i,
                story_total=story_total,
                legacy=legacy_msgs[i],
                cfg_layout=self.layout,
                padding=self.padding,
                bg_color=self.bg_color,
                font_color=self.font_color,
            )
            for i, info in enumerate(ordered_infos)
        ]
        logger.info(
            "MLB Promotions %s updated: %d stories",
            self.team,
            len(self.feed_stories),
        )

    def _parse_home_games(
        self, data: dict[str, Any], tz: ZoneInfo
    ) -> tuple[list[GamePromos], bool]:
        """Per-date home-game promo lists from a schedule response.

        Returns (games sorted by date, whether the response had ANY games) —
        the flag distinguishes a road trip from the offseason in the
        fallback path. Doubleheader promos merge into one date entry.
        """
        by_date: dict[date, list[str]] = {}
        had_games = False
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                had_games = True
                home = g.get("teams", {}).get("home", {}).get("team", {})
                if home.get("id") != self._team_id:
                    continue
                d = _game_local_date(g, tz)
                if d is None:
                    continue
                names = [
                    _clean_promo_name(p["name"])
                    for p in g.get("promotions", [])
                    if p and p.get("name")
                ]
                by_date.setdefault(d, []).extend(names)
        games = [
            GamePromos(game_date=d, promos=_dedupe_promos(names))
            for d, names in sorted(by_date.items())
        ]
        return games, had_games

    def _parse_promo_infos(
        self, data: dict[str, Any], tz: ZoneInfo, today: date
    ) -> list[PromoInfo]:
        """Structured per-promo entries for every upcoming home game.

        Feeds the card/crawl layouts (later tasks) — a richer companion to
        ``_parse_home_games``'s ``list[str]`` names, NOT a replacement; the
        SegmentMessage story path is untouched. Only home games carry
        promotions for this team, matching ``_parse_home_games`` (an away
        game is skipped even if it has its own promotions). Unlike
        ``_parse_home_games``, a doubleheader's two home games stay separate
        entries here (each keeps its own start time) rather than merging by
        date. Cleaned + deduped per game via ``_dedupe_indices`` — the same
        rule ``_dedupe_promos`` uses — so the two views can't disagree on
        what counts as a promo. Sorted by date, then ``self.filter`` applied
        last (same semantics as ``_apply_filter``) so the structured list
        matches what the crawl would show.
        """
        infos: list[PromoInfo] = []
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                home = g.get("teams", {}).get("home", {}).get("team", {})
                if home.get("id") != self._team_id:
                    continue
                d = _game_local_date(g, tz)
                if d is None:
                    continue
                raw = [p for p in g.get("promotions", []) if p and p.get("name")]
                if not raw:
                    continue
                names = [_clean_promo_name(p["name"]) for p in raw]
                survivors = _dedupe_indices(names)

                opponent_abbr = _resolve_opponent_abbr(
                    g.get("teams", {}).get("away", {}).get("team", {})
                )
                date_label = "TODAY" if d == today else d.strftime("%a %b %-d").upper()
                local_dt = _game_local_datetime(g, tz)
                time_label = local_dt.strftime("%-I:%M") if local_dt else ""
                am_pm = local_dt.strftime("%p") if local_dt else ""

                for i in survivors:
                    infos.append(
                        PromoInfo(
                            name=names[i],
                            offer_type=raw[i].get("offerType") or "",
                            presented_by=raw[i].get("presentedBy") or "",
                            opponent_abbr=opponent_abbr,
                            date_label=date_label,
                            time_label=time_label,
                            am_pm=am_pm,
                            game_date=d.isoformat(),
                        )
                    )
        infos.sort(key=lambda p: p.game_date)
        if self.filter:
            infos = [p for p in infos if _match_any(p.name, self.filter)]
        return infos

    def _apply_filter(self, promos: list[str]) -> list[str]:
        """Keep only promos matching the filter keywords (all when unset)."""
        if not self.filter:
            return list(promos)
        return [p for p in promos if _match_any(p, self.filter)]

    def _pick_target(self, games: list[GamePromos], today: date) -> GamePromos | None:
        """First game on/after today with post-filter promos (today wins)."""
        for game in games:
            if game.game_date < today:
                continue
            matches = self._apply_filter(game.promos)
            if matches:
                return GamePromos(game_date=game.game_date, promos=matches)
        return None

    def _order_and_limit(
        self, items: list[_PromoT], key: Callable[[_PromoT], str]
    ) -> tuple[list[_PromoT], list[_PromoT]]:
        """Stable partition (highlight-matches first) then `self.limit`
        truncation — the ONE implementation shared by the legacy
        SegmentMessage builder (`_build_promo_stories`, `list[str]`) and the
        card/crawl `PromoInfo` builder (`_build_promo_card_stories`), so
        `highlight`/`limit` can never apply differently to the two story
        shapes (Task 1's report flagged `self._promos` as un-highlighted
        and un-limited — this closes that gap by construction rather than
        by re-deriving the ordering twice).

        `key` extracts the text to match against `self.highlight`;
        membership below uses full VALUE equality on the item itself (not
        identity or a set of `id()`s) — correct even when two items share
        the same `key()` result but differ elsewhere (e.g. a doubleheader's
        two games offering the identically-named promo: both `PromoInfo`s
        match `_match_any` the same way and both partition into
        `highlighted` together; neither collapses into the other since
        they're never treated as interchangeable, just co-classified).
        Returns `(ordered, highlighted)` — callers use membership in
        `highlighted` to color the matching lines/cards.
        """
        highlighted = [it for it in items if _match_any(key(it), self.highlight)]
        rest = [it for it in items if it not in highlighted]
        ordered = highlighted + rest
        if self.limit > 0:
            ordered = ordered[: self.limit]
        return ordered, highlighted

    def _promo_line_date_label(self, game_date: date, today: date) -> str:
        """'Today' or e.g. 'Jun 23' — the legacy SegmentMessage's date
        lead-in. Deliberately a DIFFERENT format from `PromoInfo.date_label`
        ("TODAY" / "FRI JUL 24", uppercase — feeds the card/crawl
        renderers, which upper-case at render time per the handoff's
        all-caps fixtures); this is the pre-Phase-3 ticker-text format,
        unchanged.
        """
        return "Today" if game_date == today else game_date.strftime("%b %-d")

    def _build_promo_stories(
        self, target: GamePromos, today: date
    ) -> list[TickerMessage | SegmentMessage]:
        """One centered story per promo: 'TOR <Today|Jun 22> · <name>'.

        Every line leads with the team abbreviation in its brand color —
        stories scroll independently, so each must identify its team without
        relying on the section title. Highlighted promos render amber and
        sort first; ``limit`` truncates AFTER that sort so highlights are
        never the lines dropped.
        """
        label = self._promo_line_date_label(target.game_date, today)
        team_c = _team_color(self.team)
        date_c = make_color(150, 150, 150)  # grey — date label
        highlight_c = make_color(255, 200, 60)  # amber — highlighted promo
        body_c = self._plain_body_color()

        ordered, highlighted = self._order_and_limit(target.promos, key=lambda n: n)

        return [
            SegmentMessage(
                [
                    (f"{self.team} ", team_c),
                    (f"{label} · ", date_c),
                    (
                        name,
                        highlight_c if name in highlighted else body_c,
                    ),
                ],
                center=True,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for name in ordered
        ]

    def _build_promo_card_stories(
        self, infos: list[PromoInfo], label: str
    ) -> tuple[list[SegmentMessage], list[PromoInfo]]:
        """One legacy SegmentMessage + one `PromoInfo`, per displayed promo,
        built from a SINGLE ordered pass over `infos` — the pairing
        `MLBPromoCard` needs (`legacy` at scale<=1, `promo` at scale>1) can
        never drift apart because both come from the same `ordered` list at
        the same index, rather than being computed separately and zipped
        by position after the fact.

        `infos` must already be scoped to the picked target date (see
        `update()` — this method only orders/limits within that date, it
        does not re-scope across dates). `label` is the legacy line's date
        lead-in (`_promo_line_date_label`'s output for that date) — passed
        in rather than recomputed here since every entry in `infos` shares
        the same target date already.
        """
        team_c = _team_color(self.team)
        date_c = make_color(150, 150, 150)  # grey — date label
        highlight_c = make_color(255, 200, 60)  # amber — highlighted promo
        body_c = self._plain_body_color()

        ordered, highlighted = self._order_and_limit(infos, key=lambda p: p.name)

        legacy = [
            SegmentMessage(
                [
                    (f"{self.team} ", team_c),
                    (f"{label} · ", date_c),
                    (info.name, highlight_c if info in highlighted else body_c),
                ],
                center=True,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for info in ordered
        ]
        return legacy, ordered

    def _set_title(self) -> None:
        """Team-colored '<Team> Promos' title, or the configured override."""
        if self.title:
            t_c = self.font_color if self.font_color is not None else colors.RGB_WHITE
            self.feed_title = TickerMessage(
                self.title, font_color=t_c, center=True, bg_color=self.bg_color
            )
            return
        team_name = MLB_TEAM_NAMES.get(self.team, self.team)
        self.feed_title = SegmentMessage(
            [(team_name, _team_color(self.team)), (" Promos", colors.RGB_WHITE)],
            center=True,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )

    def _body_color(self) -> Color | ColorProvider:
        return self.font_color if self.font_color is not None else colors.RGB_WHITE

    def _plain_body_color(self) -> Color | ColorProvider:
        """Body-text color for per-segment use.

        A plain-Color ``font_color`` tints body text while callout segments
        (team prefix, date label, amber highlight) keep their colors.
        Providers (``color_for``) can't color a single segment; they pass
        through ``font_color=`` on the message instead, which overrides every
        segment in core — same as the sibling widgets.
        """
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            return self.font_color
        return colors.RGB_WHITE

    def _story_line(self, text: str) -> SegmentMessage:
        """Single status line led by the team abbreviation in its brand color."""
        return SegmentMessage(
            [
                (f"{self.team} ", _team_color(self.team)),
                (text, self._plain_body_color()),
            ],
            center=True,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )

    # Contract for the _set_*_state setters below: they manage feed_stories
    # only. update() calls _set_title() unconditionally before dispatching to
    # any of them, so feed_title is always set — including on error paths.

    def _set_error_state(self) -> None:
        """Set display to error state."""
        self.feed_stories = [self._story_line("No Data")]
        logger.info(
            "MLB Promotions %s updated: %d stories (no data)",
            self.team,
            len(self.feed_stories),
        )

    def _set_next_home_state(self, game_date: date, today: date) -> None:
        """Home games exist in the window but none had matching promos."""
        if game_date == today:
            text = "Home game today"
        else:
            text = f"Next home game: {game_date.strftime('%b %-d')}"
        self.feed_stories = [self._story_line(text)]
        logger.info("MLB Promotions %s updated: %s", self.team, text)

    async def _set_fallback_state(self, tz: ZoneInfo, had_games: bool) -> None:
        """No home games in the window: probe 30 days of regular season.

        First home game → "Next home game: <date>". Otherwise ``had_games``
        (the main window had away games → mid-season road trip) decides
        between "No home games soon" and the offseason "Opens …" texts.
        A failed probe degrades to the no-result text silently.
        """
        now = datetime.now(tz)
        start = now.strftime("%Y-%m-%d")
        end = (now + timedelta(days=30)).strftime("%Y-%m-%d")
        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1&gameType=R"
        )
        data: dict[str, Any] = {}
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Promotions probe failed for %s", self.team)

        first_any: date | None = None
        first_home: date | None = None
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                d = _game_local_date(g, tz)
                if d is None:
                    continue
                if first_any is None or d < first_any:
                    first_any = d
                home = g.get("teams", {}).get("home", {}).get("team", {})
                if home.get("id") == self._team_id and (
                    first_home is None or d < first_home
                ):
                    first_home = d

        if first_home is not None:
            text = f"Next home game: {first_home.strftime('%b %-d')}"
        elif had_games:
            text = "No home games soon"
        elif first_any is not None:
            text = f"Opens {first_any.strftime('%b %-d')}"
        else:
            text = "Opens soon"

        self.feed_stories = [self._story_line(text)]
        logger.info("MLB Promotions %s updated: fallback (%s)", self.team, text)
