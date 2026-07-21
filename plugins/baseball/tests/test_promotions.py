"""Tests for the MLB promotions widget and the shared resolve_team_id helper."""

import datetime as dt
import logging
import unittest.mock as mock
from zoneinfo import ZoneInfo


def _ctx(json_value):
    """Async context manager mock whose response .json() returns json_value."""
    resp = mock.AsyncMock()
    resp.json.return_value = json_value
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = resp
    return ctx


def make_session(routes):
    """Mock aiohttp session routing by URL substring; first match wins."""
    session = mock.MagicMock()

    def side_effect(url, *args, **kwargs):
        for key, payload in routes.items():
            if key in url:
                return _ctx(payload)
        return _ctx({})

    session.get.side_effect = side_effect
    return session


TEAMS_PAYLOAD = {
    "teams": [
        {"id": 141, "abbreviation": "TOR"},
        {"id": 147, "abbreviation": "NYY"},
    ]
}


class TestResolveTeamId:
    async def test_resolves_known_abbreviation(self):
        from led_ticker_baseball.teams import resolve_team_id

        session = make_session({"/teams": TEAMS_PAYLOAD})
        assert await resolve_team_id(session, "TOR") == 141

    async def test_unknown_abbreviation_returns_none(self):
        from led_ticker_baseball.teams import resolve_team_id

        session = make_session({"/teams": TEAMS_PAYLOAD})
        assert await resolve_team_id(session, "ZZZ") is None

    async def test_request_failure_returns_none(self):
        from led_ticker_baseball.teams import resolve_team_id

        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        assert await resolve_team_id(session, "TOR") is None

    async def test_canonical_code_resolves_api_abbreviation(self):
        # StatsAPI emits ATH/AZ; the plugin's canonical config codes are
        # OAK/ARI. A canonical code must still resolve.
        from led_ticker_baseball.teams import resolve_team_id

        session = make_session(
            {
                "/teams": {
                    "teams": [
                        {"id": 133, "abbreviation": "ATH"},
                        {"id": 109, "abbreviation": "AZ"},
                    ]
                }
            }
        )
        assert await resolve_team_id(session, "OAK") == 133
        assert await resolve_team_id(session, "ARI") == 109
        # The raw API spelling still works too.
        assert await resolve_team_id(session, "ATH") == 133


class TestCleanPromoName:
    def test_strips_presented_by(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert (
            _clean_promo_name("Loonie Dogs Night presented by Schneiders")
            == "Loonie Dogs Night"
        )

    def test_strips_pres_by(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert _clean_promo_name("Loonie Dogs Night pres. by Schneiders") == (
            "Loonie Dogs Night"
        )

    def test_case_insensitive(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert _clean_promo_name("Pride Night Presented By TD") == "Pride Night"

    def test_no_sponsor_unchanged(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert _clean_promo_name("Canada Day") == "Canada Day"


class TestDedupePromos:
    def test_exact_duplicates_collapse(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        assert _dedupe_promos(["Pride Night", "pride night"]) == ["Pride Night"]

    def test_prefix_duplicate_keeps_shorter_seen_first(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        names = [
            "Dylan Cease Bobblehead Giveaway",
            "Dylan Cease Bobblehead Giveaway Night",
        ]
        assert _dedupe_promos(names) == ["Dylan Cease Bobblehead Giveaway"]

    def test_prefix_duplicate_keeps_shorter_seen_second(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        names = [
            "Dylan Cease Bobblehead Giveaway Night",
            "Dylan Cease Bobblehead Giveaway",
        ]
        assert _dedupe_promos(names) == ["Dylan Cease Bobblehead Giveaway"]

    def test_distinct_names_kept_in_order(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        names = ["Loonie Dogs Night", "Pride Night"]
        assert _dedupe_promos(names) == names


class TestMatchAny:
    def test_case_insensitive_substring(self):
        from led_ticker_baseball.promotions import _match_any

        assert _match_any("Loonie Dogs Night", ["loonie dogs"])

    def test_no_match(self):
        from led_ticker_baseball.promotions import _match_any

        assert not _match_any("Pride Night", ["bobblehead"])

    def test_empty_keywords_never_match(self):
        from led_ticker_baseball.promotions import _match_any

        assert not _match_any("Pride Night", [])


class TestGameLocalDate:
    def test_official_date_preferred(self):
        from zoneinfo import ZoneInfo

        from led_ticker_baseball.promotions import _game_local_date

        g = {"officialDate": "2026-06-23", "gameDate": "2026-06-24T02:15:00Z"}
        tz = ZoneInfo("America/New_York")
        assert _game_local_date(g, tz) == dt.date(2026, 6, 23)

    def test_game_date_fallback_converts_timezone(self):
        from zoneinfo import ZoneInfo

        from led_ticker_baseball.promotions import _game_local_date

        # 02:15 UTC = 22:15 the previous day in New York
        g = {"gameDate": "2026-06-24T02:15:00Z"}
        tz = ZoneInfo("America/New_York")
        assert _game_local_date(g, tz) == dt.date(2026, 6, 23)

    def test_missing_dates_return_none(self):
        from zoneinfo import ZoneInfo

        from led_ticker_baseball.promotions import _game_local_date

        assert _game_local_date({}, ZoneInfo("America/New_York")) is None


def make_game(home_id, official_date, promos=()):
    """Minimal schedule-game payload. home_id 141 = TOR (the tested team)."""
    return {
        "officialDate": official_date,
        "teams": {
            "home": {"team": {"id": home_id}},
            "away": {"team": {"id": 999}},
        },
        "promotions": [{"name": n} for n in promos],
    }


def make_rich_game(
    home_id,
    official_date,
    promos=(),
    *,
    away_abbr="NYY",
    game_time="19:05:00Z",
):
    """Schedule-game payload shaped like the real hydrated response.

    ``promos`` items are raw promo dicts (name/offerType/presentedBy), as
    returned when the request hydrates ``game(promotions),team`` — mirrors
    what `_parse_promo_infos` consumes. `away_abbr` requires `team` hydration
    (only present when the real request adds `,team`, confirmed against a
    live API response during Phase 3 Task 1).
    """
    return {
        "officialDate": official_date,
        "gameDate": f"{official_date}T{game_time}",
        "teams": {
            "home": {"team": {"id": home_id}},
            "away": {"team": {"id": 999, "abbreviation": away_abbr}},
        },
        "promotions": list(promos),
    }


def make_schedule(*games):
    return {"dates": [{"games": list(games)}]}


def make_widget(**kwargs):
    from led_ticker_baseball.promotions import MLBPromotionsMonitor

    widget = MLBPromotionsMonitor(
        session=kwargs.pop("session", mock.Mock()),
        team="TOR",
        **kwargs,
    )
    widget._team_id = 141
    return widget


def line_text(story):
    """Full visible text of a segment story line."""
    return "".join(seg[0] for seg in story.segments)


class TestParseHomeGames:
    def _parse(self, data):
        from zoneinfo import ZoneInfo

        widget = make_widget()
        return widget._parse_home_games(data, ZoneInfo("America/New_York"))

    def test_home_games_only(self):
        data = make_schedule(
            make_game(141, "2026-06-23", promos=["Loonie Dogs Night"]),
            make_game(144, "2026-06-24", promos=["Bobblehead Giveaway"]),  # away
        )
        games, had_games = self._parse(data)
        assert had_games is True
        assert len(games) == 1
        assert games[0].promos == ["Loonie Dogs Night"]

    def test_promos_cleaned_and_deduped(self):
        data = make_schedule(
            make_game(
                141,
                "2026-06-10",
                promos=[
                    "Dylan Cease Bobblehead Giveaway Night",
                    "Dylan Cease Bobblehead Giveaway presented by Rogers",
                ],
            ),
        )
        games, _ = self._parse(data)
        assert games[0].promos == ["Dylan Cease Bobblehead Giveaway"]

    def test_doubleheader_promos_merged_by_date(self):
        data = make_schedule(
            make_game(141, "2026-06-23", promos=["Loonie Dogs Night"]),
            make_game(141, "2026-06-23", promos=["Pride Night"]),
        )
        games, _ = self._parse(data)
        assert len(games) == 1
        assert games[0].game_date == dt.date(2026, 6, 23)
        assert games[0].promos == ["Loonie Dogs Night", "Pride Night"]

    def test_sorted_by_date(self):
        data = make_schedule(
            make_game(141, "2026-06-30", promos=["Loonie Dogs Night"]),
            make_game(141, "2026-06-23", promos=["Pride Night"]),
        )
        games, _ = self._parse(data)
        assert [g.game_date.day for g in games] == [23, 30]

    def test_empty_schedule(self):
        games, had_games = self._parse({"dates": []})
        assert games == []
        assert had_games is False

    def test_away_only_sets_had_games(self):
        data = make_schedule(make_game(144, "2026-06-24"))
        games, had_games = self._parse(data)
        assert games == []
        assert had_games is True


class TestDedupeIndices:
    def test_survivor_indices_match_dedupe_promos(self):
        from led_ticker_baseball.promotions import _dedupe_indices

        names = [
            "Dylan Cease Bobblehead Giveaway Night",
            "Dylan Cease Bobblehead Giveaway",
        ]
        assert _dedupe_indices(names) == [1]

    def test_no_duplicates_keeps_all_indices(self):
        from led_ticker_baseball.promotions import _dedupe_indices

        assert _dedupe_indices(["Loonie Dogs Night", "Pride Night"]) == [0, 1]


class TestResolveOpponentAbbr:
    def test_canonicalizes_athletics(self):
        from led_ticker_baseball.promotions import _resolve_opponent_abbr

        assert _resolve_opponent_abbr({"abbreviation": "ATH"}) == "OAK"

    def test_canonicalizes_diamondbacks(self):
        from led_ticker_baseball.promotions import _resolve_opponent_abbr

        assert _resolve_opponent_abbr({"abbreviation": "AZ"}) == "ARI"

    def test_passthrough_for_already_canonical(self):
        from led_ticker_baseball.promotions import _resolve_opponent_abbr

        assert _resolve_opponent_abbr({"abbreviation": "NYY"}) == "NYY"

    def test_missing_abbreviation_returns_empty(self):
        from led_ticker_baseball.promotions import _resolve_opponent_abbr

        assert _resolve_opponent_abbr({}) == ""


class TestGameLocalDatetime:
    def test_parses_gamedate_in_target_timezone(self):
        from led_ticker_baseball.promotions import _game_local_datetime

        g = {"gameDate": "2026-07-18T23:05:00Z"}
        local = _game_local_datetime(g, NY)
        assert (local.hour, local.minute) == (19, 5)

    def test_missing_gamedate_returns_none(self):
        from led_ticker_baseball.promotions import _game_local_datetime

        assert _game_local_datetime({}, NY) is None

    def test_malformed_gamedate_returns_none(self):
        from led_ticker_baseball.promotions import _game_local_datetime

        assert _game_local_datetime({"gameDate": "not-a-date"}, NY) is None


def raw_promo(name, offer_type=None, presented_by=None):
    """A single raw promo dict as the real API sends it (hydrate=game(promotions))."""
    p = {"name": name}
    if offer_type is not None:
        p["offerType"] = offer_type
    if presented_by is not None:
        p["presentedBy"] = presented_by
    return p


class TestParsePromoInfos:
    def _parse(self, data, today, **kwargs):
        widget = make_widget(**kwargs)
        return widget._parse_promo_infos(data, NY, today)

    def test_home_game_promo_fields(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Loonie Dogs Night", "Theme Days")],
                away_abbr="NYY",
                game_time="23:05:00Z",
            )
        )
        infos = self._parse(data, today)
        assert len(infos) == 1
        info = infos[0]
        assert info.name == "Loonie Dogs Night"
        assert info.offer_type == "Theme Days"
        assert info.presented_by == ""
        assert info.opponent_abbr == "NYY"
        assert info.date_label == "TODAY"
        assert info.time_label == "7:05"
        assert info.am_pm == "PM"
        assert info.game_date == "2026-07-18"

    def test_presented_by_populated_when_present(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-26",
                promos=[
                    raw_promo(
                        "Kids Run the Bases", "Day of Game Highlights", "L.L.Bean"
                    )
                ],
            )
        )
        infos = self._parse(data, today)
        assert infos[0].presented_by == "L.L.Bean"

    def test_missing_offer_type_and_presented_by_default_empty(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(141, "2026-07-19", promos=[raw_promo("Work From Dome")])
        )
        infos = self._parse(data, today)
        assert infos[0].offer_type == ""
        assert infos[0].presented_by == ""

    def test_future_date_label_is_uppercase_weekday_month_day(self):
        # 2026-07-24 is a Friday.
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(141, "2026-07-24", promos=[raw_promo("Work From Dome")])
        )
        infos = self._parse(data, today)
        assert infos[0].date_label == "FRI JUL 24"

    def test_away_game_skipped(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(999, "2026-07-18", promos=[raw_promo("Bobblehead Giveaway")])
        )
        infos = self._parse(data, today)
        assert infos == []

    def test_game_without_promotions_yields_no_entries(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(make_rich_game(141, "2026-07-18", promos=[]))
        infos = self._parse(data, today)
        assert infos == []

    def test_dedupe_collapses_night_variant_within_game(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-20",
                promos=[
                    raw_promo(
                        "Kazuma Okamoto T-Shirt Giveaway Night",
                        "Day of Game Highlights",
                    ),
                    raw_promo("Kazuma Okamoto T-Shirt Giveaway", "Giveaway"),
                ],
            )
        )
        infos = self._parse(data, today)
        assert len(infos) == 1
        assert infos[0].name == "Kazuma Okamoto T-Shirt Giveaway"
        assert infos[0].offer_type == "Giveaway"

    def test_opponent_abbr_canonicalized(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Work From Dome")],
                away_abbr="ATH",
            )
        )
        infos = self._parse(data, today)
        assert infos[0].opponent_abbr == "OAK"

    def test_sorted_by_date(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(141, "2026-07-24", promos=[raw_promo("Later Promo")]),
            make_rich_game(141, "2026-07-19", promos=[raw_promo("Sooner Promo")]),
        )
        infos = self._parse(data, today)
        assert [i.game_date for i in infos] == ["2026-07-19", "2026-07-24"]

    def test_doubleheader_games_stay_separate_entries(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Game 1 Promo")],
                game_time="17:05:00Z",
            ),
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Game 2 Promo")],
                game_time="23:05:00Z",
            ),
        )
        infos = self._parse(data, today)
        assert len(infos) == 2
        assert {i.name for i in infos} == {"Game 1 Promo", "Game 2 Promo"}
        assert {i.time_label for i in infos} == {"1:05", "7:05"}

    def test_filter_applied_to_structured_list(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Loonie Dogs Night"), raw_promo("Pride Night")],
            )
        )
        infos = self._parse(data, today, filter=["pride"])
        assert len(infos) == 1
        assert infos[0].name == "Pride Night"

    def test_no_filter_returns_all(self):
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Loonie Dogs Night"), raw_promo("Pride Night")],
            )
        )
        infos = self._parse(data, today)
        assert len(infos) == 2

    def test_doubleheader_same_name_kept_separate(self):
        """Task 4 carry-forward pin (Task 1 review): a doubleheader whose
        TWO games offer the identically-named promo must NOT collapse into
        one `PromoInfo` — `_dedupe_indices` runs PER GAME (this function's
        own per-`g` loop), never across games sharing a date, unlike
        `_parse_home_games`'s date-level merge. `MLBPromotionsMonitor.update`
        relies on this: it scopes `_parse_promo_infos`'s full-window result
        down to one target date and uses THAT as the card/crawl story
        count, so a same-name doubleheader must surface as two cards, not
        a silently-deduped one."""
        today = dt.date(2026, 7, 18)
        data = make_schedule(
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Bobblehead Night")],
                game_time="17:05:00Z",
            ),
            make_rich_game(
                141,
                "2026-07-18",
                promos=[raw_promo("Bobblehead Night")],
                game_time="23:05:00Z",
            ),
        )
        infos = self._parse(data, today)
        assert len(infos) == 2
        assert all(i.name == "Bobblehead Night" for i in infos)
        assert {i.time_label for i in infos} == {"1:05", "7:05"}

    def test_date_label_respects_official_date_across_utc_boundary(self):
        """Task 4 carry-forward pin (Task 1 review): `officialDate` and a
        naive UTC-calendar-date reading of `gameDate` can disagree across
        midnight UTC. A late first pitch — 10:15pm July 18 Eastern — has
        `gameDate="2026-07-19T02:15:00Z"` (already past midnight UTC) while
        MLB's own `officialDate` still says "2026-07-18" (the LOCAL game
        day). `_game_local_date` (which this parse's `date_label`/
        `game_date` both route through) must keep preferring `officialDate`
        over a naive UTC-date slice of `gameDate` — otherwise a promo at a
        late-starting home game would mislabel as "tomorrow" (or fail the
        "TODAY" match) purely from the UTC day-rollover.

        Built directly (not via `make_rich_game`, whose `gameDate` is
        always the SAME calendar date as `officialDate` by construction) so
        the two fields can genuinely diverge.
        """
        today = dt.date(2026, 7, 18)
        g = {
            "officialDate": "2026-07-18",
            "gameDate": "2026-07-19T02:15:00Z",  # UTC calendar date: the 19th
            "teams": {
                "home": {"team": {"id": 141}},
                "away": {"team": {"id": 999, "abbreviation": "NYY"}},
            },
            "promotions": [raw_promo("Fireworks Night")],
        }
        infos = self._parse(make_schedule(g), today)
        assert len(infos) == 1
        assert infos[0].game_date == "2026-07-18"
        assert infos[0].date_label == "TODAY"
        # Sanity: the local WALL-CLOCK time is late evening on the 18th,
        # not the UTC-date's 2am — confirms the divergence is real, not an
        # accidental same-day fixture.
        assert infos[0].time_label == "10:15"
        assert infos[0].am_pm == "PM"


def gp(day, promos):
    """GamePromos in June 2026 shorthand."""
    from led_ticker_baseball.promotions import GamePromos

    return GamePromos(game_date=dt.date(2026, 6, day), promos=list(promos))


TODAY = dt.date(2026, 6, 10)


class TestPickTarget:
    def test_today_preferred_over_future(self):
        widget = make_widget()
        target = widget._pick_target(
            [gp(10, ["Loonie Dogs Night"]), gp(23, ["Pride Night"])], TODAY
        )
        assert target.game_date == TODAY

    def test_earliest_future_when_today_empty(self):
        widget = make_widget()
        target = widget._pick_target([gp(10, []), gp(23, ["Pride Night"])], TODAY)
        assert target.game_date == dt.date(2026, 6, 23)

    def test_filter_skips_non_matching_games(self):
        widget = make_widget(filter=["loonie"])
        target = widget._pick_target(
            [gp(10, ["Pride Night"]), gp(23, ["Loonie Dogs Night"])], TODAY
        )
        assert target.game_date == dt.date(2026, 6, 23)
        assert target.promos == ["Loonie Dogs Night"]

    def test_none_when_no_matches(self):
        widget = make_widget(filter=["bobblehead"])
        assert widget._pick_target([gp(10, ["Pride Night"])], TODAY) is None


class TestBuildPromoStories:
    def test_today_label(self):
        widget = make_widget()
        stories = widget._build_promo_stories(gp(10, ["Loonie Dogs Night"]), TODAY)
        assert len(stories) == 1
        texts = [t for t, _ in stories[0].segments]
        assert texts == ["TOR ", "Today · ", "Loonie Dogs Night"]

    def test_future_date_label(self):
        widget = make_widget()
        stories = widget._build_promo_stories(gp(23, ["Pride Night"]), TODAY)
        texts = [t for t, _ in stories[0].segments]
        assert texts[0] == "TOR "
        assert texts[1] == "Jun 23 · "

    def test_highlight_sorts_first_and_renders_amber(self):
        widget = make_widget(highlight=["loonie"])
        stories = widget._build_promo_stories(
            gp(10, ["Pride Night", "Loonie Dogs Night"]), TODAY
        )
        first_texts = [t for t, _ in stories[0].segments]
        assert first_texts[2] == "Loonie Dogs Night"
        name_color = stories[0].segments[2][1]
        assert (name_color.red, name_color.green, name_color.blue) == (255, 200, 60)
        # Non-highlighted promo stays white
        from led_ticker.colors import RGB_WHITE

        assert stories[1].segments[2][1] is RGB_WHITE

    def test_limit_applied_after_highlight_sort(self):
        widget = make_widget(highlight=["pride"], limit=1)
        stories = widget._build_promo_stories(
            gp(10, ["Loonie Dogs Night", "Pride Night"]), TODAY
        )
        assert len(stories) == 1
        assert stories[0].segments[2][0] == "Pride Night"

    def test_zero_limit_means_all(self):
        widget = make_widget(limit=0)
        stories = widget._build_promo_stories(
            gp(10, ["Loonie Dogs Night", "Pride Night"]), TODAY
        )
        assert len(stories) == 2

    def test_stories_centered(self):
        widget = make_widget()
        stories = widget._build_promo_stories(gp(10, ["Pride Night"]), TODAY)
        assert stories[0].center is True

    def test_plain_font_color_tints_names_not_callouts(self):
        from led_ticker.plugin import make_color

        c = make_color(0, 255, 0)
        widget = make_widget(highlight=["loonie"], font_color=c)
        stories = widget._build_promo_stories(
            gp(10, ["Loonie Dogs Night", "Pride Night"]), TODAY
        )
        amber = stories[0].segments[2][1]
        assert (amber.red, amber.green, amber.blue) == (255, 200, 60)
        assert stories[1].segments[2][1] is c
        grey = stories[1].segments[1][1]
        assert (grey.red, grey.green, grey.blue) == (150, 150, 150)

    def test_team_prefix_leads_each_line_in_brand_color(self):
        from led_ticker.colors import RGB_WHITE

        widget = make_widget()
        stories = widget._build_promo_stories(
            gp(10, ["Loonie Dogs Night", "Pride Night"]), TODAY
        )
        for story in stories:
            assert story.segments[0][0] == "TOR "
            assert story.segments[0][1] is not RGB_WHITE


NY = ZoneInfo("America/New_York")


def probe_schedule(*games):
    """Payload served to the 30-day fallback probe (gameType=R URL)."""
    return {"dates": [{"games": list(games)}]}


class TestStateSetters:
    def test_default_title_is_team_name_plus_promos(self):
        widget = make_widget()
        widget._set_title()
        texts = [t for t, _ in widget.feed_title.segments]
        assert texts == ["Blue Jays", " Promos"]

    def test_title_override(self):
        widget = make_widget(title="Dog Watch")
        widget._set_title()
        assert widget.feed_title.text == "Dog Watch"

    def test_error_state(self):
        widget = make_widget()
        widget._set_error_state()
        assert len(widget.feed_stories) == 1
        assert line_text(widget.feed_stories[0]) == "TOR No Data"

    def test_next_home_future(self):
        widget = make_widget()
        widget._set_next_home_state(dt.date(2026, 6, 22), TODAY)
        assert line_text(widget.feed_stories[0]) == "TOR Next home game: Jun 22"

    def test_next_home_today(self):
        widget = make_widget()
        widget._set_next_home_state(TODAY, TODAY)
        assert line_text(widget.feed_stories[0]) == "TOR Home game today"

    async def test_fallback_road_trip_finds_next_home(self):
        session = make_session(
            {"gameType=R": probe_schedule(make_game(141, "2026-06-26"))}
        )
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=True)
        assert line_text(widget.feed_stories[0]) == "TOR Next home game: Jun 26"

    async def test_fallback_road_trip_no_home_in_probe(self):
        session = make_session(
            {"gameType=R": probe_schedule(make_game(144, "2026-06-26"))}
        )
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=True)
        assert line_text(widget.feed_stories[0]) == "TOR No home games soon"

    async def test_fallback_offseason_opener_on_road(self):
        session = make_session(
            {"gameType=R": probe_schedule(make_game(144, "2027-03-28"))}
        )
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert line_text(widget.feed_stories[0]) == "TOR Opens Mar 28"

    async def test_fallback_offseason_no_games(self):
        session = make_session({"gameType=R": {"dates": []}})
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert line_text(widget.feed_stories[0]) == "TOR Opens soon"

    async def test_fallback_probe_failure_degrades(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert line_text(widget.feed_stories[0]) == "TOR Opens soon"

    async def test_fallback_probe_json_failure_degrades(self):
        resp = mock.AsyncMock()
        resp.json.side_effect = ValueError("not json")
        ctx = mock.AsyncMock()
        ctx.__aenter__.return_value = resp
        session = mock.MagicMock()
        session.get.return_value = ctx
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert line_text(widget.feed_stories[0]) == "TOR Opens soon"

    def test_font_color_override_selected_for_body(self):
        from led_ticker.plugin import make_color

        c = make_color(255, 0, 0)
        widget = make_widget(font_color=c)
        assert widget._body_color() is c

    def test_default_body_color_is_white(self):
        from led_ticker.colors import RGB_WHITE

        assert make_widget()._body_color() is RGB_WHITE


def _freeze_today():
    """(patcher, today) freezing promotions.datetime.now at the current time.

    Fixtures dated from `today` and update()'s own now() call could otherwise
    straddle midnight; the frozen mock wraps the real datetime so classmethods
    like fromisoformat still work.
    """
    now = dt.datetime.now(NY)
    frozen = mock.Mock(wraps=dt.datetime)
    frozen.now.return_value = now
    patcher = mock.patch("led_ticker_baseball.promotions.datetime", frozen)
    return patcher, now.date()


class TestUpdate:
    def _widget(self, schedule_payload, probe_payload=None, **kwargs):
        routes = {"hydrate=game(promotions)": schedule_payload}
        if probe_payload is not None:
            routes["gameType=R"] = probe_payload
        widget = make_widget(session=make_session(routes), **kwargs)
        widget._tz = NY
        return widget

    async def test_today_home_game_with_promos(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_game(141, today.isoformat(), promos=["Loonie Dogs Night"])
            )
        )
        with patcher:
            await widget.update()
        # feed_stories now holds MLBPromoCard (Task 4) — .legacy is the
        # per-promo SegmentMessage the scale<=1 draw path forwards to.
        texts = [t for t, _ in widget.feed_stories[0].legacy.segments]
        assert texts == ["TOR ", "Today · ", "Loonie Dogs Night"]
        assert widget.feed_title is not None

    async def test_future_home_game_when_today_empty(self):
        patcher, today = _freeze_today()
        future = today + dt.timedelta(days=5)
        widget = self._widget(
            make_schedule(make_game(141, future.isoformat(), promos=["Pride Night"]))
        )
        with patcher:
            await widget.update()
        texts = [t for t, _ in widget.feed_stories[0].legacy.segments]
        assert texts[0] == "TOR "
        assert texts[1] == f"{future.strftime('%b %-d')} · "

    async def test_no_matching_promos_shows_next_home_game(self):
        patcher, today = _freeze_today()
        future = today + dt.timedelta(days=5)
        widget = self._widget(
            make_schedule(make_game(141, future.isoformat(), promos=["Pride Night"])),
            filter=["bobblehead"],
        )
        with patcher:
            await widget.update()
        assert line_text(widget.feed_stories[0]) == (
            f"TOR Next home game: {future.strftime('%b %-d')}"
        )

    async def test_road_trip_routes_to_fallback(self):
        patcher, today = _freeze_today()
        home_date = today + dt.timedelta(days=20)
        widget = self._widget(
            make_schedule(make_game(144, today.isoformat())),  # away game only
            probe_payload=probe_schedule(make_game(141, home_date.isoformat())),
        )
        with patcher:
            await widget.update()
        assert line_text(widget.feed_stories[0]) == (
            f"TOR Next home game: {home_date.strftime('%b %-d')}"
        )

    async def test_empty_schedule_routes_to_offseason_fallback(self):
        widget = self._widget({"dates": []}, probe_payload={"dates": []})
        await widget.update()
        assert line_text(widget.feed_stories[0]) == "TOR Opens soon"

    async def test_api_error_sets_no_data(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        widget._tz = NY
        await widget.update()
        assert line_text(widget.feed_stories[0]) == "TOR No Data"

    async def test_unresolved_team_id_sets_no_data(self):
        widget = self._widget(make_schedule())
        widget._team_id = 0
        await widget.update()
        assert line_text(widget.feed_stories[0]) == "TOR No Data"

    async def test_update_logs_info(self, caplog):
        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_game(141, today.isoformat(), promos=["Loonie Dogs Night"])
            )
        )
        with (
            patcher,
            caplog.at_level(logging.INFO, logger="led_ticker_baseball.promotions"),
        ):
            await widget.update()
        matching = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "promotions" in r.message.lower()
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"


class TestPromoCardStoryBuild:
    """Task 4: `update()` builds one `MLBPromoCard` per displayed promo,
    `legacy` (the SegmentMessage) and `promo` (the `PromoInfo`) paired 1:1
    from a SINGLE ordered pass — `highlight`/`limit` apply identically to
    both views by construction (Task 1's report flagged `self._promos` as
    un-highlighted/un-limited; this is the fix)."""

    def _widget(self, schedule_payload, **kwargs):
        widget = make_widget(
            session=make_session({"hydrate=game(promotions)": schedule_payload}),
            **kwargs,
        )
        widget._tz = NY
        return widget

    async def test_feed_stories_are_promo_cards(self):
        from led_ticker_baseball._promo_card import MLBPromoCard

        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_rich_game(
                    141, today.isoformat(), promos=[raw_promo("Loonie Dogs Night")]
                )
            )
        )
        with patcher:
            await widget.update()
        assert len(widget.feed_stories) == 1
        card = widget.feed_stories[0]
        assert isinstance(card, MLBPromoCard)
        assert card.story_index == 0
        assert card.story_total == 1
        assert card.promo.name == "Loonie Dogs Night"

    async def test_promos_field_matches_feed_stories_order(self):
        """`self._promos` (Task 1) must line up 1:1, in order, with the
        `.promo` each `MLBPromoCard` in `feed_stories` carries — no
        index-guessing between the two."""
        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_rich_game(
                    141,
                    today.isoformat(),
                    promos=[
                        raw_promo("Loonie Dogs Night"),
                        raw_promo("Pride Night"),
                    ],
                )
            )
        )
        with patcher:
            await widget.update()
        assert len(widget._promos) == 2
        assert len(widget.feed_stories) == 2
        for info, card in zip(widget._promos, widget.feed_stories, strict=True):
            assert card.promo is info

    async def test_highlight_sorts_first_in_both_legacy_and_promo_view(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_rich_game(
                    141,
                    today.isoformat(),
                    promos=[
                        raw_promo("Pride Night"),
                        raw_promo("Loonie Dogs Night"),
                    ],
                )
            ),
            highlight=["loonie"],
        )
        with patcher:
            await widget.update()
        first = widget.feed_stories[0]
        legacy_texts = [t for t, _ in first.legacy.segments]
        assert legacy_texts[-1] == "Loonie Dogs Night"
        assert first.promo.name == "Loonie Dogs Night"
        assert widget._promos[0].name == "Loonie Dogs Night"

    async def test_limit_caps_both_legacy_and_promo_view(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_rich_game(
                    141,
                    today.isoformat(),
                    promos=[
                        raw_promo("Loonie Dogs Night"),
                        raw_promo("Pride Night"),
                    ],
                )
            ),
            limit=1,
        )
        with patcher:
            await widget.update()
        assert len(widget.feed_stories) == 1
        assert len(widget._promos) == 1
        assert widget.feed_stories[0].story_total == 1

    async def test_layout_and_padding_threaded_through_to_cards(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            make_schedule(
                make_rich_game(
                    141, today.isoformat(), promos=[raw_promo("Loonie Dogs Night")]
                )
            ),
            layout="ticker",
            padding=10,
        )
        with patcher:
            await widget.update()
        card = widget.feed_stories[0]
        assert card.cfg_layout == "ticker"
        assert card.padding == 10


class TestValidateConfig:
    def _validate(self, cfg):
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        return MLBPromotionsMonitor.validate_config(cfg)

    def test_clean_config_passes(self):
        assert (
            self._validate({"team": "TOR", "highlight": ["Loonie Dogs"], "limit": 3})
            == []
        )

    def test_negative_limit_rejected(self):
        msgs = self._validate({"team": "TOR", "limit": -1})
        assert len(msgs) == 1
        assert "limit" in msgs[0]

    def test_non_int_limit_rejected(self):
        msgs = self._validate({"team": "TOR", "limit": "3"})
        assert len(msgs) == 1
        assert "limit" in msgs[0]

    def test_string_filter_rejected(self):
        msgs = self._validate({"team": "TOR", "filter": "Loonie Dogs"})
        assert len(msgs) == 1
        assert "filter" in msgs[0]

    def test_string_highlight_rejected(self):
        msgs = self._validate({"team": "TOR", "highlight": "Loonie Dogs"})
        assert len(msgs) == 1
        assert "highlight" in msgs[0]

    def test_messages_returned_not_raised(self):
        msgs = self._validate({"team": "TOR", "limit": -1, "filter": "x"})
        assert len(msgs) == 2

    def test_default_layout_passes(self):
        assert self._validate({"team": "TOR"}) == []

    def test_auto_ticker_card_all_pass(self):
        for layout in ("auto", "ticker", "card"):
            assert self._validate({"team": "TOR", "layout": layout}) == []

    def test_invalid_layout_rejected(self):
        msgs = self._validate({"team": "TOR", "layout": "scoreboard"})
        assert len(msgs) == 1
        assert "layout" in msgs[0]

    def test_invalid_layout_suggests_close_match(self):
        msgs = self._validate({"team": "TOR", "layout": "crad"})
        assert len(msgs) == 1
        assert "Did you mean 'card'?" in msgs[0]


class TestStart:
    async def test_resolves_state_runs_update_and_spawns_loop(self):
        import led_ticker_baseball.promotions as mod
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        # Empty /teams leaves the team unresolved, so update() takes its
        # no-data path; we only assert the wiring around it.
        session = make_session({})
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            widget = await MLBPromotionsMonitor.start(
                session, "tor", update_interval=99
            )

        assert isinstance(widget, MLBPromotionsMonitor)
        assert widget.team == "TOR"  # upper-cased
        assert widget._tz is not None
        assert widget.feed_stories  # update() ran
        loop.assert_called_once_with(widget, 99)
        spawn.assert_called_once_with("LOOP")


class TestValidateConfigDemo:
    def _validate(self, cfg):
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        return MLBPromotionsMonitor.validate_config(cfg)

    def test_demo_true_passes_without_team(self):
        assert self._validate({"demo": True}) == []

    def test_demo_false_with_team_passes(self):
        assert self._validate({"demo": False, "team": "TOR"}) == []

    def test_validate_demo_must_be_bool(self):
        # A truthy non-bool "demo" bypasses the team-required check (same
        # as `demo = true` would) — only the bool-type message is expected.
        msgs = self._validate({"demo": "yes"})
        assert len(msgs) == 1
        assert "demo" in msgs[0]
        assert "bool" in msgs[0]

    def test_team_required_unless_demo(self):
        msgs = self._validate({})
        assert len(msgs) == 1
        assert "team" in msgs[0]
        # demo = true never needs a team.
        assert self._validate({"demo": True}) == []

    def test_team_blank_string_still_required(self):
        msgs = self._validate({"team": "   "})
        assert len(msgs) == 1
        assert "team" in msgs[0]


# --- demo = true (fixture data, no live fetch) ---


class TestPromotionsDemo:
    """`demo = true` builds feed_stories from curated fixture promos —
    never fetching the MLB API or spawning the background poll loop."""

    async def test_demo_populates_feed_without_fetch(self):
        import led_ticker_baseball.promotions as mod
        from led_ticker_baseball._promo_card import MLBPromoCard
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        # A session whose .get() would raise if ever called — start() must
        # never touch it in demo mode.
        session = mock.Mock()
        session.get.side_effect = AssertionError(
            "demo mode must never call session.get()"
        )
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            widget = await MLBPromotionsMonitor.start(session, demo=True)

        assert isinstance(widget, MLBPromotionsMonitor)
        assert widget.feed_stories
        assert widget.feed_title is not None
        # The real card type update() would build — demo reuses the SAME
        # story builder, not a re-implemented rendering path.
        assert all(isinstance(s, MLBPromoCard) for s in widget.feed_stories)
        names = {s.promo.name for s in widget.feed_stories}
        assert "Bobblehead Night" in names
        # Different opponents so the chip color varies across the rotation.
        opponents = {s.promo.opponent_abbr for s in widget.feed_stories}
        assert len(opponents) >= 2
        # Never fetched, never spawned the background poll loop.
        session.get.assert_not_called()
        loop.assert_not_called()
        spawn.assert_not_called()

    async def test_demo_works_without_team_or_session(self):
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        widget = await MLBPromotionsMonitor.start(session=None, demo=True)

        assert widget.feed_stories
        assert widget.team  # set from the fixture, not left blank

    def test_demo_construct_directly_without_team(self):
        from led_ticker_baseball._promo_card import MLBPromoCard
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        widget = MLBPromotionsMonitor(session=None, demo=True)
        widget._load_demo()

        assert widget.feed_stories
        assert any(isinstance(s, MLBPromoCard) for s in widget.feed_stories)

    def test_demo_with_configured_team_logs_override(self, caplog):
        from led_ticker_baseball.promotions import DEMO_TEAM, MLBPromotionsMonitor

        widget = MLBPromotionsMonitor(session=None, team="SEA", demo=True)
        with caplog.at_level(logging.DEBUG, logger="led_ticker_baseball.promotions"):
            widget._load_demo()

        assert widget.team == DEMO_TEAM
        assert widget.team != "SEA"
        assert any(
            "ignoring configured team" in r.message.lower() for r in caplog.records
        )

    def test_demo_without_configured_team_does_not_log_override(self, caplog):
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        widget = MLBPromotionsMonitor(session=None, demo=True)
        with caplog.at_level(logging.DEBUG, logger="led_ticker_baseball.promotions"):
            widget._load_demo()

        assert not any(
            "ignoring configured team" in r.message.lower() for r in caplog.records
        )
