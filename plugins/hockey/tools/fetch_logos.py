"""Download the 32 NHL team logos from ESPN's CDN into the package assets.

Run from ``plugins/hockey/``:  ``uv run python tools/fetch_logos.py``.
Not part of the package; needs network + Pillow.
"""

import argparse
import datetime
import io
import sys
import urllib.request
from pathlib import Path

from PIL import Image

from led_ticker_hockey.teams import NHL_TEAMS

URL = "https://a.espncdn.com/i/teamlogos/nhl/500/{slug}.png"
UA = "Mozilla/5.0 led-ticker-hockey-tools"
DEFAULT_OUT = "src/led_ticker_hockey/assets/logos"
# NHL API abbreviation -> ESPN CDN slug, where they differ.
ESPN_SLUG = {"LAK": "la", "NJD": "nj", "SJS": "sj", "TBL": "tb", "UTA": "utah"}


def fetch(abbrev: str, out: Path) -> str:
    url = URL.format(slug=ESPN_SLUG.get(abbrev, abbrev.lower()))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img.thumbnail((64, 64), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    canvas.paste(img, ((64 - img.width) // 2, (64 - img.height) // 2))
    canvas.save(out / f"{abbrev}.png")
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    lines, failed = [], []
    for abbrev in sorted(NHL_TEAMS):
        try:
            url = fetch(abbrev, out)
        except Exception as exc:  # noqa: BLE001 - report every failure at the end
            failed.append(f"{abbrev}: {exc}")
            continue
        lines.append(f"{abbrev}\t{url}\t{today}")
        print(f"ok {abbrev}")
    (out / "MANIFEST.txt").write_text(
        "# ABBREV\tsource url\tfetched\n" + "\n".join(lines) + "\n"
    )
    if failed:
        print("FAILED:\n  " + "\n  ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
