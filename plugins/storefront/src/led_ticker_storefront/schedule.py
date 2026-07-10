"""Weekly business-hours schedule: parse TOML day strings into minute ranges
and evaluate open/closed against a clock. Pure logic, no rendering."""

import re
from datetime import date, timedelta

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Range = tuple[int, int]
ExcKey = tuple[int | None, int, int]

_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$", re.ASCII)


def parse_time(s, *, allow_24=False):
    m = _TIME_RE.match(s.strip())
    if not m:
        raise ValueError(f"bad time {s!r}: expected HH:MM (24-hour, zero-padded)")
    hh, mm = int(m.group(1)), int(m.group(2))
    if allow_24 and hh == 24 and mm == 0:
        return 1440
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"bad time {s!r}: out of range")
    return hh * 60 + mm


def parse_day(value):
    text = value.strip().lower()
    if text in ("", "closed"):
        return []
    ranges = []
    for part in text.split(","):
        if "-" not in part:
            raise ValueError(f"bad range {part!r}: expected HH:MM-HH:MM")
        start_s, _, end_s = part.strip().partition("-")
        start = parse_time(start_s)
        end = parse_time(end_s, allow_24=True)
        if start == end:
            raise ValueError(
                f"bad range {part!r}: zero-length range is ambiguous; "
                'write "closed" or "00:00-24:00" instead'
            )
        ranges.append((start, end))
    return ranges


def parse_schedule(raw):
    sched = {}
    for key, value in raw.items():
        day = key.strip().lower()
        if day not in DAYS:
            raise ValueError(f"unknown schedule day {key!r}: expected one of {DAYS}")
        sched[day] = parse_day(str(value))
    return sched


_EXC_SPECIFIC_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$", re.ASCII)
_EXC_RECURRING_RE = re.compile(r"^(\d{2})-(\d{2})$", re.ASCII)


def _validate_calendar_date(year, month, day, key, label):
    """Raise a ValueError naming `key`/`label` if (year, month, day) isn't a
    real calendar date. Shared by the specific and recurring exception-key
    branches in parse_exceptions."""
    try:
        date(year, month, day)
    except ValueError:
        raise ValueError(f"bad {label} {key!r}: not a real calendar date") from None


def parse_exceptions(raw):
    """Parse the [storefront.exceptions] table: "YYYY-MM-DD" (specific) or
    "MM-DD" (recurring annually) keys -> the same day-string grammar as the
    weekly schedule. Keys are validated as real calendar dates; "02-29"
    recurring is allowed (matches only in leap years)."""
    out = {}
    for key, value in raw.items():
        k = str(key).strip()
        if m := _EXC_SPECIFIC_RE.match(k):
            y, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            _validate_calendar_date(y, mo, dd, key, "exception date")
            out[(y, mo, dd)] = parse_day(str(value))
        elif m := _EXC_RECURRING_RE.match(k):
            mo, dd = int(m.group(1)), int(m.group(2))
            # 2024 is a leap year, so "02-29" validates
            _validate_calendar_date(2024, mo, dd, key, "recurring exception")
            out[(None, mo, dd)] = parse_day(str(value))
        else:
            raise ValueError(
                f'bad exception key {key!r}: expected "MM-DD" (recurring) '
                'or "YYYY-MM-DD" (specific), zero-padded'
            )
    return out


def fmt_range(r):
    start, end = r
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def ranges_for(schedule, exceptions, d):
    """Effective (ranges, source_label) for calendar date `d`. Precedence:
    specific YYYY-MM-DD exception > recurring MM-DD exception > weekly day.
    An exception REPLACES the day's ranges (no merging)."""
    if exceptions:
        spec = (d.year, d.month, d.day)
        if spec in exceptions:
            return exceptions[spec], f"exception {d.year:04d}-{d.month:02d}-{d.day:02d}"
        rec = (None, d.month, d.day)
        if rec in exceptions:
            return exceptions[rec], f"exception {d.month:02d}-{d.day:02d}"
    day = DAYS[d.weekday()]
    return schedule.get(day, []), day


def evaluate(schedule, now, exceptions=None):
    """Return a reason string ("mon 09:00-17:00", "exception 12-25 ...") if
    `now` is within business hours, else None. A range whose end <= start
    wraps past midnight and BELONGS TO ITS START DAY — so a wrap that starts
    on day D-1 (weekly or exception) still covers early hours of day D, even
    when day D is an exception day."""
    minute = now.hour * 60 + now.minute
    today = now.date()

    ranges, label = ranges_for(schedule, exceptions, today)
    for start, end in ranges:
        if end > start:  # normal same-day range
            if start <= minute < end:
                return f"{label} {fmt_range((start, end))}"
        else:  # wrap: open from start until midnight
            if minute >= start:
                return f"{label} {fmt_range((start, end))}"

    y_ranges, y_label = ranges_for(schedule, exceptions, today - timedelta(days=1))
    for start, end in y_ranges:
        if end <= start and minute < end:  # yesterday's wrap past midnight
            return f"{y_label} {fmt_range((start, end))}"

    return None


def is_open(schedule, now, exceptions=None):
    return evaluate(schedule, now, exceptions) is not None
