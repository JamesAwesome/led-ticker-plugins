"""Resolve a `<plugin>-vX.Y.Z` release tag to a buildable plugin dir.

With hatch-vcs, the git tag IS the version — no static version field in
pyproject.toml to compare against. The resolver checks that the plugin is in
the publishable allowlist and that the plugin directory (with a pyproject.toml)
exists. On success, prints the plugin directory to stdout and exits 0; otherwise
exits 1.
"""

import sys
from pathlib import Path

# Plugins published to PyPI on a `<plugin>-vX.Y.Z` release: the 6 data plugins,
# `flair` (the consolidated homage sprite-trail pack), and `telnet`.
PUBLISHABLE_PLUGINS = {
    "pool",
    "baseball",
    "crypto",
    "calendar",
    "rss",
    "weather",
    "flair",
    "telnet",
    "storefront",
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


def main() -> int:
    tag = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "plugins"
    plugin_dir, msg = resolve(tag, root)
    print(msg, file=sys.stderr)
    if plugin_dir is None:
        return 1
    print(plugin_dir)   # stdout = the dir, for the workflow to consume
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
