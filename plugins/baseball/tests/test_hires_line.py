from led_ticker.plugin import HeadlessBackend, ScaledCanvas, SegmentMessage, make_color

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._hires_line import _MARGIN, HiresLine

WHITE = (255, 255, 255)


def _segs(text="NYY · Yankee Stadium"):
    return [(text, pal.IDENT)]


def _line(segments=None, **kw):
    segs = segments if segments is not None else _segs()
    return HiresLine(segments=segs, legacy=SegmentMessage(segs), **kw)


def _render(story, scale, w=512):
    real = HeadlessBackend(w, 64).create_canvas()
    story.draw(ScaledCanvas(real, scale=scale, content_height=16), 0)
    return real


def _span(real):
    ys = [y for (x, y), c in real._pixels.items() if c != (0, 0, 0)]
    return (max(ys) - min(ys) + 1) if ys else 0


def test_scale1_forwards_to_legacy_byte_identical():
    story = _line()
    hires = _render(story, 1)
    ref = HeadlessBackend(512, 64).create_canvas()
    story.legacy.draw(ScaledCanvas(ref, scale=1, content_height=16), 0)
    assert hires._pixels == ref._pixels


def test_scale_gt1_is_hires_not_bdf():
    story = _line()
    real = _render(story, 4)
    # hi-res span sits ~18-24; a BDF line block-scaled through scale=4 spans ~35.
    assert 12 <= _span(real) <= 30
    # mutation-proof: differs from what forwarding to the BDF legacy would draw.
    bdf = HeadlessBackend(512, 64).create_canvas()
    story.legacy.draw(ScaledCanvas(bdf, scale=4, content_height=16), 0)
    assert real._pixels != bdf._pixels


def test_scale_gt1_preserves_segment_color():
    teal = make_color(0, 200, 180)
    story = _line(segments=[("NYY ", teal), ("· Yankee Stadium", pal.IDENT)])
    real = _render(story, 4)
    assert any(c == (0, 200, 180) for c in real._pixels.values())


def test_long_line_fits_on_canvas_512_and_256():
    long = [
        ("PHI · " + "Very Long Ballpark Name " * 6 + "· 72°, wind 5 mph", pal.IDENT)
    ]
    for w in (512, 256):
        real = _render(_line(segments=long), 4, w=w)
        xs = [x for (x, y) in real._pixels]
        assert xs and min(xs) >= 0 and max(xs) < w  # no overflow/clip past edges


def test_multi_segment_head_overflow_stays_on_canvas():
    # A head (non-last) segment that alone blows past the usable width even
    # at the _MIN_SIZE floor. Only the LAST segment gets ellipsized today —
    # the head segment's glyphs still draw at their full, unclipped width,
    # which pushes the centered start x so far negative that a chunk of the
    # head spans the panel edge-to-edge, bleeding into the reserved right
    # margin instead of stopping at `real.width - _MARGIN`.
    #
    # HeadlessCanvas.SetPixel already bounds-checks to [0, width), so a lit
    # pixel can never literally land outside the canvas — the real,
    # observable invariant (and the one the fix restores) is that no glyph
    # is drawn past the reserved right MARGIN.
    segments = [("X" * 200, pal.IDENT), (" tail", pal.LABEL)]
    for w in (512, 256):
        real = _render(_line(segments=segments), 4, w=w)
        xs = [x for (x, y) in real._pixels]
        right_margin = w - _MARGIN
        assert xs and min(xs) >= 0
        assert max(xs) < right_margin


def test_empty_segments_forwards_to_legacy():
    story = HiresLine(segments=[], legacy=SegmentMessage(_segs()))
    real = _render(story, 4)
    ref = HeadlessBackend(512, 64).create_canvas()
    story.legacy.draw(ScaledCanvas(ref, scale=4, content_height=16), 0)
    assert real._pixels == ref._pixels


def test_frame_hooks_forward_to_legacy():
    calls = []

    class Spy(SegmentMessage):
        def advance_frame(self, *, visit_id=None):
            calls.append("advance")

        def reset_frame(self):
            calls.append("reset")

        def pause_frame(self):
            calls.append("pause")

        def resume_frame(self):
            calls.append("resume")

    story = HiresLine(segments=_segs(), legacy=Spy(_segs()))
    story.advance_frame()
    story.pause_frame()
    story.resume_frame()
    story.reset_frame()
    assert set(calls) == {"advance", "pause", "resume", "reset"}
