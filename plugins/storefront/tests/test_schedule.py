import pytest

from led_ticker_storefront.schedule import (
    DAYS,
    fmt_range,
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
