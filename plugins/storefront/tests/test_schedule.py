from datetime import date as _date
from datetime import datetime

import pytest

from led_ticker_storefront.schedule import (
    DAYS,
    evaluate,
    fmt_range,
    is_open,
    next_change,
    parse_day,
    parse_exceptions,
    parse_schedule,
    parse_time,
    ranges_for,
)


def test_days_order():
    assert DAYS == ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def test_parse_time_basic():
    assert parse_time("09:00") == 540
    assert parse_time("17:30") == 1050
    assert parse_time("00:00") == 0


def test_parse_time_24_only_when_allowed():
    assert parse_time("24:00", allow_24=True) == 1440
    with pytest.raises(ValueError):
        parse_time("24:00")


@pytest.mark.parametrize("bad", ["9:00", "25:00", "12:60", "noon", "0900", ""])
def test_parse_time_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


def test_parse_day_single_range():
    assert parse_day("09:00-17:00") == [(540, 1020)]


def test_parse_day_multi_range():
    assert parse_day("09:00-12:00,13:00-17:00") == [(540, 720), (780, 1020)]


def test_parse_day_closed_and_empty():
    assert parse_day("closed") == []
    assert parse_day("") == []


def test_parse_day_all_day():
    assert parse_day("00:00-24:00") == [(0, 1440)]


def test_parse_day_overnight_wrap_allowed():
    assert parse_day("18:00-02:00") == [(1080, 120)]


@pytest.mark.parametrize("bad", ["09:0017:00", "09:00-", "-17:00", "09:00_17:00"])
def test_parse_day_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_day(bad)


def test_parse_time_rejects_fullwidth_unicode_digits():
    # "０９:００" — fullwidth digits are \d-matching under re.UNICODE (Python's
    # default) but must be rejected; only ASCII 0-9 is a valid clock digit.
    with pytest.raises(ValueError):
        parse_time("０９:００")


def test_parse_day_rejects_zero_length_range():
    with pytest.raises(ValueError, match="closed|00:00-24:00"):
        parse_day("00:00-00:00")


def test_parse_day_rejects_zero_length_range_non_midnight():
    with pytest.raises(ValueError, match="closed|00:00-24:00"):
        parse_day("09:00-09:00")


def test_parse_day_overnight_wrap_still_allowed():
    assert parse_day("18:00-02:00") == [(1080, 120)]


def test_parse_day_all_day_still_allowed():
    assert parse_day("00:00-24:00") == [(0, 1440)]


def test_parse_schedule_maps_days():
    sched = parse_schedule({"mon": "09:00-17:00", "sun": "closed"})
    assert sched["mon"] == [(540, 1020)]
    assert sched["sun"] == []
    assert "tue" not in sched


def test_parse_schedule_rejects_unknown_day():
    with pytest.raises(ValueError):
        parse_schedule({"funday": "09:00-17:00"})


def test_fmt_range():
    assert fmt_range((540, 1020)) == "09:00-17:00"
    assert fmt_range((0, 1440)) == "00:00-24:00"


# Monday 2024-01-01 .. Sunday 2024-01-07 (weekday() Mon=0)
MON_1000 = datetime(2024, 1, 1, 10, 0)
MON_0800 = datetime(2024, 1, 1, 8, 0)
MON_1700 = datetime(2024, 1, 1, 17, 0)  # exclusive end → closed
MON_1230 = datetime(2024, 1, 1, 12, 30)  # lunch gap
FRI_2300 = datetime(2024, 1, 5, 23, 0)  # inside 18:00-02:00 start day
SAT_0030 = datetime(2024, 1, 6, 0, 30)  # inside Friday's wrap, next calendar day
SAT_0230 = datetime(2024, 1, 6, 2, 30)  # after wrap end → closed
SUN_1200 = datetime(2024, 1, 7, 12, 0)


def _sched():
    return parse_schedule(
        {
            "mon": "09:00-12:00,13:00-17:00",
            "fri": "18:00-02:00",
            "sun": "closed",
        }
    )


def test_open_inside_range():
    assert evaluate(_sched(), MON_1000) == "mon 09:00-12:00"
    assert is_open(_sched(), MON_1000) is True


def test_closed_before_open():
    assert evaluate(_sched(), MON_0800) is None


def test_end_is_exclusive():
    assert is_open(_sched(), MON_1700) is False


def test_closed_in_lunch_gap():
    assert is_open(_sched(), MON_1230) is False


def test_overnight_open_on_start_day():
    assert evaluate(_sched(), FRI_2300) == "fri 18:00-02:00"


def test_overnight_open_after_midnight_belongs_to_prev_day():
    assert evaluate(_sched(), SAT_0030) == "fri 18:00-02:00"


def test_overnight_closed_after_wrap_end():
    assert is_open(_sched(), SAT_0230) is False


def test_absent_day_is_closed():
    # Saturday has no key and no inherited wrap after 02:00 → closed
    assert is_open(_sched(), datetime(2024, 1, 6, 12, 0)) is False


def test_explicit_closed_day():
    assert is_open(_sched(), SUN_1200) is False


def test_parse_exceptions_specific_and_recurring():
    exc = parse_exceptions(
        {
            "2026-11-26": "closed",
            "12-25": "closed",
            "12-24": "09:00-13:00",
        }
    )
    assert exc[(2026, 11, 26)] == []
    assert exc[(None, 12, 25)] == []
    assert exc[(None, 12, 24)] == [(540, 780)]


def test_parse_exceptions_values_reuse_day_grammar():
    exc = parse_exceptions({"2026-12-31": "20:00-02:00,09:00-12:00"})
    assert exc[(2026, 12, 31)] == [(1200, 120), (540, 720)]


def test_parse_exceptions_feb29_recurring_allowed():
    assert (None, 2, 29) in parse_exceptions({"02-29": "closed"})


@pytest.mark.parametrize(
    "bad",
    [
        "02-30",  # not a real date
        "13-01",  # bad month
        "2026-02-30",  # not a real date (specific)
        "12/25",  # wrong separator
        "Dec-25",  # not numeric
        "2-5",  # not zero-padded
        "2026-1-5",  # not zero-padded (specific)
        "",  # empty
    ],
)
def test_parse_exceptions_rejects_malformed_keys(bad):
    with pytest.raises(ValueError):
        parse_exceptions({bad: "closed"})


def test_parse_exceptions_bad_value_raises():
    with pytest.raises(ValueError):
        parse_exceptions({"12-25": "9-5"})


def test_parse_exceptions_empty_dict():
    assert parse_exceptions({}) == {}


def _wk():
    return parse_schedule({"mon": "09:00-17:00", "fri": "18:00-02:00"})


def test_ranges_for_precedence_specific_beats_recurring_beats_weekly():
    exc = parse_exceptions({"2024-01-01": "10:00-12:00", "01-01": "closed"})
    ranges, label = ranges_for(_wk(), exc, _date(2024, 1, 1))
    assert ranges == [(600, 720)]
    assert label == "exception 2024-01-01"
    # recurring only:
    exc2 = parse_exceptions({"01-01": "closed"})
    ranges2, label2 = ranges_for(_wk(), exc2, _date(2024, 1, 1))
    assert ranges2 == [] and label2 == "exception 01-01"
    # no exception -> weekly
    ranges3, label3 = ranges_for(_wk(), {}, _date(2024, 1, 1))
    assert ranges3 == [(540, 1020)] and label3 == "mon"


def test_exception_replaces_not_merges():
    exc = parse_exceptions({"01-01": "10:00-12:00"})  # Monday
    assert is_open(_wk(), datetime(2024, 1, 1, 9, 30), exc) is False  # weekly 9-5 gone
    assert is_open(_wk(), datetime(2024, 1, 1, 11, 0), exc) is True


def test_wrap_belongs_to_start_day_into_closed_exception():
    # Friday 18:00-02:00; Saturday 2024-01-06 exception "closed"
    exc = parse_exceptions({"2024-01-06": "closed"})
    assert evaluate(_wk(), datetime(2024, 1, 6, 0, 30), exc) == "fri 18:00-02:00"
    assert is_open(_wk(), datetime(2024, 1, 6, 2, 30), exc) is False
    assert is_open(_wk(), datetime(2024, 1, 6, 12, 0), exc) is False


def test_exception_day_wrap_carries_into_next_day():
    # NYE special hours wrap into Jan 1, even when Jan 1 is itself closed
    exc = parse_exceptions({"2023-12-31": "20:00-02:00", "2024-01-01": "closed"})
    got = evaluate(_wk(), datetime(2024, 1, 1, 1, 0), exc)
    assert got == "exception 2023-12-31 20:00-02:00"
    assert is_open(_wk(), datetime(2024, 1, 1, 2, 30), exc) is False


def test_recurring_feb29_matches_leap_years_only():
    exc = parse_exceptions({"02-29": "10:00-12:00"})
    sched = parse_schedule({})  # closed all week otherwise
    assert is_open(sched, datetime(2024, 2, 29, 11, 0), exc) is True  # leap year
    assert is_open(sched, datetime(2026, 3, 1, 11, 0), exc) is False  # no feb 29


def test_evaluate_two_arg_backcompat():
    # existing call shape (no exceptions) still works and returns weekly labels
    assert evaluate(_wk(), datetime(2024, 1, 1, 10, 0)) == "mon 09:00-17:00"


def test_next_change_closes_today():
    nc = next_change(_wk(), datetime(2024, 1, 1, 10, 0))
    assert nc == datetime(2024, 1, 1, 17, 0)


def test_next_change_opens_next_open_day():
    # Monday 18:00 -> next open is Friday 18:00 (within 48h? no -> None);
    # use Thursday 12:00 -> Friday 18:00 IS within 48h
    nc = next_change(_wk(), datetime(2024, 1, 4, 12, 0))
    assert nc == datetime(2024, 1, 5, 18, 0)


def test_next_change_none_beyond_horizon():
    always = parse_schedule(
        {d: "00:00-24:00" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    )
    assert next_change(always, datetime(2024, 1, 1, 10, 0)) is None


def test_next_change_respects_exceptions():
    exc = parse_exceptions({"2024-01-01": "10:00-12:00"})
    nc = next_change(_wk(), datetime(2024, 1, 1, 10, 30), exc)
    assert nc == datetime(2024, 1, 1, 12, 0)
