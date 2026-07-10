from datetime import datetime

import pytest

from led_ticker_storefront.schedule import (
    DAYS,
    evaluate,
    fmt_range,
    is_open,
    parse_day,
    parse_schedule,
    parse_time,
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
