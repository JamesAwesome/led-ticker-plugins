"""Validation tests for the re-homed Calendar widget.

Two surfaces are exercised:

- ``Calendar.validate_config(cfg)`` — field/type ERRORS (returns a list of
  strings; non-empty => rejected). Ported from core's
  ``test_calendar_validate_contract.py``.
- ``Calendar.validate_config_warnings(cfg, ctx)`` — advisory WARNINGS surfaced by
  ``led-ticker validate``. Re-homed from core's ``validate.py`` rules 54 (ics
  local-file existence), 22 (two_row band fit) and 23 (held-top overflow), all
  emitted as warnings here.

Dropped from the core source (intentionally, see Task 5 report): the pure
core-machinery tests ``test_list_fields_calendar_shows_hint_descriptions``,
``test_list_fields_calendar_layout_is_calendar_specific`` and
``test_calendar_builds_through_factory`` — those exercise core's
``_list_widget_fields`` / ``validate_widget_cfg`` plumbing, which is core's
responsibility (covered by core's own tests), not the plugin's.
"""

from pathlib import Path

from led_ticker.plugin import ValidationContext

from led_ticker_calendar.calendar import Calendar

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "calendar_sample.ics"
_V = f"file://{_FIXTURE}"


def _ctx(tmp_path, *, scale=1, content_height=16, panel_width=160, panel_height=16):
    return ValidationContext(
        scale=scale,
        content_height=content_height,
        panel_width=panel_width,
        panel_height=panel_height,
        config_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# A. validate_config ERROR assertions (ported from core contract test)
# ---------------------------------------------------------------------------


def test_validate_config_missing_ics_url_is_error():
    errors = Calendar.validate_config({"type": "calendar"})
    assert errors
    assert any("ics_url" in m for m in errors)


def test_validate_config_bad_layout_is_error():
    errors = Calendar.validate_config(
        {"type": "calendar", "ics_url": "x", "layout": "bad"}
    )
    assert errors
    assert any("layout" in m for m in errors)


def test_validate_config_bad_timezone_is_error():
    errors = Calendar.validate_config(
        {"type": "calendar", "ics_url": "x", "timezone": "Mars/Phobos"}
    )
    assert errors
    assert any("timezone" in m for m in errors)


def test_validate_config_negative_max_events_is_error():
    errors = Calendar.validate_config(
        {"type": "calendar", "ics_url": "x", "max_events": -1}
    )
    assert errors
    assert any("max_events" in m for m in errors)


def test_validate_config_bad_time_format_is_error():
    errors = Calendar.validate_config(
        {"type": "calendar", "ics_url": "x", "time_format": "bogus"}
    )
    assert errors
    assert any("time_format" in m for m in errors)


def test_validate_config_accepts_clean_https_config():
    errors = Calendar.validate_config(
        {"type": "calendar", "ics_url": "https://x.com/c.ics", "timezone": "UTC"}
    )
    assert errors == []


# ---------------------------------------------------------------------------
# B. ics_url local-file existence WARNING (re-homed rule 54)
# ---------------------------------------------------------------------------


def test_missing_local_ics_emits_warning(tmp_path):
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": "does_not_exist.ics"}
    warnings = Calendar.validate_config_warnings(cfg, ctx)
    assert any("does not exist" in w for w in warnings)


def test_missing_local_ics_resolves_against_config_dir(tmp_path):
    # A relative path is resolved against ctx.config_dir; create the file there.
    (tmp_path / "events.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": "events.ics"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_existing_local_ics_emits_no_warning(tmp_path):
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": _V}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_existing_bare_path_ics_emits_no_warning(tmp_path):
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": str(_FIXTURE)}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_file_url_with_localhost_and_percent_encoding(tmp_path):
    p = tmp_path / "my events.ics"  # space -> percent-encoded
    p.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    ctx = _ctx(tmp_path)
    url = f"file://localhost{p.as_posix()}".replace(" ", "%20")
    cfg = {"type": "calendar", "ics_url": url}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_https_ics_url_is_never_path_checked(tmp_path):
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": "https://example.com/c.ics"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_webcal_ics_url_is_never_path_checked(tmp_path):
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": "webcal://example.com/c.ics"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_placeholder_ics_is_error_not_path_warning(tmp_path):
    # The unfilled placeholder is a hard ERROR from validate_config, not a path
    # warning (validate_config_warnings only runs when there are no errors).
    cfg = {"type": "calendar", "ics_url": "PASTE_YOUR_ICS_URL_HERE"}
    errors = Calendar.validate_config(cfg)
    assert any("placeholder" in m for m in errors)


# ---------------------------------------------------------------------------
# C. two_row band-fit + held-top overflow WARNINGS (re-homed rules 22, 23)
# ---------------------------------------------------------------------------


def test_two_row_default_font_is_clean(tmp_path):
    # Default font (FONT_DEFAULT -> substituted to FONT_SMALL, lh 8); content 16
    # -> 50/50 band = 8 rows. FONT_SMALL fits. scale=1 gives a 160-wide canvas so
    # the held phrase fits too. No warnings expected.
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": _V, "layout": "two_row"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_two_row_oversized_explicit_font_warns(tmp_path):
    # 7x13 has logical line-height 13 > 8-row band -> band-fit warning.
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": _V, "layout": "two_row", "font": "7x13"}
    warnings = Calendar.validate_config_warnings(cfg, ctx)
    assert any("exceeds the per-row band" in w for w in warnings)


def test_two_row_top_row_height_ge_content_warns(tmp_path):
    # top_row_height >= content_height leaves the bottom band zero rows.
    ctx = _ctx(tmp_path)
    cfg = {
        "type": "calendar",
        "ics_url": _V,
        "layout": "two_row",
        "top_row_height": 16,
    }
    warnings = Calendar.validate_config_warnings(cfg, ctx)
    assert warnings  # zero-row bottom band surfaces a warning


def test_two_row_non_int_top_row_height_does_not_raise(tmp_path):
    # A string top_row_height is a validate_config ERROR; validate_config_warnings
    # must return [] without raising (never-raises contract).
    ctx = _ctx(tmp_path)
    cfg = {
        "type": "calendar",
        "ics_url": _V,
        "layout": "two_row",
        "top_row_height": "bad",
    }
    result = Calendar.validate_config_warnings(cfg, ctx)
    assert result == []


def test_two_row_held_top_clips_on_narrow_bigsign_canvas(tmp_path):
    # Bigsign-like: scale=4, content_height=16, panel 256x64 -> logical canvas is
    # only 64px wide. "Tomorrow 12:00 PM" overflows -> held-top warning.
    ctx = _ctx(tmp_path, scale=4, content_height=16, panel_width=256, panel_height=64)
    cfg = {"type": "calendar", "ics_url": _V, "layout": "two_row"}
    warnings = Calendar.validate_config_warnings(cfg, ctx)
    assert any("clips on this" in w for w in warnings)


def test_two_row_held_top_fits_at_scale_2(tmp_path):
    # scale=2 on the bigsign -> 128px logical canvas; the held phrase fits.
    ctx = _ctx(tmp_path, scale=2, content_height=16, panel_width=256, panel_height=64)
    cfg = {"type": "calendar", "ics_url": _V, "layout": "two_row"}
    warnings = Calendar.validate_config_warnings(cfg, ctx)
    assert not any("clips on this" in w for w in warnings)


def test_two_row_explicit_6x12_font_is_clean(tmp_path):
    # An explicit 6x12 (FONT_DEFAULT) is substituted with FONT_SMALL just like the
    # inherited default, so it stays clean on the smallsign.
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": _V, "layout": "two_row", "font": "6x12"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_two_row_custom_strftime_skips_held_top_check(tmp_path):
    # A custom strftime time_format has unknown width -> held-top check skipped.
    # On the narrow bigsign canvas this means NO clip warning despite the scale.
    ctx = _ctx(tmp_path, scale=4, content_height=16, panel_width=256, panel_height=64)
    cfg = {
        "type": "calendar",
        "ics_url": _V,
        "layout": "two_row",
        "time_format": "%H:%M",
    }
    warnings = Calendar.validate_config_warnings(cfg, ctx)
    assert not any("clips on this" in w for w in warnings)


def test_non_two_row_layout_skips_two_row_warnings(tmp_path):
    # agenda layout: only the ics-path check runs; band/held-top checks skipped.
    ctx = _ctx(tmp_path, scale=4, content_height=16, panel_width=256, panel_height=64)
    cfg = {"type": "calendar", "ics_url": _V, "layout": "agenda", "font": "7x13"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []


def test_warnings_returns_empty_for_clean_https_two_row(tmp_path):
    ctx = _ctx(tmp_path)
    cfg = {"type": "calendar", "ics_url": "https://x.com/c.ics", "layout": "two_row"}
    assert Calendar.validate_config_warnings(cfg, ctx) == []
