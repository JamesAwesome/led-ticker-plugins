"""LiveTennisSource: the free-tier cadence floor, one-request-per-tick,
backoff on failure with the last good payload retained, key rejection.
No network: a fake aiohttp-shaped session and an injected clock."""

import asyncio
import logging

import aiohttp
import pytest

from led_ticker_tennis import _source as src
from led_ticker_tennis._source import (
    DEFAULT_BASE_URL,
    KEY_REJECTED_BACKOFF,
    MAX_BACKOFF,
    MIN_UPDATE_INTERVAL,
    LiveTennisSource,
    clamp_interval,
    resolve_api_key,
)

LIVE = {"data": [{"id": 1, "status": "live", "players": {"p1": {"name": "A B"}}}]}
UPCOMING = {"data": [{"id": 2, "status": "upcoming"}]}
EMPTY = {"data": []}


class FakeResp:
    def __init__(self, status=200, body=None, headers=None, json_exc=None):
        self.status = status
        self.body = body if body is not None else EMPTY
        self.headers = headers or {}
        self.json_exc = json_exc

    async def json(self):
        if self.json_exc:
            raise self.json_exc
        return self.body


class _Ctx:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        if isinstance(self.resp, BaseException):
            raise self.resp
        return self.resp

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        resp = self.queue.pop(0) if self.queue else FakeResp(200, EMPTY)
        return _Ctx(resp)

    @property
    def urls(self):
        return [u for u, _ in self.calls]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _source(session, interval=900, **kw):
    clock = Clock()
    s = LiveTennisSource(session, "ltapi_test", interval=interval, clock=clock, **kw)
    return s, clock


class TestClampInterval:
    def test_floor_applied_and_logged(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert clamp_interval(60) == MIN_UPDATE_INTERVAL
        assert "free-tier floor" in caplog.text

    def test_at_or_above_floor_passes_through(self):
        assert clamp_interval(900) == 900
        assert clamp_interval(3600) == 3600
        assert clamp_interval("1800") == 1800

    def test_garbage_falls_back_to_floor(self):
        assert clamp_interval("abc") == MIN_UPDATE_INTERVAL
        assert clamp_interval(None) == MIN_UPDATE_INTERVAL
        assert clamp_interval(0) == MIN_UPDATE_INTERVAL


class TestResolveApiKey:
    def test_env_wins(self, monkeypatch):
        monkeypatch.setenv("LIVETENNIS_API_KEY", "env-key")
        assert resolve_api_key(" cfg-key ") == "env-key"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("LIVETENNIS_API_KEY", " env-key ")
        assert resolve_api_key("") == "env-key"
        assert resolve_api_key(None) == "env-key"

    def test_neither(self, monkeypatch):
        monkeypatch.delenv("LIVETENNIS_API_KEY", raising=False)
        assert resolve_api_key("") == ""


class TestCadence:
    async def test_first_poll_fetches_live_with_key_header(self):
        session = FakeSession(FakeResp(200, LIVE))
        s, _ = _source(session)
        snap = await s.poll()
        assert snap.live == LIVE["data"] and not snap.stale
        assert session.urls == [f"{DEFAULT_BASE_URL}/matches?status=live&limit=200"]
        headers = session.calls[0][1]["headers"]
        assert headers["X-API-Key"] == "ltapi_test"
        assert isinstance(session.calls[0][1]["timeout"], aiohttp.ClientTimeout)
        assert snap.requests_made == 1

    async def test_no_request_before_interval_elapses(self):
        session = FakeSession(FakeResp(200, LIVE), FakeResp(200, LIVE))
        s, clock = _source(session, interval=900)
        await s.poll()
        await s.poll()  # immediate re-poll: gated
        clock.t += 899
        await s.poll()
        assert len(session.calls) == 1
        assert s.seconds_until_allowed() == pytest.approx(1)
        clock.t += 1
        await s.poll()
        assert len(session.calls) == 2

    async def test_config_below_floor_is_clamped_in_the_fetcher(self):
        session = FakeSession(FakeResp(200, LIVE), FakeResp(200, LIVE))
        s, clock = _source(session, interval=10)
        assert s.interval == MIN_UPDATE_INTERVAL
        await s.poll()
        clock.t += 600
        await s.poll()
        assert len(session.calls) == 1, "fast-poll config must not reach the API"

    async def test_live_nonempty_keeps_polling_live(self):
        session = FakeSession(*(FakeResp(200, LIVE) for _ in range(3)))
        s, clock = _source(session)
        for _ in range(3):
            await s.poll()
            clock.t += 900
        assert all("status=live" in u for u in session.urls)
        assert session.urls and len(session.urls) == 3


class TestUpcomingFallback:
    async def test_boot_with_nothing_live_waits_before_fetching_upcoming(self):
        session = FakeSession(FakeResp(200, EMPTY), FakeResp(200, UPCOMING))
        s, clock = _source(session)
        snap = await s.poll()
        assert len(session.calls) == 1
        assert snap.upcoming == []
        clock.t += 900
        snap = await s.poll()
        assert [u.split("status=")[1].split("&")[0] for u in session.urls] == [
            "live",
            "upcoming",
        ]
        assert snap.upcoming == UPCOMING["data"] and snap.live == []
        assert "limit=100" in session.urls[1]

    async def test_quiet_sign_alternates_live_and_upcoming_one_request_per_tick(self):
        session = FakeSession(*(FakeResp(200, EMPTY) for _ in range(6)))
        s, clock = _source(session)
        await s.poll()
        kinds = []
        for _ in range(4):
            clock.t += 900
            before = len(session.calls)
            await s.poll()
            assert len(session.calls) == before + 1, "one request per tick"
            kinds.append(session.urls[-1].split("status=")[1].split("&")[0])
        assert kinds == ["upcoming", "live", "upcoming", "live"]

    async def test_upcoming_payload_survives_a_later_empty_live_poll(self):
        session = FakeSession(
            FakeResp(200, EMPTY), FakeResp(200, UPCOMING), FakeResp(200, EMPTY)
        )
        s, clock = _source(session)
        await s.poll()
        clock.t += 900
        await s.poll()
        clock.t += 900
        snap = await s.poll()
        assert snap.upcoming == UPCOMING["data"]


class TestFailures:
    async def test_429_keeps_last_payload_and_backs_off(self, caplog):
        session = FakeSession(FakeResp(200, LIVE), FakeResp(429), FakeResp(200, LIVE))
        s, clock = _source(session, interval=900)
        await s.poll()
        clock.t += 900
        with caplog.at_level(logging.WARNING):
            snap = await s.poll()
        assert snap.stale and "429" in (snap.last_error or "")
        assert snap.live == LIVE["data"], "last good payload retained"
        assert "rate limited" in caplog.text
        clock.t += 900  # only one interval: still backing off (2x)
        await s.poll()
        assert len(session.calls) == 2
        clock.t += 900
        snap = await s.poll()
        assert len(session.calls) == 3 and not snap.stale

    async def test_retry_after_header_is_honoured(self):
        session = FakeSession(FakeResp(429, headers={"Retry-After": "3600"}))
        s, clock = _source(session)
        await s.poll()
        assert s.seconds_until_allowed() == pytest.approx(3600)
        session.queue.append(FakeResp(429, headers={"Retry-After": "junk"}))
        clock.t += 3600
        await s.poll()  # unparsable header -> plain doubling
        assert s.seconds_until_allowed() == pytest.approx(7200)

    async def test_consecutive_failures_double_up_to_the_cap(self):
        session = FakeSession(*(FakeResp(503) for _ in range(6)))
        s, clock = _source(session, interval=900)
        waits = []
        for _ in range(6):
            await s.poll()
            waits.append(s.seconds_until_allowed())
            clock.t += waits[-1]
        assert waits == [1800, 3600, 7200, MAX_BACKOFF, MAX_BACKOFF, MAX_BACKOFF]

    async def test_success_resets_backoff(self):
        session = FakeSession(FakeResp(500), FakeResp(200, LIVE))
        s, clock = _source(session)
        await s.poll()
        clock.t += 1800
        await s.poll()
        assert s.seconds_until_allowed() == pytest.approx(900)

    @pytest.mark.parametrize(
        ("exc", "needle"),
        [
            (TimeoutError(), "timed out"),
            (aiohttp.ClientConnectionError("boom"), "network error"),
            (RuntimeError("weird"), "unexpected error"),
        ],
    )
    async def test_exceptions_never_escape(self, exc, needle):
        session = FakeSession(exc)
        s, _ = _source(session)
        snap = await s.poll()
        assert snap.stale and needle in (snap.last_error or "")

    async def test_bad_json_and_malformed_body(self):
        session = FakeSession(
            FakeResp(200, json_exc=ValueError("not json")),
            FakeResp(200, body={"meta": {}}),
            FakeResp(200, body="nope"),
        )
        s, clock = _source(session)
        for _ in range(3):
            snap = await s.poll()
            assert snap.stale
            clock.t += s.seconds_until_allowed()
        assert "malformed" in (snap.last_error or "")

    async def test_bare_list_body_is_accepted(self):
        session = FakeSession(FakeResp(200, body=[{"id": 1}, "junk"]))
        s, _ = _source(session)
        snap = await s.poll()
        assert snap.live == [{"id": 1}]

    @pytest.mark.parametrize("status", [401, 403])
    async def test_rejected_key_parks_for_an_hour(self, status):
        session = FakeSession(FakeResp(status), FakeResp(200, LIVE))
        s, clock = _source(session)
        snap = await s.poll()
        assert snap.key_rejected and snap.stale
        assert s.seconds_until_allowed() == pytest.approx(KEY_REJECTED_BACKOFF)
        clock.t += KEY_REJECTED_BACKOFF
        snap = await s.poll()
        assert not snap.key_rejected and snap.live == LIVE["data"]

    async def test_other_4xx_is_a_plain_failure(self):
        session = FakeSession(FakeResp(404))
        s, _ = _source(session)
        snap = await s.poll()
        assert snap.stale and "HTTP 404" in (snap.last_error or "")
        assert not snap.key_rejected


def test_module_constants_match_the_free_tier():
    # Listings and result lookups share these 96 daily request slots.
    assert 86400 // src.MIN_UPDATE_INTERVAL <= 96
    assert src.DEFAULT_BASE_URL == "https://api.livetennisapi.com/api/public/v1"


class TestResults:
    async def test_displayed_match_resolves_once_and_expires(self):
        final = {"id": 1, "status": "completed", "outcome": "retired", "winner": 2}
        session = FakeSession(FakeResp(200, LIVE), FakeResp(), FakeResp(body=final))
        source, clock = _source(session)
        await source.poll()
        source.remember_displayed([1])
        clock.t += 900
        snap = await source.poll()
        assert snap.recent[0]["_stale"] is True
        assert snap.recent[0]["status"] == "live"
        assert len(session.calls) == 2
        clock.t += 900
        snap = await source.poll()
        assert session.urls[-1] == f"{DEFAULT_BASE_URL}/matches/1"
        assert snap.recent[0]["winner"] == 2
        assert snap.recent[0]["outcome"] == "retired"
        for _ in range(5):
            await source.poll()
        assert len(session.calls) == 3
        clock.t += 900
        assert (await source.poll()).recent
        clock.t += 900
        assert (await source.poll()).recent == []
        assert session.urls.count(f"{DEFAULT_BASE_URL}/matches/1") == 1

    async def test_unshown_matches_do_not_cost_result_lookups(self):
        session = FakeSession(FakeResp(200, LIVE), FakeResp(), FakeResp())
        source, clock = _source(session)
        for _ in range(3):
            await source.poll()
            clock.t += 900
        assert all("status=" in url for url in session.urls)

    async def test_results_alternate_with_live_polls(self):
        rows = [{"id": i, "status": "live"} for i in (1, 2, 3)]
        session = FakeSession(
            FakeResp(body={"data": rows}),
            FakeResp(),
            FakeResp(body={"id": 1, "status": "completed"}),
            FakeResp(),
            FakeResp(body={"id": 2, "status": "completed"}),
        )
        source, clock = _source(session)
        await source.poll()
        source.remember_displayed([1, 2])
        for _ in range(4):
            clock.t += 900
            before = len(session.calls)
            await source.poll()
            assert len(session.calls) == before + 1
        assert [url.split("/matches")[1] for url in session.urls] == [
            "?status=live&limit=200",
            "?status=live&limit=200",
            "/1",
            "?status=live&limit=200",
            "/2",
        ]

    @pytest.mark.parametrize("status", [404, 410])
    async def test_unavailable_result_is_not_fabricated_or_requested_again(
        self, status
    ):
        session = FakeSession(FakeResp(body=LIVE), FakeResp(), FakeResp(status))
        source, clock = _source(session)
        await source.poll()
        source.remember_displayed([1])
        for _ in range(2):
            clock.t += 900
            snap = await source.poll()
        assert snap.recent[0]["status"] == "live"
        assert snap.recent[0]["_stale"] is True
        clock.t += source.seconds_until_allowed()
        await source.poll()
        assert session.urls.count(f"{DEFAULT_BASE_URL}/matches/1") == 1

    async def test_resolved_matches_expire_and_can_be_looked_up_again(self):
        final = {"id": 1, "status": "completed"}
        session = FakeSession(
            FakeResp(body=LIVE),
            FakeResp(),
            FakeResp(404),
            FakeResp(body=LIVE),  # reappears within the TTL
            FakeResp(),  # and vanishes again: no second lookup yet
        )
        source, clock = _source(session)
        await source.poll()
        source.remember_displayed([1])
        for _ in range(4):
            clock.t += 900
            await source.poll()
            source.remember_displayed([1])
        assert session.urls.count(f"{DEFAULT_BASE_URL}/matches/1") == 1
        assert set(source._resolved) == {1} and not source._pending
        ttl = src.RESOLVED_TTL_INTERVALS * 900
        clock.t += ttl
        await source.poll()
        assert source._resolved == {}
        session.queue = [FakeResp(body=LIVE), FakeResp(), FakeResp(body=final)]
        for _ in range(3):
            clock.t += 900
            await source.poll()
            source.remember_displayed([1])
        assert session.urls.count(f"{DEFAULT_BASE_URL}/matches/1") == 2

    async def test_resolved_set_stays_bounded_over_a_long_run(self):
        source, clock = _source(FakeSession())
        for match_id in range(1, 500):
            row = {"id": match_id, "status": "live"}
            source.session.queue = [
                FakeResp(body={"data": [row]}),
                FakeResp(),
                FakeResp(404),
            ]
            for _ in range(3):
                await source.poll()
                source.remember_displayed([match_id])
                clock.t += 900
        assert source.session.urls.count(f"{DEFAULT_BASE_URL}/matches/499") == 1
        assert 1 <= len(source._resolved) <= src.RESOLVED_TTL_INTERVALS + 1

    @pytest.mark.parametrize("body", [{}, {"id": 2}, {"id": 1, "status": "junk"}])
    async def test_bad_detail_keeps_last_seen_match(self, body):
        session = FakeSession(FakeResp(body=LIVE), FakeResp(), FakeResp(body=body))
        source, clock = _source(session)
        await source.poll()
        source.remember_displayed([1])
        for _ in range(2):
            clock.t += 900
            snap = await source.poll()
        assert snap.stale and snap.recent[0]["id"] == 1
        assert snap.recent[0]["status"] == "live"

    async def test_nonfinal_detail_never_invents_a_winner(self):
        session = FakeSession(
            FakeResp(body=LIVE), FakeResp(), FakeResp(body=LIVE["data"][0])
        )
        source, clock = _source(session)
        await source.poll()
        source.remember_displayed([1])
        for _ in range(2):
            clock.t += 900
            snap = await source.poll()
        assert snap.recent[0]["_stale"]
        assert "winner" not in snap.recent[0]


class TestSharedSource:
    async def test_widgets_with_same_key_share_concurrent_fetch(self):
        class SlowResponse(FakeResp):
            async def json(self):
                await asyncio.sleep(0)
                return await super().json()

        session = FakeSession(SlowResponse(body=LIVE))
        first = src.shared_source(session, "same", interval=1800)
        second = src.shared_source(FakeSession(), "same", interval=900)
        assert first is second and first.interval == 900
        snapshots = await asyncio.gather(*(first.poll() for _ in range(5)))
        assert len(session.calls) == 1
        assert all(s is snapshots[0] for s in snapshots)
        assert src.shared_source(session, "different", interval=900) is not first

    def test_shared_sources_are_capped_least_recent_first(self):
        session = FakeSession()
        keep = src.shared_source(session, "key-0", interval=900)
        for i in range(1, src._MAX_SHARED_SOURCES + 3):
            src.shared_source(session, f"key-{i}", interval=900)
            assert src.shared_source(session, "key-0", interval=900) is keep
        assert len(src._SHARED_SOURCES) == src._MAX_SHARED_SOURCES
        assert "key-1" not in src._SHARED_SOURCES

    def test_closed_session_is_replaced_without_resetting_gate(self):
        session = FakeSession()
        first = src.shared_source(session, "same", interval=900)
        first._next_allowed = 12345
        session.closed = True
        replacement = FakeSession()
        assert src.shared_source(replacement, "same", interval=900) is first
        assert first.session is replacement and first._next_allowed == 12345

    async def test_full_day_stays_below_free_quota_even_when_empty(self):
        source, clock = _source(FakeSession())
        for _ in range(86400 // 900):
            await asyncio.gather(source.poll(), source.poll())
            clock.t += 900
        assert source.snapshot.requests_made == 96

    async def test_long_interval_key_rejection_waits_longer_than_one_hour(self):
        source, _ = _source(FakeSession(FakeResp(401)), interval=3600)
        await source.poll()
        assert source.seconds_until_allowed() == 7200
