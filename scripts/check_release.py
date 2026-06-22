"""Resolve a `<plugin>-vX.Y.Z` release tag to a buildable plugin dir.

Allows only the 6 DATA plugins; rejects homage plugins (GitHub-only) and any
tag whose version doesn't match the plugin's pyproject version. On success,
prints the plugin directory to stdout and exits 0; otherwise exits 1.
"""

import sys
import tomllib
from pathlib import Path

DATA_PLUGINS = {"pool", "baseball", "crypto", "calendar", "rss", "weather"}
HOMAGE_PLUGINS = {"nyancat", "pokeball", "pacman", "sailor_moon"}


def resolve(tag: str, plugins_root: str = "plugins") -> tuple[str | None, str]:
    if "-v" not in tag:
        return None, f"Tag {tag!r} is malformed (expected <plugin>-vX.Y.Z)."
    plugin, _, version = tag.rpartition("-v")
    if plugin in HOMAGE_PLUGINS:
        return None, (
            f"Plugin {plugin!r} is GitHub-install-only and is not published to PyPI."
        )
    if plugin not in DATA_PLUGINS:
        return None, f"Unknown plugin {plugin!r} (not in the publishable set)."
    plugin_dir = Path(plugins_root) / plugin
    pyproject = plugin_dir / "pyproject.toml"
    if not pyproject.exists():
        return None, f"No pyproject at {pyproject}."
    with open(pyproject, "rb") as f:
        pp_version = tomllib.load(f)["project"]["version"]
    if version != pp_version:
        return None, (
            f"Tag {tag!r} (version {version}) does not match {plugin} pyproject "
            f"version {pp_version!r}. Bump the version or fix the tag."
        )
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
