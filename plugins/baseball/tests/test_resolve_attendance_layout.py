"""Tests for resolve_attendance_layout."""

from led_ticker_baseball.layouts import resolve_attendance_layout


def test_scale_one_is_legacy():
    assert resolve_attendance_layout("auto", 1, 160) == "legacy"


def test_auto_by_width():
    assert resolve_attendance_layout("auto", 4, 256) == "big"
    assert resolve_attendance_layout("auto", 4, 512) == "long"


def test_explicit_respected_when_it_fits():
    assert resolve_attendance_layout("long", 4, 512) == "long"
    assert resolve_attendance_layout("big", 4, 256) == "big"


def test_explicit_long_degrades_on_narrow_panel():
    assert resolve_attendance_layout("long", 4, 256) == "big"  # the guard
