"""README "Display fonts" section stays in step with the shipped example
(docs-parity rule: the snippet is copied verbatim from the demo TOML) and
the example fails validation the way a user would see it when `font_size`
is missing."""

import asyncio
import re
from pathlib import Path

from led_ticker import _plugin_loader as L
from led_ticker.validate import validate_config

_FLAIR = Path(__file__).parent.parent
_README = (_FLAIR / "README.md").read_text()
_EXAMPLE = (_FLAIR / "examples" / "config.display-fonts.bigsign.toml").read_text()
_NAMES = (
    "flair.BungeeShade",
    "flair.BungeeOutline",
    "flair.LondrinaShadow",
    "flair.LondrinaOutline",
)


def _section() -> str:
    assert "## Display fonts" in _README, "README has no Display fonts section"
    return _README.split("## Display fonts", 1)[1].split("\n## ", 1)[0]


def _readme_snippet() -> str:
    m = re.search(r"```toml\n(.*?)```", _section(), re.S)
    assert m, "README Display fonts section has no toml snippet"
    return m.group(1)


def test_readme_snippet_is_verbatim_from_the_example():
    assert _readme_snippet() in _EXAMPLE


def test_readme_table_lists_every_font_once():
    section = _section()
    for name in _NAMES:
        assert section.count(f"`{name}`") >= 1, name


def test_example_without_font_size_fails_rule_5(tmp_path):
    broken = tmp_path / "c.toml"
    broken.write_text(_EXAMPLE.replace("font_size = 46\n", "", 1))
    L.reset_plugins()
    try:
        L.load_plugins_for_config(broken)
        result = asyncio.run(validate_config(broken))
    finally:
        L.reset_plugins()
    assert any(
        e.rule == 5 and "flair.BungeeShade" in e.message for e in result.errors
    ), result.errors
