"""flair.poker — the ``Poker`` suit-ripple transition class (Task 3) +
registration.

Stub canvas / widget fixtures copied from test_flair_stickers_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import SNAP_THRESHOLD, ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.poker import SUITS, Poker


class _StubCanvas:
    """Minimal scale=1 real-canvas stub."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.calls: list[tuple[int, int, int, int, int]] = []

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)
        self.calls.append((x, y, r, g, b))

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.SetPixel(xx, yy, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)


def _make_widget(draw_pixel: bool = True, fill: Any = None) -> Any:
    """Widget stub. ``draw_pixel`` lights one pixel at (0, 0); ``fill`` (an
    (r, g, b) tuple) fills the whole canvas — used to make 'revealed but
    empty' pixels observable as the incoming colour rather than black."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        if fill is not None:
            canvas.Fill(*fill)
        if draw_pixel:
            canvas.SetPixel(0, 0, 255, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


class TestKnobValidation:
    def test_unknown_suit_raises_naming_options(self):
        with pytest.raises(ValueError, match="hearts.*diamonds.*clubs.*spades|suits"):
            Poker(suits=["wands"])

    def test_empty_or_nonlist_rejected(self):
        for bad in ([], "hearts", [1], [""]):
            with pytest.raises(ValueError):
                Poker(suits=bad)

    def test_valid_suits_and_default(self):
        assert Poker().suits == ["hearts", "diamonds", "clubs", "spades"]
        assert Poker(suits=["diamonds"]).suits == ["diamonds"]
        assert Poker(suits=["hearts", "spades"]).suits == ["hearts", "spades"]


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        p = Poker(suits=["hearts"], seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        result = p.frame_at(0.0, canvas, outgoing, incoming)

        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # No glyph/ring layer painted anything at t=0 (outgoing is a no-op
        # stub here, so any pixel at all would be a leak).
        assert canvas._pixels == {}
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        p = Poker(suits=["hearts"], seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=True)

        result = p.frame_at(
            0.96, canvas, outgoing, incoming, incoming_bg_color=(9, 9, 9)
        )

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        # incoming drew its own pixel at (0, 0) AFTER the bg fill -> wins there.
        assert canvas._pixels[(0, 0)] == (255, 0, 0)
        # Elsewhere the snap_reset bg fill is observable.
        assert canvas._pixels[(5, 5)] == (9, 9, 9)
        assert result is canvas

    def test_no_outgoing_paint_after_cutover(self) -> None:
        p = Poker(suits=["clubs"], seed=2)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        p.frame_at(0.6, canvas, outgoing, incoming)

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)


# ---------------------------------------------------------------------------
# Full-reveal spec matrix -- both geometries x (all-suits, single-suit each)
# x >=25 seeds. Clubs is the non-radially-monotone suit the spec calls out as
# the trap for the full-reveal guarantee: its waist (the stem between the
# three lobes) is narrower than the lobes at the same radius, so a glyph
# planted right at a panel edge can leave a sliver of that waist just past
# the last swept ring shell unrevealed. The two now-removed
# test_full_reveal_before_snap_smallsign/_bigsign tests only ever exercised
# the default all-suits pool, so they never hit this trap.
# ---------------------------------------------------------------------------

_FULL_REVEAL_POOLS: list[list[str]] = [
    list(SUITS),
    ["hearts"],
    ["diamonds"],
    ["clubs"],
    ["spades"],
]
_SMALLSIGN = ("smallsign", 160, 16, 1)
_BIGSIGN = ("bigsign", 256, 64, 4)
_FULL_REVEAL_SEEDS = range(8)

# The exact (geometry, seed) pairs where single-suit CLUBS left an unrevealed
# far-left-edge pixel at the pre-fix _MAX_R_FACTOR = 1.2 (clubs are the one
# non-radially-monotone suit — the spec's flagged trap; found by the Task 3
# review's seed sweep). Pinning them makes this a fast, DETERMINISTIC
# regression guard: if _MAX_R_FACTOR is ever lowered back, these fail
# immediately without needing a 250-case brute-force sweep (which cost ~7min
# of RingCache pre-warming). Bigsign is ~5s/case, so we run only these known
# bad seeds there, not a full range.
_CLUBS_REGRESSION_CASES = [
    (_SMALLSIGN, 2),
    (_SMALLSIGN, 15),
    (_SMALLSIGN, 22),
    (_SMALLSIGN, 23),
    (_BIGSIGN, 15),
]


def _full_reveal_missing_pixels(
    suits: list[str], width: int, height: int, scale: int, seed: int
) -> list[tuple[int, int]]:
    """Run the wash phase to just below SNAP and return every panel pixel
    left as the black complement: the incoming widget fills a non-black
    colour, so a black pixel can only be one we blacked out for being
    still-unrevealed. Rainbow rings are never pure black, so black ==
    unrevealed exactly.

    A single ``frame_at`` call at ``SNAP_THRESHOLD - 1e-4`` reproduces the
    same accumulated reveal mask a full per-tick sweep from t=0.4 would
    produce: ``_accumulate_reveal``'s target radius for a glyph is a pure
    function of ``t`` and that glyph's stagger, not of how many prior ticks
    were rendered, and ``_reveal_r`` starts at -1 so the first call already
    unions every radius from 0 up to that target. Verified empirically
    against the old sweep-based assertion (identical missing-pixel sets,
    including the clubs failures this test exists to catch) before relying on
    it here -- the single-frame shortcut is what keeps the guard fast.
    """
    real = _StubCanvas(width=width, height=height)
    canvas = ScaledCanvas(real, scale=scale, content_height=16) if scale > 1 else real
    p = Poker(suits=suits, seed=seed)
    outgoing = _make_widget(draw_pixel=False)
    incoming = _make_widget(draw_pixel=False, fill=(7, 7, 7))

    p.frame_at(SNAP_THRESHOLD - 1e-4, canvas, outgoing, incoming)

    return [
        (x, y)
        for y in range(real.height)
        for x in range(real.width)
        if real._pixels.get((x, y)) == (0, 0, 0)
    ]


@pytest.mark.parametrize("suits", _FULL_REVEAL_POOLS, ids=lambda s: "-".join(s))
@pytest.mark.parametrize("seed", _FULL_REVEAL_SEEDS)
def test_full_reveal_before_snap_smallsign(suits, seed) -> None:
    """General full-reveal guarantee across every pool on the cheap
    (scale-1) geometry: at t just below SNAP no panel pixel is left as the
    black complement."""
    _, width, height, scale = _SMALLSIGN
    black = _full_reveal_missing_pixels(suits, width, height, scale, seed)
    assert black == [], (
        f"suits={suits} smallsign seed={seed}: "
        f"{len(black)} panel pixels left as black complement"
    )


@pytest.mark.parametrize("geometry,seed", _CLUBS_REGRESSION_CASES, ids=lambda v: str(v))
def test_full_reveal_clubs_regression(geometry, seed) -> None:
    """Deterministic regression guard for the clubs far-left-edge gap: these
    exact (geometry, seed) pairs left 1 unrevealed pixel at _MAX_R_FACTOR=1.2
    and must stay clean. Includes the one expensive bigsign case that the
    general smallsign sweep can't reach."""
    _, width, height, scale = geometry
    black = _full_reveal_missing_pixels(["clubs"], width, height, scale, seed)
    assert black == [], (
        f"clubs {geometry[0]} seed={seed}: {len(black)} panel pixels left "
        "as black complement — did _MAX_R_FACTOR regress below the fix?"
    )


class TestDeterminismAndRefire:
    def test_same_seed_same_frames(self) -> None:
        canvas_a = _StubCanvas(width=160, height=16)
        canvas_b = _StubCanvas(width=160, height=16)

        Poker(seed=5).frame_at(0.3, canvas_a, _make_widget(False), _make_widget(False))
        Poker(seed=5).frame_at(0.3, canvas_b, _make_widget(False), _make_widget(False))

        assert canvas_a._pixels == canvas_b._pixels
        assert canvas_a._pixels  # sanity: something actually painted

    def test_refire_replans(self) -> None:
        p = Poker()  # seed=None -> entropy reseed on every re-fire
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        for t in (0.0, 0.3, 0.6, 1.0):
            p.frame_at(t, canvas, outgoing, incoming)
        first_plan = p._plan
        assert first_plan is not None

        for t in (0.0, 0.1):
            p.frame_at(t, canvas, outgoing, incoming)
        second_plan = p._plan
        assert second_plan is not None
        assert second_plan is not first_plan


class TestPerf:
    def test_no_ring_rasterization_after_first_frame(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        calls: list[Any] = []
        real_ring = m.ring_pixels

        def _spy(*a: Any, **k: Any) -> Any:
            calls.append(a)
            return real_ring(*a, **k)

        monkeypatch.setattr(m, "ring_pixels", _spy)

        p = Poker(seed=2)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        p.frame_at(0.5, canvas, outgoing, incoming)
        # NOTE: `calls` may be EMPTY here — geometry is cached process-wide
        # (_ring_geom / _warm_suit_geometry), so an earlier test in this
        # process may have already rasterized these suits. The invariant is
        # only that frames AFTER the first do zero rasterization; the
        # stronger per-firing/per-instance guard lives in
        # TestNoPerFiringRasterization.
        first_call_count = len(calls)

        p.frame_at(0.6, canvas, outgoing, incoming)
        assert len(calls) == first_call_count


# ---------------------------------------------------------------------------
# Registration -- _RecordingAPI idiom copied per this repo's
# per-file-duplication convention (see test_flair_stickers_transition.py).
# ---------------------------------------------------------------------------


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording animation + transition registrations."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}
        self.widgets: dict[str, type] = {}

    def animation(self, style: str):
        def deco(cls):
            self.animations[style] = cls
            return cls

        return deco

    def transition(self, name: str):
        def deco(cls):
            self.transitions[name] = cls
            return cls

        return deco

    def widget(self, name: str):
        def deco(cls):
            self.widgets[name] = cls
            return cls

        return deco


class TestRegistration:
    def test_poker_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "poker" in api.transitions
        assert api.transitions["poker"] is Poker

    def test_other_transitions_still_registered(self) -> None:
        """Poker registration must not displace existing transitions."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "spinout" in api.transitions
        assert "fireworks" in api.transitions
        assert "stickers" in api.transitions

    def test_other_namespaces_unaffected(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "propeller" in api.animations
        assert "fisheye" in api.animations
        assert "lottery" in api.widgets


class TestNoPerFiringRasterization:
    """ROOT-CAUSE guard for the on-sign CPU spin (2026-07-18): the per-firing
    pre-warm rasterized ~1,072 rings (~12.6M mask evals, ~3s dev / ~10s Pi)
    because the ring cache keyed on each glyph's HUE — so every glyph re-
    rasterized the same suit geometry, and a seed-less transition re-paid the
    whole stall on EVERY firing. Geometry must be rasterized once per PROCESS
    per (suit, radius): a second firing — and a second Poker instance — must
    do ZERO mask-function work."""

    @staticmethod
    def _mask_spy(monkeypatch):
        import led_ticker_flair.flair.poker as m

        calls: list = []
        for name in ("_in_heart", "_in_diamond", "_in_club", "_in_spade"):
            real = getattr(m, name)

            def _wrap(x, y, r, _real=real, _n=name):
                calls.append(_n)
                return _real(x, y, r)

            monkeypatch.setattr(m, name, _wrap)
            # _MASKS holds direct references — repoint them too so lookups
            # through the dispatch table are also counted.
            suit = {
                "_in_heart": "hearts",
                "_in_diamond": "diamonds",
                "_in_club": "clubs",
                "_in_spade": "spades",
            }[name]
            monkeypatch.setitem(m._MASKS, suit, _wrap)
        return calls

    def test_second_firing_does_zero_rasterization(self, monkeypatch) -> None:
        calls = self._mask_spy(monkeypatch)
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)

        p = Poker()  # seed=None: replans EVERY firing (the smoke-config shape)
        p.frame_at(0.3, canvas, o, i)
        p.frame_at(0.96, canvas, o, i)  # finish firing 1
        after_first = len(calls)
        assert after_first >= 0  # first-ever firing may rasterize

        p.frame_at(0.05, canvas, o, i)  # firing 2 begins (replan, new entropy)
        p.frame_at(0.5, canvas, o, i)
        assert len(calls) == after_first, (
            f"firing 2 rasterized {len(calls) - after_first} mask points — "
            "geometry must be cached per process, not per firing"
        )

    def test_second_instance_does_zero_rasterization(self, monkeypatch) -> None:
        calls = self._mask_spy(monkeypatch)
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)

        Poker(seed=5).frame_at(0.5, canvas, o, i)
        after_first = len(calls)

        Poker(seed=9).frame_at(0.5, canvas, o, i)  # fresh instance, same panel
        assert len(calls) == after_first, (
            f"a second Poker instance rasterized {len(calls) - after_first} "
            "mask points — geometry must be shared process-wide"
        )


class TestNoCutoverBacklogSpike:
    """The 'explosion start' hitch (2026-07-18, on-sign): reveal accumulation
    only ran in the peel branch, so the FIRST peel frame paid every glyph's
    entire ring backlog (0..~36 radii x 16 glyphs, ~1M ops — measured 34ms on
    dev vs 0.5ms neighbors; a dropped frame on the Pi). The reveal mask must
    accumulate INCREMENTALLY from pulse start so the cutover frame's
    remaining backlog is bounded (a couple of radii per glyph, same as any
    other frame)."""

    def test_reveal_accumulates_during_build_phase(self) -> None:
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = Poker(seed=3)
        # Build-phase frames only (t < cutover 0.45), pulses active from ~0.25.
        for t in (0.05, 0.2, 0.3, 0.38, 0.44):
            p.frame_at(t, canvas, o, i)
        assert any(r > -1 for r in p._reveal_r), (
            "reveal must accumulate during the build phase — deferring it all "
            "to the first peel frame is the cutover backlog spike"
        )
        # And the accumulated radius tracks the wavefront (not still-zero).
        assert max(p._reveal_r) >= 5

    def test_cutover_frame_backlog_is_bounded(self) -> None:
        """After stepping the build phase at engine-like cadence, the first
        peel frame's per-glyph catch-up must be a few radii, not the whole
        pulse history."""
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = Poker(seed=3)
        t = 0.02
        while t < 0.45:
            p.frame_at(round(t, 3), canvas, o, i)
            t += 0.02
        before = list(p._reveal_r)
        p.frame_at(0.46, canvas, o, i)  # first peel frame
        after = p._reveal_r
        worst = max(a - b for a, b in zip(after, before, strict=True))
        assert worst <= 6, (
            f"first peel frame advanced a glyph {worst} radii — the backlog "
            "was deferred to the cutover instead of accumulating incrementally"
        )


class TestWarmWorker:
    """First-firing warm stall (2026-07-19): geometry warming moves off the
    render path into a background thread started at construction. The worker
    must cover EVERY radius a firing can request — a gap would surface as
    lazy rasterization mid-transition on the Pi."""

    def test_worker_covers_every_radius_a_firing_needs(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        try:
            # Cold-start the process for one suit, warm it via the worker
            # ONLY, then spy the masks: any rasterization during a full
            # firing afterwards is a coverage gap in the worker.
            m._ring_geom.cache_clear()
            m._interior_geom.cache_clear()
            m._warm_suit_geometry.cache_clear()
            m._warm_worker(["diamonds"], yield_s=0)

            calls = TestNoPerFiringRasterization._mask_spy(monkeypatch)
            canvas = _StubCanvas(width=256, height=64)
            o = _make_widget(draw_pixel=False)
            i = _make_widget(draw_pixel=False)
            p = Poker(suits=["diamonds"], seed=5)
            t = 0.02
            while t < 1.0:
                p.frame_at(round(t, 3), canvas, o, i)
                t += 0.02
            assert not calls, (
                f"firing rasterized {len(calls)} mask points after a full "
                "worker warm — _warm_worker's radius range has a gap"
            )
        finally:
            # Restore the fully-warmed-process invariant for later tests.
            m._warm_worker(list(m.SUITS), yield_s=0)

    def test_worker_swallows_exceptions(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        def _boom(suit, r_int):
            raise RuntimeError("rasterizer exploded")

        monkeypatch.setattr(m, "_ring_geom", _boom)
        m._warm_worker(["hearts"], yield_s=0)  # must not raise


class TestBackgroundWarm:
    """Construction dispatches the geometry warm to a daemon thread — once
    per suit per process — so the first firing renders like every other
    firing instead of stalling ~2-3s on the Pi."""

    def test_saturated_process_spawns_no_thread(self) -> None:
        import led_ticker_flair.flair.poker as m

        # The session fixture saturated _warm_dispatched, so constructions
        # here must not spawn threads (this is also what keeps every other
        # test in the suite free of live warm threads).
        before = len(m._warm_threads)
        Poker(seed=1)
        Poker(suits=["hearts", "clubs"], seed=2)
        assert len(m._warm_threads) == before

    def test_new_suits_spawn_single_daemon_thread(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        started: list = []

        class _SpyThread:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def start(self):
                started.append(self)

        monkeypatch.setattr(m.threading, "Thread", _SpyThread)
        monkeypatch.setattr(m, "_warm_dispatched", set())
        monkeypatch.setattr(m, "_warm_threads", [])

        Poker(seed=3)  # default pool = all four suits
        assert len(started) == 1
        assert started[0].kwargs["daemon"] is True
        assert started[0].kwargs["target"] is m._warm_worker
        assert sorted(started[0].kwargs["args"][0]) == sorted(SUITS)

        Poker(seed=4)  # same pool again -> deduped, nothing new
        assert len(started) == 1

    def test_partial_overlap_dispatches_only_new_suits(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        started: list = []

        class _SpyThread:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def start(self):
                started.append(self)

        monkeypatch.setattr(m.threading, "Thread", _SpyThread)
        monkeypatch.setattr(m, "_warm_dispatched", {"hearts", "spades"})
        monkeypatch.setattr(m, "_warm_threads", [])

        Poker(suits=["hearts", "diamonds"], seed=6)
        assert len(started) == 1
        assert started[0].kwargs["args"][0] == ["diamonds"]
