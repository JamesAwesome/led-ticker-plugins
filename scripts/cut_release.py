#!/usr/bin/env python3
"""Cut a plugin release the safe way: derive vNext from the LIVE remote at
execution time, guard the ordering, then `gh release create` on origin/main.

    uv run python scripts/cut_release.py <plugin> <patch|minor|major> \
        --notes FILE [--title T]

Exists because a stale "vNext" carried in a plan once cut an out-of-order
core release (v4.16.1 after v4.17.0, 2026-07-16). The version base here is
always the tag list as of NOW; the same ordering check publish.yml enforces
(check_release.check_release_order) runs before the release is created.
"""

import argparse
import subprocess
import sys

from check_release import PUBLISHABLE_PLUGINS, _parse_family, check_release_order


def compute_next(plugin: str, existing_tags: list[str], bump: str) -> str:
    """Pure: the next <plugin>-vX.Y.Z after the plugin's highest existing tag."""
    versioned = [
        v for t in existing_tags if (v := _parse_family(t, plugin)) is not None
    ]
    if not versioned:
        return f"{plugin}-v0.1.0"
    major, minor, patch = max(versioned)
    if bump == "major":
        return f"{plugin}-v{major + 1}.0.0"
    if bump == "minor":
        return f"{plugin}-v{major}.{minor + 1}.0"
    return f"{plugin}-v{major}.{minor}.{patch + 1}"


def _run(*cmd: str) -> str:
    return subprocess.run(
        list(cmd), capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plugin", choices=sorted(PUBLISHABLE_PLUGINS))
    ap.add_argument("bump", choices=["patch", "minor", "major"])
    ap.add_argument("--notes", required=True)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    _run("git", "fetch", "origin", "--tags", "--quiet")
    tags = _run("git", "tag", "-l").split()
    tag = compute_next(args.plugin, tags, args.bump)
    sha = _run("git", "rev-parse", "origin/main")

    def is_ancestor(a: str, b_tag: str) -> bool:
        target = sha if b_tag == tag else b_tag
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", a, target],
                capture_output=True,
            ).returncode
            == 0
        )

    err = check_release_order(tag, tags, is_ancestor)
    if err:
        print(f"refusing to cut: {err}", file=sys.stderr)
        return 1

    version = tag.rpartition("-v")[2]
    title = args.title or f"led-ticker-{args.plugin} {version}"
    url = _run(
        "gh",
        "release",
        "create",
        tag,
        "--target",
        sha,
        "--title",
        title,
        "--notes-file",
        args.notes,
    )
    print(f"{tag} cut on {sha[:9]}: {url or '(created)'}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0] or ".")
    sys.exit(main())
