import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.check_release import resolve

DATA = ["pool", "baseball", "crypto", "calendar", "rss", "weather"]
HOMAGE = ["nyancat", "pokeball", "pacman", "sailor_moon"]


def _mk(tmp_path: Path, plugin: str, version: str) -> str:
    d = tmp_path / "plugins" / plugin
    d.mkdir(parents=True)
    (d / "pyproject.toml").write_text(textwrap.dedent(f"""
        [project]
        name = "led-ticker-{plugin}"
        version = "{version}"
    """))
    return str(tmp_path / "plugins")


def test_data_plugin_matching_ok(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("pool-v0.1.0", root)
    assert plugin_dir == str(Path(root) / "pool"), msg


def test_homage_plugin_rejected(tmp_path):
    root = _mk(tmp_path, "nyancat", "0.1.0")
    plugin_dir, msg = resolve("nyancat-v0.1.0", root)
    assert plugin_dir is None
    assert "not published to PyPI" in msg


def test_version_mismatch_rejected(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("pool-v0.2.0", root)
    assert plugin_dir is None
    assert "0.2.0" in msg and "0.1.0" in msg


def test_unknown_plugin_rejected(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("bogus-v1.0.0", root)
    assert plugin_dir is None


def test_malformed_tag_rejected(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("pool0.1.0", root)
    assert plugin_dir is None


def test_cli_exit_codes(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    ok = subprocess.run(
        [sys.executable, "scripts/check_release.py", "pool-v0.1.0", root],
        capture_output=True, text=True)
    bad = subprocess.run(
        [sys.executable, "scripts/check_release.py", "nyancat-v0.1.0", root],
        capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.strip().endswith("pool")
    assert bad.returncode == 1
