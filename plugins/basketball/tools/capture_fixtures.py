"""Capture trimmed ESPN scoreboard + PHI schedule fixtures.

Run from ``plugins/basketball/``:
``uv run python tools/capture_fixtures.py [--date YYYYMMDD] --out tests/fixtures``.
Raw payloads are also saved under ``<out>/raw/`` (gitignored). Not part of the
package; needs network.
"""

import argparse
import datetime
import json
import sys
import urllib.request
from pathlib import Path

HOST = "https://site.api.espn.com"
PATH = "/apis/site/v2/sports/basketball/nba"
UA = "Mozilla/5.0 led-ticker-basketball-tools"
EVENT_KEYS = ("id", "date", "shortName", "season", "status")
COMP_KEYS = (
    "competitors",
    "venue",
    "broadcasts",
    "neutralSite",
    "status",
)


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _trim_event(ev: dict) -> dict:
    out = {k: ev[k] for k in EVENT_KEYS if k in ev}
    comp = (ev.get("competitions") or [{}])[0]
    out["competitions"] = [{k: comp[k] for k in COMP_KEYS if k in comp}]
    return out


def trim_scoreboard(data: dict) -> dict:
    picked, seen, have_ot = [], set(), False
    for ev in data.get("events", []):
        state = ev.get("status", {}).get("type", {}).get("state")
        period = ev.get("status", {}).get("period", 0) or 0
        if state == "post" and period > 4 and not have_ot:
            have_ot = True
            picked.append(ev)
        elif state in ("pre", "in", "post") and state not in seen:
            seen.add(state)
            picked.append(ev)
    out = {k: v for k, v in data.items() if k != "events"}
    out["events"] = [_trim_event(e) for e in picked]
    return out


def trim_schedule(data: dict) -> dict:
    out = {k: data[k] for k in ("team", "season") if k in data}
    out["events"] = data.get("events", [])[:6]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="YYYYMMDD (default: today's scoreboard)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    url = f"{HOST}{PATH}/scoreboard" + (f"?dates={args.date}" if args.date else "")
    board = get(url)
    stamp = args.date or datetime.date.today().strftime("%Y%m%d")
    (raw / f"scoreboard_{stamp}.json").write_text(json.dumps(board, indent=2))
    (out / f"scoreboard_{stamp}.json").write_text(
        json.dumps(trim_scoreboard(board), indent=2)
    )

    sched = get(f"{HOST}{PATH}/teams/PHI/schedule")
    (raw / "schedule_phi.json").write_text(json.dumps(sched, indent=2))
    (out / "schedule_phi.json").write_text(json.dumps(trim_schedule(sched), indent=2))
    print(f"wrote scoreboard_{stamp}.json and schedule_phi.json to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
