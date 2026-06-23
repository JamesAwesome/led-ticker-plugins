# led-ticker-plugins

The official first-party plugin pack for [led-ticker](https://github.com/JamesAwesome/led-ticker),
developed together in one uv workspace and **distributed per-plugin** so you
install only what you want.

## Install one plugin

The **data plugins** (`pool`, `baseball`, `crypto`, `calendar`, `rss`, `weather`) are published to PyPI:

```bash
pip install led-ticker-<name>   # e.g. pip install led-ticker-baseball
```

The **homage plugins** (all four sprite-trail families: `nyancat`, `pokeball`, `pacman`, `sailor_moon`) ship together as **`led-ticker-flair`** — not on PyPI, install from source:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair"
```

## Develop

```bash
make dev    # uv sync the whole workspace (needs a sibling ../led-ticker checkout)
make test   # pytest every member
make lint   # ruff + pyright
```

Each plugin lives under `plugins/<name>/` with its own `pyproject.toml`,
version, `CLAUDE.md`, and `README.md`. See
`docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

## Third-party homages

The `led-ticker-flair` pack (`nyancat`, `pokeball`, `pacman`, `sailor_moon`)
contains **unofficial fan homages** — the character names/designs and any bundled
sprite artwork belong to their respective owners and are **not** covered by this
project's license. See [NOTICE.md](NOTICE.md) for details. The data plugins
(`pool`, `baseball`, `crypto`, `calendar`, `rss`, `weather`) are original
works.

## License

[MIT](LICENSE) © James Awesome — applies to the plugin **code**. The third-party
characters/artwork referenced by the sprite-trail homage plugins are **not**
covered by it; see [NOTICE.md](NOTICE.md).
