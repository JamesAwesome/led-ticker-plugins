"""Each plugin derives its version from its OWN <plugin>-v* tags (hatch-vcs)."""

import re
from importlib.metadata import version

import pytest

PLUGINS = ["pool", "baseball", "crypto", "calendar", "rss", "weather", "flair", "telnet"]


@pytest.mark.parametrize("name", PLUGINS)
def test_plugin_version_is_vcs_derived(name):
    # After `uv sync`, each plugin is editable-installed with its hatch-vcs
    # version. With git present it must be a real version, not the 0.0.0 fallback.
    v = version(f"led-ticker-{name}")
    assert re.match(r"^\d+\.\d+", v), (name, v)
    assert v != "0.0.0", (name, v)


def test_versions_are_tag_scoped():
    # crypto (crypto-v0.2.x) and pool (pool-v0.1.x) come from different tag
    # lines, so their major.minor must differ — proves --match scoping works
    # (a plugin doesn't pick up another's tags).
    def major_minor(name):
        return tuple(version(f"led-ticker-{name}").split(".")[:2])

    assert major_minor("crypto") != major_minor("pool"), (
        major_minor("crypto"), major_minor("pool"))


def test_no_static_version_in_any_pyproject():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in PLUGINS:
        pp = (root / "plugins" / name / "pyproject.toml").read_text()
        assert 'dynamic = ["version"]' in pp, name
        assert "hatch-vcs" in pp, name
        assert not re.search(r'^version\s*=\s*"', pp, re.MULTILINE), name
