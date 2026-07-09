"""Weekly business-hours schedule: parse TOML day strings into minute ranges
and evaluate open/closed against a clock. Pure logic, no rendering."""

import re

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Range = tuple[int, int]

_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")


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


def fmt_range(r):
    start, end = r
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"
