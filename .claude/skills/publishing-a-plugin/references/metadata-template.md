# Plugin pyproject metadata template (the `audit` gate)

The house template every `plugins/<name>/pyproject.toml` `[project]` block is checked against. Drift is **fix-and-ask** — show the user the diff and the rule, don't silently rewrite. `crypto`'s pyproject is the living reference.

## `[project.urls]` — exactly these 5, in order

```toml
[project.urls]
Homepage = "https://docs.ledticker.dev"
Documentation = "https://docs.ledticker.dev/plugins/"
Repository = "https://github.com/JamesAwesome/led-ticker-plugins"
Issues = "https://github.com/JamesAwesome/led-ticker-plugins/issues"
Changelog = "https://github.com/JamesAwesome/led-ticker-plugins/releases"
```
PyPI renders these as sidebar links — a missing block (flair once had none) means a bare project page.

## `classifiers` — exactly these 9

```toml
classifiers = [
    "Development Status :: 4 - Beta",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.14",
    "Operating System :: POSIX :: Linux",
    "Topic :: Multimedia :: Graphics",
    "Topic :: System :: Hardware",
    "Framework :: AsyncIO",
    "Intended Audience :: Developers",
]
```
**`Development Status` is the ONE line allowed to differ** — it should reflect real maturity (`3 - Alpha` for a young plugin like telnet, `4 - Beta` for the rest). PyPI facets by the license + status classifiers, so keep the other 8 identical everywhere.

## `keywords` — common prefix + domain terms

Every plugin starts with these 5, then adds real domain terms (don't pad with junk):
```toml
keywords = [
    "led-ticker", "led-ticker-plugin", "raspberry-pi", "led-matrix", "rgb-led-matrix",
    # + domain, e.g. stocks: "stocks", "equities", "finnhub", "ticker"
    #              flair:  "transitions", "animation", "lottery", "fireworks", "fisheye"
]
```

## Other `[project]` fields
- `description` — one accurate line (shows under the name in PyPI search). Verify it still matches what the plugin actually does (flair's drifted stale once — listed only some of its effects).
- `readme = "README.md"` — must exist and be usable as the PyPI long description.
- `name`, `license = "MIT"`, `license-files`, `requires-python = ">=3.14"`, `authors` — consistent across plugins.
- Never touch `dynamic = ["version"]` / `[tool.hatch.version]` — versions are tag-driven.

## Machine spot-check
Every plugin should print `5 9`:
```bash
uv run python -c "import tomllib,glob; [print(f, len(tomllib.load(open(f,'rb'))['project']['urls']), len(tomllib.load(open(f,'rb'))['project']['classifiers'])) for f in sorted(glob.glob('plugins/*/pyproject.toml'))]"
```
That only catches count drift — still read the actual url names, classifier strings, keyword prefix, and description by eye against the above.
