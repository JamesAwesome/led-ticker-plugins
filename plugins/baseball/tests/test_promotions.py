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
        texts = [t for t, _ in widget.feed_stories[0].segments]
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
        texts = [t for t, _ in widget.feed_stories[0].segments]
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
