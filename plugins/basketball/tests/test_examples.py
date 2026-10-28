"""The shipped example configs stay valid, on-brand and documented."""

import tomllib
from pathlib import Path

import attrs
import pytest

from led_ticker_basketball.scores import BasketballScoreMonitor

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("config.basketball-*.toml"))
SIGNS = ("smallsign", "bigsign", "longboi")
# Handed to the widget by the engine or runtime-only; not user config.
_NOT_USER_FACING = {"session", "feed_stories"}


def _widgets(path: Path) -> list[dict]:
    cfg = tomllib.loads(path.read_text())
    return [
        w
        for section in cfg["playlist"]["section"]
        for w in section["widget"]
        if w["type"] == "basketball.scores"
    ]


def test_all_six_examples_exist():
    names = {p.name for p in EXAMPLES}
    assert names == {
        f"config.basketball-{kind}.{sign}.toml"
        for kind in ("demo", "live")
        for sign in SIGNS
    }


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_examples_validate(path):
    widgets = _widgets(path)
    assert widgets
    for w in widgets:
        cfg = {k: v for k, v in w.items() if k != "type"}
        assert BasketballScoreMonitor.validate_config(cfg) == []


@pytest.mark.parametrize(
    "path", [p for p in EXAMPLES if "-live." in p.name], ids=lambda p: p.name
)
def test_examples_use_example_teams(path):
    for w in _widgets(path):
        assert w["teams"] == ["PHI", "NY"]


def test_readme_lists_every_option():
    readme = (ROOT / "README.md").read_text()
    fields = [
        f.name
        for f in attrs.fields(BasketballScoreMonitor)
        if not f.name.startswith("_") and f.name not in _NOT_USER_FACING
    ]
    assert "teams" in fields
    missing = [n for n in [*fields, "update_interval"] if f"| `{n}` |" not in readme]
    assert missing == []


def test_readme_states_small_font_is_rejected():
    readme = (ROOT / "README.md").read_text()
    assert "`small_font`" in readme
    assert "not accepted" in readme
    assert BasketballScoreMonitor.validate_config(
        {"teams": ["PHI"], "small_font": "5x8"}
    )
