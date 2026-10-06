"""Each plugin derives its version from its OWN <plugin>-v* tags (hatch-vcs)."""

import re
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

PLUGINS = [
    "pool",
    "baseball",
    "crypto",
    "calendar",
    "rss",
    "weather",
    "flair",
    "telnet",
]


def _git(*args: str) -> str | None:
    """Run git at the repo root. None if git is missing or the command failed."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _own_tag_versions(name: str) -> list[str]:
    """The X.Y.Z parts of this plugin's own `<name>-v*` tags."""
    out = _git("tag", "--list", f"{name}-v*")
    if out is None:
        pytest.skip("git is unavailable")
    prefix = f"{name}-v"
    return [
        line.removeprefix(prefix)
        for line in out.splitlines()
        if line.startswith(prefix)
    ]


def _next_patch(tag_version: str) -> str:
    """setuptools_scm's guess-next-dev bump: what an untagged commit reports."""
    head, _, last = tag_version.rpartition(".")
    if not head or not last.isdigit():
        return tag_version
    return f"{head}.{int(last) + 1}"


def _release_base(v: str) -> str:
    """Drop hatch-vcs dev/local suffixes: `0.2.1.dev5+g1234abc` -> `0.2.1`."""
    return v.split("+")[0].split(".dev")[0]


@pytest.mark.parametrize("name", PLUGINS)
def test_plugin_version_is_vcs_derived(name):
    # After `uv sync`, each plugin is editable-installed with its hatch-vcs
    # version. With git present it must be a real version, not the 0.0.0 fallback.
    v = version(f"led-ticker-{name}")
    assert re.match(r"^\d+\.\d+", v), (name, v)
    assert v != "0.0.0", (name, v)


@pytest.mark.parametrize("name", PLUGINS)
def test_versions_are_tag_scoped(name):
    # Every plugin scopes hatch-vcs with `git describe --match "<name>-v*"`, so
    # its installed version must trace back to one of its OWN tags and never to
    # another plugin's. This used to be checked by asserting crypto's and pool's
    # major.minor differed — a proxy that died the moment pool-v0.2.0 shipped and
    # put both on 0.2.x. Two plugins sharing a version number is legal, so check
    # the real property instead: compare the installed version against this
    # plugin's actual tag list. Dropping --match from a pyproject makes that
    # plugin report the repo's newest tag (whatever plugin it belongs to), which
    # is exactly what these assertions catch.
    own = _own_tag_versions(name)
    if not own:
        pytest.skip(f"no {name}-v* tags in this checkout")

    installed = version(f"led-ticker-{name}")
    base = _release_base(installed)

    # On a tagged commit hatch-vcs reports the tag verbatim; on any commit after
    # one it reports the next patch plus a `.devN+g<sha>` suffix.
    allowed = set(own) | {_next_patch(t) for t in own}
    assert base in allowed, (
        f"led-ticker-{name}=={installed} does not correspond to any {name}-v* "
        f"tag (own tags: {sorted(own)}) — is --match missing from "
        f"plugins/{name}/pyproject.toml?"
    )

    # Pin it to the NEAREST own tag too, so a version can't pass by coinciding
    # with some other plugin's tag number.
    nearest = _git("describe", "--tags", "--abbrev=0", "--match", f"{name}-v*")
    if not nearest:
        pytest.skip(f"no {name}-v* tag reachable from HEAD")
    nearest_version = nearest.removeprefix(f"{name}-v")
    expected = _next_patch(nearest_version) if ".dev" in installed else nearest_version
    assert base == expected, (
        f"led-ticker-{name}=={installed} should derive from the nearest "
        f"{name}-v* tag ({nearest}) and so report base {expected}, not {base}"
    )


def test_no_static_version_in_any_pyproject():
    for name in PLUGINS:
        pp = (REPO_ROOT / "plugins" / name / "pyproject.toml").read_text()
        assert 'dynamic = ["version"]' in pp, name
        assert "hatch-vcs" in pp, name
        assert not re.search(r'^version\s*=\s*"', pp, re.MULTILINE), name
