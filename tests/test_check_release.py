import subprocess
import sys
from pathlib import Path

from scripts.check_release import resolve

PUBLISHABLE = ["pool", "baseball", "crypto", "calendar", "rss", "weather", "flair", "telnet"]


def _mk(tmp_path: Path, plugin: str) -> str:
    d = tmp_path / "plugins" / plugin
    d.mkdir(parents=True)
    (d / "pyproject.toml").write_text('[project]\nname = "led-ticker-%s"\n' % plugin)
    return str(tmp_path / "plugins")


def test_data_plugin_matching_ok(tmp_path):
    root = _mk(tmp_path, "pool")
    plugin_dir, msg = resolve("pool-v0.1.0", root)
    assert plugin_dir == str(Path(root) / "pool"), msg


def test_flair_is_publishable(tmp_path):
    # flair (the consolidated homage pack) ships to PyPI, like the data plugins.
    root = _mk(tmp_path, "flair")
    plugin_dir, msg = resolve("flair-v0.1.0", root)
    assert plugin_dir == str(Path(root) / "flair"), msg


def test_telnet_is_publishable(tmp_path):
    root = _mk(tmp_path, "telnet")
    plugin_dir, msg = resolve("telnet-v0.1.0", root)
    assert plugin_dir == str(Path(root) / "telnet"), msg


def test_unknown_plugin_rejected(tmp_path):
    root = _mk(tmp_path, "telnet")
    plugin_dir, msg = resolve("bogus-v1.0.0", root)
    assert plugin_dir is None


def test_malformed_tag_rejected(tmp_path):
    root = _mk(tmp_path, "pool")
    plugin_dir, msg = resolve("pool0.1.0", root)
    assert plugin_dir is None


def test_cli_exit_codes(tmp_path):
    root = _mk(tmp_path, "pool")
    ok = subprocess.run(
        [sys.executable, "scripts/check_release.py", "pool-v0.1.0", root],
        capture_output=True, text=True)
    bad = subprocess.run(
        [sys.executable, "scripts/check_release.py", "bogus-v1.0.0", root],
        capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.strip().endswith("pool")
    assert bad.returncode == 1
