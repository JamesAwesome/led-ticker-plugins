"""flair.accordion — AccordionSweep / AccordionStretch transition classes.

Stub canvas / widget fixtures copied from test_flair_laser_transition.py
(the per-file duplication is this repo's convention), with the widget
fixtures pinning ``border`` / ``bottom_text`` explicitly (a bare Mock
attribute is truthy and non-None, which would read as bordered + two-row).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas, unwrap_to_real
from PIL import Image

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair._raster import Raster
from led_ticker_flair.flair.accordion import AccordionStretch, AccordionSweep

BOTH = [AccordionSweep, AccordionStretch]
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)


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

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:  # noqa: N802
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                if len(px) == 4 and px[3] == 0:
                    r, g, b = 0, 0, 0
                else:
                    r, g, b = px[0], px[1], px[2]
                self.SetPixel(offset_x + x, offset_y + y, r, g, b)


def _text_widget(
    pixels: list[tuple[int, int, tuple[int, int, int]]],
    border: Any = None,
    bottom_text: str = "",
) -> Any:
    """A widget that SetPixels a fixed list onto whatever canvas it gets."""
    widget = mock.Mock()
    widget.hold_time = 0.0
    # A bare Mock attribute is truthy / non-None: pin the duck-typed
    # border + two-row probes explicitly.
    widget.border = border
    widget.bottom_text = bottom_text
    widget.top_row_height = None

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        for x, y, (r, g, b) in pixels:
            canvas.SetPixel(x, y, r, g, b)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _image_widget(img: Any, border: Any = None, bottom_text: str = "") -> Any:
    """A widget that paints via unwrap_to_real(canvas).SetImage (gif/still path)."""
    widget = mock.Mock()
    widget.hold_time = 0.0
    # A bare Mock attribute is truthy / non-None: pin the duck-typed
    # border + two-row probes explicitly.
    widget.border = border
    widget.bottom_text = bottom_text
    widget.top_row_height = None

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        unwrap_to_real(canvas).SetImage(img, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _glyph(x0: int, w: int, y0: int, y1: int, col: tuple[int, int, int]) -> list:
    return [(x, y, col) for x in range(x0, x0 + w) for y in range(y0, y1)]


def _ring(w: int, h: int, col: tuple[int, int, int]) -> list:
    return [
        (x, y, col)
        for y in range(h)
        for x in range(w)
        if y in (0, h - 1) or x in (0, w - 1)
    ]


def _paint(p: Any, t: float, out: Any, inc: Any, w: int = 32, h: int = 16, **kw: Any):
    c = _StubCanvas(w, h)
    p.frame_at(t, c, out, inc, **kw)
    return c


def _pset(c: Any) -> set:
    return {(x, y, col) for (x, y), col in c._pixels.items()}


TEXT = _glyph(4, 2, 4, 10, RED) + _glyph(12, 3, 4, 10, RED) + _glyph(22, 2, 4, 10, RED)
INC_TEXT = _glyph(6, 2, 3, 9, GREEN) + _glyph(18, 2, 3, 9, GREEN)


class TestConstruction:
    def test_bad_direction_raises(self):
        with pytest.raises(ValueError):
            AccordionSweep(direction="up")
        with pytest.raises(ValueError):
            AccordionStretch(direction="up")

    def test_min_frames(self):
        assert AccordionSweep.min_frames == 30
        assert AccordionStretch.min_frames == 30

    def test_keeps_runner_default_scale_switch(self):
        # Lazy incoming snapshot relies on the runner re-wrapping at 0.5.
        assert not hasattr(AccordionSweep(), "scale_switch_at")

    def test_registration_two_types_distinct_instances(self):
        api = mock.Mock()
        reg: dict[str, Any] = {}
        api.transition.side_effect = lambda name: (
            lambda cls: reg.__setitem__(name, cls) or cls
        )
        api.animation.side_effect = lambda name: lambda cls: cls
        api.widget.side_effect = lambda name: lambda cls: cls
        flair_pkg.register(api)
        assert {"accordion.sweep", "accordion.stretch"} <= set(reg)
        assert reg["accordion.sweep"] is AccordionSweep
        assert reg["accordion.stretch"] is AccordionStretch
        assert reg["accordion.sweep"]() is not reg["accordion.sweep"]()
        assert reg["accordion.stretch"]() is not reg["accordion.stretch"]()


class TestTimeline:
    @pytest.mark.parametrize("cls", BOTH)
    def test_t0_shows_outgoing_only(self, cls):
        c = _paint(cls(), 0.0, _text_widget(TEXT), _text_widget(INC_TEXT))
        assert _pset(c) == set(TEXT)

    @pytest.mark.parametrize("cls", BOTH)
    def test_beat_paints_nothing(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        _paint(p, 0.0, out, inc)
        c = _paint(p, 0.48, out, inc)
        assert c.calls == []

    @pytest.mark.parametrize("cls", BOTH)
    def test_incoming_not_drawn_before_half(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.47, 0.48, 0.499):
            _paint(p, t, out, inc)
        assert inc.draw.call_count == 0
        _paint(p, 0.5, out, inc)
        assert inc.draw.call_count == 1
        _paint(p, 0.7, out, inc)
        assert inc.draw.call_count == 1

    @pytest.mark.parametrize("cls", BOTH)
    def test_outgoing_not_drawn_live_after_snapshot(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        for i in range(20):
            _paint(p, i * 0.94 / 19, out, inc)
        assert out.draw.call_count == 1

    @pytest.mark.parametrize("cls", BOTH)
    def test_snap_resets_and_draws_live(self, cls, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.accordion.snap_reset",
            lambda cv, bg: calls.append((cv, bg)),
        )
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        _paint(p, 0.0, out, inc)
        _paint(p, 0.6, out, inc)
        c = _StubCanvas(32, 16)
        p.frame_at(0.96, c, out, inc, incoming_bg_color=(1, 2, 3))
        assert calls == [(c, (1, 2, 3))]
        assert inc.draw.call_args_list[-1] == mock.call(c, cursor_pos=0)
        assert _pset(c) == set(INC_TEXT)

    @pytest.mark.parametrize("cls", BOTH)
    def test_end_of_incoming_phase_equals_slots(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        _paint(p, 0.0, out, inc)
        _paint(p, 0.5, out, inc)
        c = _paint(p, 0.9499, out, inc)
        assert _pset(c) == set(INC_TEXT)

    @pytest.mark.parametrize("cls", BOTH)
    def test_refire_resnapshots(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        for t in (0.0, 0.3, 0.6, 0.96):
            _paint(p, t, out, inc)
        new_px = _glyph(9, 2, 2, 12, BLUE)
        out2 = _text_widget(new_px)
        c = _paint(p, 0.0, out2, inc)
        assert _pset(c) == set(new_px)
        # Equal NON-ZERO t is not a refire: a third widget is never
        # snapshotted. (t == 0.0 always refires: test_t0_always_refires.)
        mid = _paint(p, 0.2, out2, inc)
        out3 = _text_widget(_glyph(1, 1, 1, 2, GREEN))
        c = _paint(p, 0.2, out3, inc)
        assert out3.draw.call_count == 0
        assert _pset(c) == _pset(mid)

    @pytest.mark.parametrize("cls", BOTH)
    def test_t0_always_refires(self, cls):
        # A firing cancelled right after its t=0 frame leaves _last_t == 0;
        # the next firing's t=0 must still re-snapshot, not replay the
        # stale outgoing plan.
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        _paint(p, 0.0, out, inc)  # cancelled firing: only its t=0 frame
        new_px = _glyph(9, 2, 2, 12, BLUE)
        out2 = _text_widget(new_px)
        c = _paint(p, 0.0, out2, inc)
        assert out2.draw.call_count == 1
        assert _pset(c) == set(new_px)

    @pytest.mark.parametrize("cls", BOTH)
    def test_equal_nonzero_t_is_not_a_refire(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        _paint(p, 0.0, out, inc)
        _paint(p, 0.2, out, inc)
        out2 = _text_widget(_glyph(1, 1, 1, 2, GREEN))
        _paint(p, 0.2, out2, inc)
        assert out2.draw.call_count == 0

    @pytest.mark.parametrize("cls", BOTH)
    def test_outgoing_scroll_pos_forwarded(self, cls):
        p = cls()
        out, inc = _text_widget(TEXT), _text_widget(INC_TEXT)
        _paint(p, 0.0, out, inc, outgoing_scroll_pos=-7)
        assert out.draw.call_args.kwargs["cursor_pos"] == -7


class TestScaled:
    def test_scaled_peek_is_8_real_px(self):
        # logical x 0, 10, 20 -> real cols 0, 40, 80: spacing 40 >> 8.
        px = [(x, 6, RED) for x in (0, 10, 20)]
        c = ScaledCanvas(_StubCanvas(256, 64), scale=4, content_height=16)
        p = AccordionSweep()
        p.frame_at(0.0, c, _text_widget(px), _text_widget([]))
        assert p._out_plan is not None
        decks = p._out_plan[0]
        assert [card.slot for card in decks[0].cards] == [0, 40, 80]
        assert all(d.peek == 8 for d in decks)

    def test_cross_scale_incoming_snapshot_uses_new_wrapper(self):
        real = _StubCanvas(256, 64)
        out = _text_widget([(3, 6, RED)])
        inc = _text_widget([(5, 6, GREEN)])
        p = AccordionStretch()
        c2 = ScaledCanvas(real, scale=2, content_height=16)
        p.frame_at(0.0, c2, out, inc)
        p.frame_at(0.3, c2, out, inc)
        assert p._raster_key is not None and p._raster_key[2] == 2
        c4 = ScaledCanvas(real, scale=4, content_height=16)
        p.frame_at(0.5, c4, out, inc)
        assert p._raster_key is not None and p._raster_key[2] == 4
        assert p._in_plan is not None
        (deck,) = p._in_plan[0]
        # logical x=5 at scale 4 -> real cols 20..23, one 4-wide card
        assert [(card.slot, card.width) for card in deck.cards] == [(20, 4)]
        # the outgoing decks (built at scale 2) are untouched by the re-key
        assert p._out_plan is not None
        (odeck,) = p._out_plan[0]
        assert [(card.slot, card.width) for card in odeck.cards] == [(6, 2)]

    def test_geometry_change_reallocates(self):
        # Review Focus 4: hot-reload smallsign -> bigsign dims between firings.
        p = AccordionSweep()
        small_out = _text_widget(_glyph(10, 2, 2, 8, RED))
        inc = _text_widget([])
        for t in (0.0, 0.3, 0.6, 0.96):
            p.frame_at(t, _StubCanvas(160, 16), small_out, inc)
        big = _StubCanvas(256, 64)
        sc = ScaledCanvas(big, scale=4, content_height=16)
        # logical x=50 -> real 200..203: only exists in a 256-wide raster
        big_out = _text_widget([(50, 6, RED)])
        p.frame_at(0.0, sc, big_out, inc)  # refire on the new geometry
        assert p._raster_key == (256, 64, 4, 16)
        assert p._out_plan is not None
        (deck,) = p._out_plan[0]
        assert [(card.slot, card.width) for card in deck.cards] == [(200, 4)]
        assert {(x, y) for x, y, *_ in big.calls} == {
            (x, y) for x in range(200, 204) for y in range(24, 28)
        }


class TestContent:
    @pytest.mark.parametrize("cls", BOTH)
    def test_image_widget_one_card_slides(self, cls):
        img = Image.new("RGB", (160, 16), (200, 100, 50))
        out = _image_widget(img)
        inc = _text_widget([])
        p = cls()
        c0 = _paint(p, 0.0, out, inc, w=160, h=16)
        assert len(c0._pixels) == 160 * 16
        assert p._out_plan is not None
        decks = p._out_plan[0]
        assert len(decks) == 1 and len(decks[0].cards) == 1
        mid = _paint(p, 0.3, out, inc, w=160, h=16)
        assert 0 < len(mid._pixels) < 160 * 16  # slid part-way off
        # Off-panel by the end of the outgoing phase. (A full-panel card
        # clears the 160-px panel at k >= 320/321, i.e. t >= ~0.4735.)
        end = _paint(p, 0.4749, out, inc, w=160, h=16)
        assert end.calls == []

    @pytest.mark.parametrize("cls", BOTH)
    def test_border_ring_static_and_on_top(self, cls):
        border = mock.Mock(thickness=1)
        ring = _ring(32, 16, BLUE)
        glyphs = _glyph(5, 2, 4, 10, RED) + _glyph(15, 2, 4, 10, RED)
        out = _text_widget(ring + glyphs, border=border)
        p = cls()
        _paint(p, 0.0, out, _text_widget([]))
        c = _paint(p, 0.3, out, _text_widget([]))
        painted = _pset(c)
        assert set(ring) <= painted  # static, at its snapshot colour
        ring_xy = {(x, y) for x, y, _ in ring}
        # Ring painted AFTER the cards: the call log ends with exactly the
        # ring, preceded by card pixels (cards under the frame get covered).
        n = len(ring)
        assert len(c.calls) > n
        assert {(x, y, (r, g, b)) for x, y, r, g, b in c.calls[-n:]} == set(ring)
        red_now = {
            p_ for p_ in painted if p_[2] == RED and (p_[0], p_[1]) not in ring_xy
        }
        assert red_now and red_now != set(glyphs)  # the glyphs have moved

    @pytest.mark.parametrize("cls", BOTH)
    @pytest.mark.parametrize("mode", ["chase", "alternate", "unison"])
    def test_lightbulb_ring_static_smallsign(self, cls, mode):
        # Real core LightbulbBorder on the 160x16 smallsign (1x1 bulbs,
        # gap 3, ~25% of each edge lit): the bulbs must stay painted, at
        # their snapshot colours, throughout the outgoing phase, and never
        # become cards.
        from led_ticker.borders import LightbulbBorder

        border = LightbulbBorder(mode=mode)
        ring_raster = Raster(160, 16)
        border.paint(ring_raster, 0)
        ring = [
            (x, y, ring_raster.get(x, y))
            for y in range(16)
            for x in range(160)
            if ring_raster.get(x, y) not in (None, (0, 0, 0))
        ]
        assert ring
        glyphs = _glyph(10, 3, 3, 13, RED) + _glyph(60, 4, 3, 13, RED)
        out = _text_widget(ring + glyphs, border=border)
        p = cls()
        _paint(p, 0.0, out, _text_widget([]), w=160, h=16)
        decks = p._out_plan[0]
        ring_xy = {(x, y) for x, y, _ in ring}
        assert len(decks[0].cards) == 2  # just the glyphs
        for card in decks[0].cards:
            for dx, y, _ in card.pixels:
                assert (card.slot + dx, y) not in ring_xy
        for t in (0.1, 0.3, 0.47):
            c = _paint(p, t, out, _text_widget([]), w=160, h=16)
            assert set(ring) <= _pset(c), t
            n = len(ring)
            assert {(x, y, (r, g, b)) for x, y, r, g, b in c.calls[-n:]} == set(ring)
        # By the end of the outgoing phase only the ring is left.
        end = _paint(p, 0.4749, out, _text_widget([]), w=160, h=16)
        assert _pset(end) == set(ring)

    @pytest.mark.parametrize("cls", BOTH)
    def test_two_row_decks_in_sync(self, cls):
        top = _glyph(4, 2, 1, 7, RED) + _glyph(14, 2, 1, 7, RED)
        bottom = _glyph(8, 2, 9, 15, GREEN) + _glyph(24, 3, 9, 15, GREEN)
        out = _text_widget(top + bottom, bottom_text="b")
        p = cls()
        _paint(p, 0.0, out, _text_widget([]))
        assert p._out_plan is not None
        decks = p._out_plan[0]
        assert len(decks) == 2
        boundary = 8  # resolve_band_heights(16, None) -> 8 / 8 at scale 1
        for card in decks[0].cards:
            assert all(y < boundary for _dx, y, _c in card.pixels)
        for card in decks[1].cards:
            assert all(y >= boundary for _dx, y, _c in card.pixels)
        # Both decks are fully off-panel at outgoing k = 1 ...
        for deck, pos in zip(decks, p._out(decks, 32, 1.0), strict=True):
            assert all(
                x + card.width <= 0 for x, card in zip(pos, deck.cards, strict=True)
            )
        # ... and nothing is painted just before the beat.
        assert _paint(p, 0.4749, out, _text_widget([])).calls == []
        for t in (0.1, 0.25, 0.4):
            c = _paint(p, t, out, _text_widget([]))
            assert all(y < boundary for (x, y), col in c._pixels.items() if col == RED)
            assert all(
                y >= boundary for (x, y), col in c._pixels.items() if col == GREEN
            )

    @pytest.mark.parametrize("phase", ["out", "in"])
    @pytest.mark.parametrize("cls", BOTH)
    def test_two_row_decks_lockstep_mid_phase(self, cls, phase):
        # Rows that differ in width (a short centred top label over a
        # full-width bottom row, the normal two_row shape) must share ONE
        # anchor / hand trajectory, not just meet at the endpoints.
        top = [px for x0 in (60, 66, 72, 78) for px in _glyph(x0, 3, 1, 7, RED)]
        bottom = [px for x0 in range(2, 158, 8) for px in _glyph(x0, 3, 9, 15, GREEN)]
        w = _text_widget(top + bottom, bottom_text="b")
        p = cls()
        if phase == "out":
            _paint(p, 0.0, w, _text_widget([]), w=160, h=16)
            decks = p._out_plan[0]
            motion = p._out
        else:
            _paint(p, 0.0, _text_widget([]), w, w=160, h=16)
            _paint(p, 0.5, _text_widget([]), w, w=160, h=16)
            decks = p._in_plan[0]
            motion = p._in
        assert len(decks) == 2 and all(d.cards for d in decks)
        assert decks[0].cards[0].slot != decks[1].cards[0].slot
        for k in (0.25, 0.5, 0.75):
            all_pos = motion(decks, 160, k)
            if cls is AccordionStretch:
                # One common translation: every deck's first card is
                # displaced from its slot by the same amount.
                disp = {
                    round(pos[0] - d.cards[0].slot, 6)
                    for d, pos in zip(decks, all_pos, strict=True)
                }
                assert len(disp) == 1, (phase, k, disp)
                continue
            # Sweep: one shared hand. Recover it from any card the hand is
            # carrying, then every card of every deck must follow it.
            hands = {
                round(x - i * d.peek, 6)
                for d, pos in zip(decks, all_pos, strict=True)
                for i, (x, c) in enumerate(zip(pos, d.cards, strict=True))
                if x != c.slot
            }
            assert len(hands) == 1, (phase, k, hands)
            (hand,) = hands
            pick = min if phase == "out" else max
            for d, pos in zip(decks, all_pos, strict=True):
                assert pos == pytest.approx(
                    [
                        pick(float(c.slot), hand + i * d.peek)
                        for i, c in enumerate(d.cards)
                    ]
                ), (phase, k)

    @pytest.mark.parametrize("cls", BOTH)
    def test_direction_right_mirrors_left(self, cls):
        # Symmetric about x = 15.5 on a 32-wide panel.
        sym = _glyph(3, 2, 4, 10, RED) + _glyph(27, 2, 4, 10, RED)
        sym += _glyph(10, 1, 2, 12, GREEN) + _glyph(21, 1, 2, 12, GREEN)
        assert {(31 - x, y, c) for x, y, c in sym} == set(sym)
        left, right = cls(direction="left"), cls(direction="right")
        for t in (0.0, 0.1, 0.25, 0.4, 0.47, 0.5, 0.6, 0.8, 0.94):
            out, inc = _text_widget(sym), _text_widget(sym)
            lc = _paint(left, t, out, inc)
            rc = _paint(right, t, out, inc)
            assert _pset(rc) == {(31 - x, y, c) for x, y, c in _pset(lc)}, t

    @pytest.mark.parametrize("cls", BOTH)
    def test_both_empty_paints_nothing(self, cls, monkeypatch):
        # Review Focus 2: no crash, zero SetPixels except at the snap.
        snaps: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.accordion.snap_reset",
            lambda cv, bg: snaps.append(bg),
        )
        p = cls()
        out, inc = _text_widget([]), _text_widget([])
        for i in range(20):
            c = _paint(p, i * 0.94 / 19, out, inc)
            assert c.calls == []
        assert snaps == []
        c = _paint(p, 0.96, out, inc, incoming_bg_color=(9, 9, 9))
        assert snaps == [(9, 9, 9)]
        assert inc.draw.call_count == 2  # lazy snapshot + live snap draw
        assert p._out_plan is not None and p._in_plan is not None
        assert all(not d.cards for d in p._out_plan[0] + p._in_plan[0])

    @pytest.mark.parametrize("cls", BOTH)
    def test_right_border_two_row_combined(self, cls):
        # Review Focus 5: direction=right + border + two-row together.
        border = mock.Mock(thickness=1)
        ring = _ring(32, 16, BLUE)
        top = _glyph(5, 2, 2, 7, RED) + _glyph(13, 2, 2, 7, RED)
        bottom = _glyph(9, 3, 9, 14, GREEN) + _glyph(20, 2, 9, 14, GREEN)
        content = top + bottom

        def mirrored(px: list) -> list:
            return [(31 - x, y, c) for x, y, c in px]

        right = cls(direction="right")
        left = cls(direction="left")
        ring_xy = {(x, y) for x, y, _ in ring}
        boundary = 8
        for t in (0.0, 0.1, 0.25, 0.4, 0.6, 0.8):
            r_out = _text_widget(ring + content, border=border, bottom_text="b")
            r_in = _text_widget(ring + content, border=border, bottom_text="b")
            l_out = _text_widget(
                ring + mirrored(content), border=border, bottom_text="b"
            )
            l_in = _text_widget(
                ring + mirrored(content), border=border, bottom_text="b"
            )
            rc = _paint(right, t, r_out, r_in)
            lc = _paint(left, t, l_out, l_in)
            painted = _pset(rc)
            # both decks mirror left's motion on the mirrored fixture
            assert painted == {(31 - x, y, c) for x, y, c in _pset(lc)}, t
            # the ring stays static and is painted last
            assert set(ring) <= painted, t
            n = len(ring)
            assert {(x, y, (r, g, b)) for x, y, r, g, b in rc.calls[-n:]} == set(
                ring
            ), t
            # no card crosses the band boundary
            for (x, y), col in rc._pixels.items():
                if (x, y) in ring_xy:
                    continue
                assert (col == RED) == (y < boundary), (t, x, y, col)
        assert right._out_plan is not None
        assert len(right._out_plan[0]) == 2


# Overpaint slack: 0. Each lit card pixel is painted at most once per frame
# (the compositor's owner check) and the ring once, so painted SetPixels can
# never exceed lit-snapshot pixels + ring pixels. Any slack would only hide
# an overpaint bug.
_SLACK = 0


def _lit_bound(p: Any, t: float) -> int | None:
    """Max SetPixels frame ``t`` may paint, from the active plan; None for
    the snap frame (t >= SNAP_THRESHOLD: the widget's own draw)."""
    if t >= 0.95:
        return None
    if t < 0.475:
        plan = p._out_plan
    elif t >= 0.5:
        plan = p._in_plan
    else:
        return _SLACK  # the beat: nothing painted
    decks, ring = plan
    return sum(len(c.pixels) for d in decks for c in d.cards) + len(ring) + _SLACK


def _sweep(p: Any, canvas: Any, calls: list, out: Any, inc: Any, panel: int):
    """One firing, t = 0.0, 0.02 ... 0.98: assert the panel bound and the
    lit-snapshot overpaint bound on every frame."""
    for n in range(50):
        t = round(n * 0.02, 3)
        before = len(calls)
        p.frame_at(t, canvas, out, inc)
        painted = len(calls) - before
        assert painted <= int(1.5 * panel), (t, painted)
        bound = _lit_bound(p, t)
        if bound is not None:
            assert painted <= bound, (t, painted, bound)


def _dense_img() -> Any:
    """15 fully-lit 12-px columns spaced 16 apart on a 256x64 raster; the
    deck peek is 8 so neighbours overlap by 4 px (buried card area)."""
    img = Image.new("RGB", (256, 64), (0, 0, 0))
    for c in range(15):
        for x in range(8 + c * 16, 8 + c * 16 + 12):
            for y in range(64):
                img.putpixel((x, y), (200, 100, 50))
    return img


def _tiny_img() -> Any:
    img = Image.new("RGB", (256, 64), (0, 0, 0))
    for x in range(0, 256, 2):  # every other column lit: 128 1-px cards
        for y in range(64):
            img.putpixel((x, y), (200, 200, 200))
    return img


def _bigsign(img: Any):
    real = _StubCanvas(256, 64)
    return real, ScaledCanvas(real, scale=4, content_height=16), _image_widget(img)


class TestPerfUniformity:
    """Committed CI-safe perf gate (laser convention): count WORK per
    frame, not time, so a deferred-backlog bug fails deterministically."""

    @pytest.mark.parametrize("cls", BOTH)
    def test_per_frame_paint_volume_bounded(self, cls):
        canvas = _StubCanvas(width=160, height=16)
        _sweep(
            cls(),
            canvas,
            canvas.calls,
            _text_widget(TEXT),
            _text_widget(INC_TEXT),
            160 * 16,
        )

    @pytest.mark.parametrize("cls", BOTH)
    def test_refire_frames_equally_bounded(self, cls):
        canvas = _StubCanvas(width=160, height=16)
        p = cls()
        o = _text_widget(TEXT)
        i = _text_widget(INC_TEXT)
        for t in (0.3, 0.6, 0.96):  # a partial firing, then refire
            p.frame_at(t, canvas, o, i)
        _sweep(p, canvas, canvas.calls, o, i, 160 * 16)

    @pytest.mark.parametrize("cls", BOTH)
    @pytest.mark.parametrize("refire", [False, True])
    def test_full_panel_image_bounded_bigsign(self, cls, refire):
        real, sc, w = _bigsign(Image.new("RGB", (256, 64), (7, 7, 7)))
        p = cls()
        if refire:
            for t in (0.3, 0.6, 0.96):
                p.frame_at(t, sc, w, w)
        _sweep(p, sc, real.calls, w, w, 256 * 64)

    @pytest.mark.parametrize("cls", BOTH)
    @pytest.mark.parametrize("refire", [False, True])
    def test_many_tiny_cards_bounded(self, cls, refire):
        real, sc, w = _bigsign(_tiny_img())
        p = cls()
        if refire:
            for t in (0.3, 0.6, 0.96):
                p.frame_at(t, sc, w, w)
        _sweep(p, sc, real.calls, w, w, 256 * 64)
        decks = p._out_plan[0]
        assert sum(len(d.cards) for d in decks) >= 100
        assert all(d.peek < 8 for d in decks)

    @pytest.mark.parametrize("cls", BOTH)
    def test_no_buried_card_overpaint(self, cls):
        """Dense overlapping deck: painted pixels must not exceed the lit
        area of the VISIBLE (union) card spans, so painting any buried
        card pixel fails. Columns are fully lit (64 rows)."""
        real, sc, w = _bigsign(_dense_img())
        p = cls()
        overlapped = False
        for n in range(24):  # outgoing phase + beat
            t = round(n * 0.02, 3)
            if t >= 0.475:
                break
            before = len(real.calls)
            p.frame_at(t, sc, w, w)
            painted = len(real.calls) - before
            (deck,), _ring = p._out_plan
            xs = [round(x) for x in p._out([deck], 256, t / 0.475)[0]]
            covered = set()
            for x, card in zip(xs, deck.cards, strict=True):
                covered.update(range(max(x, 0), min(x + card.width, 256)))
            raw = sum(
                max(0, min(x + c.width, 256) - max(x, 0))
                for x, c in zip(xs, deck.cards, strict=True)
            )
            overlapped |= raw > len(covered)
            assert painted <= len(covered) * 64, (t, painted, len(covered) * 64)
        assert overlapped, "fixture never produced buried card area"
