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
    # The CLI now also enforces the release ORDER guard against the real
    # repo's tags, so the happy path must use a tag that actually exists
    # and is its family's latest (well-ordered by construction): the
    # current latest pool-v* tag. A synthetic pool-v0.1.0 is correctly
    # REJECTED once newer pool releases exist.
    latest_pool = subprocess.run(
        ["git", "tag", "-l", "pool-v*"], capture_output=True, text=True
    ).stdout.split()
    latest_pool = sorted(
        latest_pool, key=lambda t: tuple(map(int, t.rpartition("-v")[2].split(".")))
    )[-1]
    root = _mk(tmp_path, "pool")
    ok = subprocess.run(
        [sys.executable, "scripts/check_release.py", latest_pool, root],
        capture_output=True, text=True)
    bad = subprocess.run(
        [sys.executable, "scripts/check_release.py", "bogus-v1.0.0", root],
        capture_output=True, text=True)
    stale = subprocess.run(
        [sys.executable, "scripts/check_release.py", "pool-v0.0.1", root],
        capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.strip().endswith("pool"), ok.stderr
    assert bad.returncode == 1
    assert stale.returncode == 1 and "order" in stale.stderr


# --- Release order guard (v4.16.1/v4.17.0 core incident, 2026-07-16) -------

from scripts.check_release import check_release_order


def _ancestry(pairs):
    def is_ancestor(a, b):
        return (a, b) in pairs

    return is_ancestor


def test_order_ok_newer_version_newer_commit():
    err = check_release_order(
        "stocks-v0.7.0",
        ["stocks-v0.6.2", "flair-v0.9.0"],
        _ancestry({("stocks-v0.6.2", "stocks-v0.7.0")}),
    )
    assert err is None


def test_order_incident_lower_version_fails():
    err = check_release_order(
        "stocks-v0.6.1", ["stocks-v0.6.2"], _ancestry(set())
    )
    assert err is not None and "0.6.2" in err


def test_order_mirror_higher_version_older_commit_fails():
    err = check_release_order(
        "stocks-v0.7.0", ["stocks-v0.6.2"], _ancestry(set())
    )
    assert err is not None and "ancestor" in err


def test_order_is_family_scoped():
    """Another plugin's higher tags must not constrain this plugin —
    stocks-v0.7.0 is fine even though flair is at v9.9.9."""
    err = check_release_order(
        "stocks-v0.7.0",
        ["stocks-v0.6.2", "flair-v9.9.9", "weather-v3.0.0"],
        _ancestry({("stocks-v0.6.2", "stocks-v0.7.0")}),
    )
    assert err is None


def test_order_first_release_of_a_plugin_passes():
    err = check_release_order("newplug-v0.1.0", ["stocks-v0.6.2"], _ancestry(set()))
    assert err is None


def test_cut_release_compute_next_is_family_scoped():
    import importlib.util
    import sys as _sys
    from pathlib import Path as _P

    _sys.path.insert(0, str(_P("scripts").resolve()))
    spec = importlib.util.spec_from_file_location(
        "cut_release", _P("scripts/cut_release.py")
    )
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    tags = ["stocks-v0.6.2", "flair-v0.7.1", "junk"]
    assert cr.compute_next("stocks", tags, "minor") == "stocks-v0.7.0"
    assert cr.compute_next("flair", tags, "patch") == "flair-v0.7.2"
    assert cr.compute_next("telnet", tags, "patch") == "telnet-v0.1.0"
