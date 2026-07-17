"""Resolve a `<plugin>-vX.Y.Z` release tag to a buildable plugin dir.

With hatch-vcs, the git tag IS the version — no static version field in
pyproject.toml to compare against. The resolver checks that the plugin is in
the publishable allowlist and that the plugin directory (with a pyproject.toml)
exists. On success, prints the plugin directory to stdout and exits 0; otherwise
exits 1.

Also enforces the RELEASE ORDER guard (v4.16.1/v4.17.0 core incident,
2026-07-16): within a plugin's own `<plugin>-v*` tag family, version order
must equal commit-ancestry order — the new tag must be strictly greater
than every released version of THAT plugin AND descend from the previous
latest. Trunk-only; no backport escape hatch. Prefer cutting releases with
scripts/cut_release.py, which derives vNext from the live remote and runs
this same check first.
"""

import re
import subprocess
import sys
from pathlib import Path

# Plugins published to PyPI on a `<plugin>-vX.Y.Z` release: the 6 data plugins,
# `flair` (the consolidated homage sprite-trail pack), `telnet`, `storefront`,
# `flight`, and `stocks`.
PUBLISHABLE_PLUGINS = {
    "pool",
    "baseball",
    "crypto",
    "calendar",
    "rss",
    "weather",
    "flair",
    "flight",
    "telnet",
    "storefront",
    "stocks",
}


def resolve(tag: str, plugins_root: str = "plugins") -> tuple[str | None, str]:
    if "-v" not in tag:
        return None, f"Tag {tag!r} is malformed (expected <plugin>-vX.Y.Z)."
    plugin, _, version = tag.rpartition("-v")
    if plugin not in PUBLISHABLE_PLUGINS:
        return None, f"Unknown plugin {plugin!r} (not in the publishable set)."
    plugin_dir = Path(plugins_root) / plugin
    pyproject = plugin_dir / "pyproject.toml"
    if not pyproject.exists():
        return None, f"No pyproject at {pyproject}."
    return str(plugin_dir), f"OK: {tag} -> {plugin_dir} (version {version})."


_FAMILY_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _parse_family(tag: str, plugin: str) -> tuple[int, int, int] | None:
    prefix = f"{plugin}-v"
    if not tag.startswith(prefix):
        return None
    m = _FAMILY_VERSION_RE.match(tag[len(prefix) :])
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def check_release_order(new_tag, existing_tags, is_ancestor):
    """Pure order guard, scoped to the new tag's own plugin family.

    Returns None when well-ordered, else a failure reason. Malformed or
    other-family tags in `existing_tags` are ignored; a malformed NEW tag
    is rejected (resolve() already screens most of that)."""
    plugin, _, _ = new_tag.rpartition("-v")
    new_v = _parse_family(new_tag, plugin)
    if new_v is None:
        return f"tag {new_tag!r} is not a plain <plugin>-vX.Y.Z release tag"
    versioned = [
        (v, t)
        for t in existing_tags
        if t != new_tag and (v := _parse_family(t, plugin)) is not None
    ]
    if not versioned:
        return None  # first release of this plugin
    prev_v, prev_tag = max(versioned)
    if new_v <= prev_v:
        return (
            f"version out of order: {new_tag} is not greater than the latest "
            f"existing {prev_tag} — cut the next version on the current main tip"
        )
    if not is_ancestor(prev_tag, new_tag):
        return (
            f"history out of order: {prev_tag} is not an ancestor of "
            f"{new_tag}'s commit — a higher version must ship newer code"
        )
    return None


def _git_is_ancestor(a: str, b: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", a, b],
            capture_output=True,
        ).returncode
        == 0
    )


def main() -> int:
    tag = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "plugins"
    plugin_dir, msg = resolve(tag, root)
    print(msg, file=sys.stderr)
    if plugin_dir is None:
        return 1
    all_tags = subprocess.run(
        ["git", "tag", "-l"], capture_output=True, text=True, check=True
    ).stdout.split()
    order_err = check_release_order(tag, all_tags, _git_is_ancestor)
    if order_err:
        print(f"::error::release order guard: {order_err}", file=sys.stderr)
        return 1
    print(plugin_dir)  # stdout = the dir, for the workflow to consume
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
