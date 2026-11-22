# Flair display fonts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship four OFL display fonts (Bungee Shade, Bungee Outline, Londrina Shadow, Londrina Outline) inside the flair plugin, registered as `flair.<Name>` with a plugin-declared default `font_threshold` of 45.

**Architecture:** The TTFs and their licences live under `src/led_ticker_flair/flair/fonts/` (the flair plugin root is `led_ticker_flair/flair/`, so `api.font` paths are `fonts/<file>`). One new module, `display_fonts.py`, holds the name→file table and a `register_display_fonts(api)` that uses the three-arg `api.font(..., threshold=45)` on core API `(1, 3)` and falls back to the two-arg form plus one warning on an older core. A demo config, a README section with a GIF, a CLAUDE.md invariant and a packaging test complete it.

**Tech Stack:** Python 3.14, led-ticker plugin API `(1, 3)` (`api.font(name, path, threshold=None)`, `default_threshold`, `resolve_font`, `list_available_hires_fonts` via `led_ticker.plugin`), hatchling (non-Python files under `packages` ship automatically; sprites prove it), pytest, core's `tools/render_demo/render.py` for the GIF.

**Spec:** `../led-ticker/docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md` (section "Flair"; the "Core" section shipped as led-ticker #551 / v4.35.0). Antagonist ledger for the core half: `../led-ticker/docs/superpowers/reviews/2026-11-20-plugin-font-thresholds-antagonist.md`.

## Global Constraints

- Core floor: `led-ticker-core>=4.35` (v4.35.0 carries API `(1, 3)`; confirm `pip index versions led-ticker-core` lists 4.35.0 before the lock step in Task 2, and co-dev against the core checkout with `uv pip install --no-deps -e ../led-ticker` + `uv run --no-sync` until it does).
- Names drop `-Regular`: `flair.BungeeShade`, `flair.BungeeOutline`, `flair.LondrinaShadow`, `flair.LondrinaOutline`. No look-based aliases.
- One threshold for all four: `45`.
- Font files are the unmodified google/fonts TTFs; sha256 (verify on copy):
  - `BungeeShade-Regular.ttf` `665c626082682b462f4e696308eafa7071c114da8f8ff3fb73a289c7ff7df482`
  - `BungeeOutline-Regular.ttf` `9232000ff85fdbb68987007305f2de877486d63d31450f81b403461bbe721f1f`
  - `LondrinaShadow-Regular.ttf` `bdc4a66213c2bed3a0e58912bb2e47f7b0ea51b07d291a43896eed5c87e01a21`
  - `LondrinaOutline-Regular.ttf` `773c655bc6a2e9b699cfa8c4a5f615c6348686d018281bb8e6cdc470b2f05f4d`
- One licence file per family dir, copied unmodified from google/fonts `ofl/{bungeeshade,bungeeoutline,londrinashadow,londrinaoutline}/OFL.txt`; the commit each came from recorded in `SOURCES.md`.
- Plugins import only from `led_ticker.plugin`; no `from __future__ import annotations`.
- Old-core fallback: two-arg `api.font` plus exactly ONE `logger.warning` on logger `led_ticker_flair` (not one per font).
- Bigsign only: the README says "scale 4; unreadable on 16-row signs"; no scale-1 warning in code.
- Docs parity: the README config snippet must match the demo TOML verbatim (pinned by a test).
- Version: no file bump; flair releases by tag `flair-v0.25.0`, cut only on James's go.

## Review Focus

1. A `message` using `flair.BungeeShade` with no `font_size` → `led-ticker validate` reports rule 5 naming the font (core's hi-res listing now includes plugin fonts). Pinned in Task 3 (`test_example_without_font_size_fails_rule_5`).
2. Older core (API `(1, 2)`) → the fonts still register and render at 128, and the log carries one warning, not four. Pinned in Task 2 (`test_old_core_registers_two_arg_and_warns_once`).
3. A sign that also has `config/fonts/BungeeShade-Regular.ttf` (moonbunny does) → both `BungeeShade-Regular` (user, threshold 128) and `flair.BungeeShade` (plugin, 45) exist and do not collide. Pinned in Task 2 (`test_plugin_names_are_namespaced_and_do_not_shadow_user_stems`).
4. A `two_row` or image two-row with these fonts at the README sizes → the row band (32 real px at scale 4) is smaller than the glyph line height, so core raises at draw time / rule 71 refuses. The README states "`message` only at these sizes" (Task 3); no new code.
5. The wheel must carry the fonts and licences. Pinned in Task 1 (`test_display_fonts_and_licences_present` with sha256) plus a one-time `uv build` listing check in Task 1 step 6.

---

### Task 1: Font assets, licences, SOURCES.md, packaging test

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/fonts/BungeeShade-Regular.ttf`, `BungeeOutline-Regular.ttf`, `LondrinaShadow-Regular.ttf`, `LondrinaOutline-Regular.ttf`
- Create: `plugins/flair/src/led_ticker_flair/flair/fonts/OFL-BungeeShade.txt`, `OFL-BungeeOutline.txt`, `OFL-LondrinaShadow.txt`, `OFL-LondrinaOutline.txt`
- Create: `plugins/flair/src/led_ticker_flair/flair/fonts/SOURCES.md`
- Modify: `plugins/flair/tests/test_packaging.py`

**Interfaces:**
- Produces: the directory `led_ticker_flair/flair/fonts/` with the four TTF basenames above (Task 2 registers them by these exact basenames).

- [ ] **Step 1: Write the failing test** (append to `tests/test_packaging.py`)

```python
import hashlib
import led_ticker_flair.flair

_FONT_SHA256 = {
    "BungeeShade-Regular.ttf": "665c626082682b462f4e696308eafa7071c114da8f8ff3fb73a289c7ff7df482",
    "BungeeOutline-Regular.ttf": "9232000ff85fdbb68987007305f2de877486d63d31450f81b403461bbe721f1f",
    "LondrinaShadow-Regular.ttf": "bdc4a66213c2bed3a0e58912bb2e47f7b0ea51b07d291a43896eed5c87e01a21",
    "LondrinaOutline-Regular.ttf": "773c655bc6a2e9b699cfa8c4a5f615c6348686d018281bb8e6cdc470b2f05f4d",
}


def _fonts() -> Path:
    return Path(led_ticker_flair.flair.__file__).resolve().parent / "fonts"


def test_display_fonts_and_licences_present():
    d = _fonts()
    for name, digest in _FONT_SHA256.items():
        assert (d / name).is_file(), f"missing {name}"
        assert hashlib.sha256((d / name).read_bytes()).hexdigest() == digest, name
    for fam in ("BungeeShade", "BungeeOutline", "LondrinaShadow", "LondrinaOutline"):
        lic = d / f"OFL-{fam}.txt"
        assert lic.is_file(), f"missing {lic.name}"
        assert "SIL OPEN FONT LICENSE" in lic.read_text(encoding="utf-8")
    assert "google/fonts" in (d / "SOURCES.md").read_text()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest plugins/flair/tests/test_packaging.py -q`
Expected: FAIL with `missing BungeeShade-Regular.ttf`

- [ ] **Step 3: Copy the TTFs and verify hashes**

The four files are at `/private/tmp/claude-501/-Users-james-projects-github-jamesawesome-led-ticker/c6556a8c-18eb-466f-96b1-87a68aa284aa/scratchpad/fonts/` (also on moonbunny at `~/led-ticker/config/fonts/`). Copy them into `fonts/` and run `shasum -a 256` on the copies; every digest must equal the Global Constraints table. Any mismatch: stop and re-fetch from google/fonts main via `gh api repos/google/fonts/contents/ofl/<dir>/<file> -H "Accept: application/vnd.github.raw"` (curl is denied in this environment; `gh api` is not).

- [ ] **Step 4: Fetch the licences and write SOURCES.md**

For each `<dir>` in `bungeeshade bungeeoutline londrinashadow londrinaoutline`:
`gh api repos/google/fonts/contents/ofl/<dir>/OFL.txt -H "Accept: application/vnd.github.raw" > fonts/OFL-<Family>.txt`
and `gh api "repos/google/fonts/commits?path=ofl/<dir>&per_page=1" --jq '.[0].sha'` for the commit. `SOURCES.md` has one table: family, google/fonts dir, TTF basename, sha256, commit sha, fetch date (2026-11-19 for the TTFs; today for the licences), plus one line: "Files are unmodified. Licence: SIL OFL 1.1 (see the OFL-*.txt beside each family)."

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest plugins/flair/tests/test_packaging.py -q`
Expected: PASS

- [ ] **Step 6: Prove the wheel carries them (one-time check, not a test)**

Run: `uv build --wheel plugins/flair -o /tmp/flair-wheel && unzip -l /tmp/flair-wheel/*.whl | grep -c "flair/fonts/"`
Expected: `9` (four TTFs, four licences, SOURCES.md). Ruling if the count differs: hatch's `packages = ["src/led_ticker_flair"]` must be including the dir; fix packaging before Task 2, not after.

- [ ] **Step 7: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/fonts plugins/flair/tests/test_packaging.py
git commit -m "feat(flair): bundle Bungee Shade/Outline and Londrina Shadow/Outline (OFL) with licences and sources"
```

---

### Task 2: Register the fonts with threshold 45, old-core fallback, core floor

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/display_fonts.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (`register`, module docstring)
- Modify: `plugins/flair/pyproject.toml` (`led-ticker-core>=4.35`), `uv.lock`
- Create: `plugins/flair/tests/test_flair_display_fonts.py`

**Interfaces:**
- Consumes: `fonts/<basename>.ttf` from Task 1.
- Produces: `DISPLAY_FONTS: tuple[tuple[str, str], ...]` = `(("BungeeShade", "BungeeShade-Regular.ttf"), ("BungeeOutline", "BungeeOutline-Regular.ttf"), ("LondrinaShadow", "LondrinaShadow-Regular.ttf"), ("LondrinaOutline", "LondrinaOutline-Regular.ttf"))`; `DISPLAY_FONT_THRESHOLD: int = 45`; `register_display_fonts(api) -> None`. Task 3's README table and demo config use the qualified names `flair.<name>`.

- [ ] **Step 1: Write the failing tests** (`tests/test_flair_display_fonts.py`)

```python
import logging
from pathlib import Path
from unittest import mock

import pytest
from led_ticker import _plugin_loader as L
from led_ticker.plugin import HiresFont, default_threshold, resolve_font
from led_ticker.fonts import list_available_hires_fonts  # not on the plugin surface; test-only

NAMES = ["BungeeShade", "BungeeOutline", "LondrinaShadow", "LondrinaOutline"]


@pytest.fixture
def loaded():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        assert not result.failed, result.failed
        yield
    finally:
        L.reset_plugins()


@pytest.mark.parametrize("name", NAMES)
def test_font_resolves_as_hires_with_threshold_45(loaded, name):
    font = resolve_font(f"flair.{name}", size=48)
    assert isinstance(font, HiresFont)
    assert font.threshold == 45
    assert default_threshold(f"flair.{name}") == 45
    assert f"flair.{name}" in list_available_hires_fonts()


def test_registered_paths_exist(loaded):
    from led_ticker.fonts import hires_loader
    for name in NAMES:
        assert Path(hires_loader._PLUGIN_FONTS[f"flair.{name}"]).is_file()


def test_plugin_names_are_namespaced_and_do_not_shadow_user_stems(loaded):
    # A sign may also carry config/fonts/BungeeShade-Regular.ttf (threshold 128).
    assert "flair.BungeeShade" in list_available_hires_fonts()
    assert default_threshold("BungeeShade-Regular") == 128


def test_new_core_registers_three_arg_no_warning(caplog):
    from led_ticker_flair.flair.display_fonts import register_display_fonts
    api = mock.Mock()
    with caplog.at_level(logging.WARNING, logger="led_ticker_flair"):
        register_display_fonts(api)
    assert api.font.call_args_list == [
        mock.call("BungeeShade", "fonts/BungeeShade-Regular.ttf", threshold=45),
        mock.call("BungeeOutline", "fonts/BungeeOutline-Regular.ttf", threshold=45),
        mock.call("LondrinaShadow", "fonts/LondrinaShadow-Regular.ttf", threshold=45),
        mock.call("LondrinaOutline", "fonts/LondrinaOutline-Regular.ttf", threshold=45),
    ]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_old_core_registers_two_arg_and_warns_once(caplog, monkeypatch):
    from led_ticker_flair.flair import display_fonts
    monkeypatch.setattr(display_fonts, "API_VERSION", (1, 2))
    api = mock.Mock()
    with caplog.at_level(logging.WARNING, logger="led_ticker_flair"):
        display_fonts.register_display_fonts(api)
    assert api.font.call_args_list == [
        mock.call("BungeeShade", "fonts/BungeeShade-Regular.ttf"),
        mock.call("BungeeOutline", "fonts/BungeeOutline-Regular.ttf"),
        mock.call("LondrinaShadow", "fonts/LondrinaShadow-Regular.ttf"),
        mock.call("LondrinaOutline", "fonts/LondrinaOutline-Regular.ttf"),
    ]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "font_threshold = 45" in warnings[0].getMessage()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest plugins/flair/tests/test_flair_display_fonts.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: led_ticker_flair.flair.display_fonts` and, for the `loaded` tests, `UnknownFontError` on `flair.BungeeShade`.

- [ ] **Step 3: Implement `display_fonts.py`**

Module docstring: what the fonts are, OFL, bigsign only, 45 measured on moonbunny 2026-11-20 plus the local 36-56 px grid. `from led_ticker.plugin import API_VERSION` at module level (the test monkeypatches `display_fonts.API_VERSION`). `logger = logging.getLogger("led_ticker_flair")`. `register_display_fonts(api)`: if `API_VERSION >= (1, 3)` call `api.font(name, f"fonts/{file}", threshold=DISPLAY_FONT_THRESHOLD)` per entry; else call the two-arg form per entry and, after the loop, one `logger.warning("flair display fonts need `font_threshold = 45` on this core (plugin API %s < (1, 3)); set it on each widget or update the core image", API_VERSION)`.

- [ ] **Step 4: Wire it into `register(api)` and the module docstring**

In `flair/__init__.py`: `from led_ticker_flair.flair.display_fonts import register_display_fonts  # noqa: PLC0415` inside `register`, then `register_display_fonts(api)` after the `api.widget("lottery")(Lottery)` line. Add one docstring sentence: "The namespace also ships four display fonts, `font = "flair.BungeeShade"` etc. (see `display_fonts.py`)." Do NOT add a `(1, 3)` probe to `_import_seam`; the fallback is the design.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest plugins/flair/tests/test_flair_display_fonts.py plugins/flair/tests/test_smoke.py -q`
Expected: PASS (all; `test_smoke` still registers five namespaces).

- [ ] **Step 6: Core floor and lock**

In `plugins/flair/pyproject.toml` change the dependency to `"led-ticker-core>=4.35",` and extend its comment with one line: `4.35 ships plugin API (1, 3): api.font(..., threshold=) so the display fonts carry their own default.` Then, once `pip index versions led-ticker-core` lists 4.35.0: `uv lock --upgrade-package led-ticker-core` and `uv sync --all-extras`; confirm `grep -A1 'name = "led-ticker-core"' uv.lock` shows `4.35.0`. If PyPI does not have it yet, leave the lock step for the end of Task 4 and run the suite with `uv run --no-sync` against the editable core checkout; ledger the ruling.

- [ ] **Step 7: Run the flair suite**

Run: `uv run pytest plugins/flair -q`
Expected: all PASS (the `test_examples_validate.py` glob and `test_smoke.py` included).

- [ ] **Step 8: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/display_fonts.py plugins/flair/src/led_ticker_flair/flair/__init__.py plugins/flair/pyproject.toml uv.lock plugins/flair/tests/test_flair_display_fonts.py
git commit -m "feat(flair): register the display fonts as flair.<Name> with default font_threshold 45 (core >= 4.35)"
```

---

### Task 3: Demo config, GIF, README section, parity test

**Files:**
- Create: `plugins/flair/examples/config.display-fonts.bigsign.toml` (the spec says `display-fonts.bigsign.toml`; the repo's examples are all `config.<name>.<sign>.toml`, so the convention wins)
- Create: `plugins/flair/docs/display-fonts.gif`
- Modify: `plugins/flair/README.md` (new `## Display fonts` section immediately before `## Install`)
- Create: `plugins/flair/tests/test_display_fonts_readme.py`

**Interfaces:**
- Consumes: `flair.<name>` from Task 2.

- [ ] **Step 1: Write the demo config**

`examples/config.display-fonts.bigsign.toml`: the bigsign `[display]` block as in `examples/config.accordion-smoke.bigsign.toml` (rows 32, cols 64, chain 8, Remap, `default_scale = 4`), `[title] delay = 0`, `[transitions] default = "dissolve"`, `between_sections = "random"`, `transition_duration = 0.8`, then five `[[playlist.section]]` blocks (`loop_count = 1`, `hold_time = 6`) each with one `message`:

| text | font | font_size | font_color |
|---|---|---|---|
| `OPEN 9-5` | `flair.BungeeShade` | 46 | `{style = "shimmer", base = "gold", shimmer = "white"}` |
| `HELLO 123` | `flair.BungeeOutline` | 48 | `"rainbow"` |
| `Fresh Donuts` | `flair.LondrinaShadow` | 52 | `[255, 80, 160]` |
| `Hello 123` | `flair.LondrinaOutline` | 48 | `{style = "gradient", from = [120, 255, 120], to = [0, 200, 255]}` |
| `Open fonts, style baked in` | `flair.BungeeShade` | 44 | `[255, 200, 0]` (this one `hold_time = 8`, scrolls) |

No `font_threshold` lines: the point is the plugin default. Header comment: what it shows, bigsign only, source of 45. (This is the config running on moonbunny today with user-font names; `../led-ticker/docs/superpowers/specs/assets/2026-11-19-text-styling-gate/hw/display-fonts-demo.toml`.)

- [ ] **Step 2: Validate it through the shipped-examples test**

Run: `uv run pytest plugins/flair/tests/test_examples_validate.py -q -k display-fonts`
Expected: PASS, no errors (rule 5 is satisfied by every `font_size`; rule 2 is quiet because nothing overrides).

- [ ] **Step 3: Write the failing parity test** (`tests/test_display_fonts_readme.py`)

```python
import re
from pathlib import Path

_FLAIR = Path(__file__).parent.parent
_README = (_FLAIR / "README.md").read_text()
_EXAMPLE = (_FLAIR / "examples" / "config.display-fonts.bigsign.toml").read_text()


def _readme_snippet() -> str:
    section = _README.split("## Display fonts", 1)[1].split("\n## ", 1)[0]
    m = re.search(r"```toml\n(.*?)```", section, re.S)
    assert m, "README Display fonts section has no toml snippet"
    return m.group(1)


def test_readme_snippet_is_verbatim_from_the_example():
    assert _readme_snippet() in _EXAMPLE


def test_readme_table_lists_every_font_once():
    section = _README.split("## Display fonts", 1)[1].split("\n## ", 1)[0]
    for name in ("flair.BungeeShade", "flair.BungeeOutline", "flair.LondrinaShadow", "flair.LondrinaOutline"):
        assert section.count(f"`{name}`") >= 1, name


def test_example_without_font_size_fails_rule_5(tmp_path):
    import asyncio
    from led_ticker import _plugin_loader as L
    from led_ticker.validate import validate_config
    broken = tmp_path / "c.toml"
    broken.write_text(_EXAMPLE.replace("font_size = 46\n", "", 1))
    L.reset_plugins()
    try:
        L.load_plugins_for_config(broken)
        result = asyncio.run(validate_config(broken))
    finally:
        L.reset_plugins()
    assert any(e.rule == 5 and "flair.BungeeShade" in e.message for e in result.errors), result.errors
```

- [ ] **Step 4: Run it to verify it fails**

Run: `uv run pytest plugins/flair/tests/test_display_fonts_readme.py -q`
Expected: FAIL on `_readme_snippet` (no "## Display fonts" section yet); `test_example_without_font_size_fails_rule_5` PASSES already (core behaviour) — that is expected, it is a pin.

- [ ] **Step 5: Render the GIF**

Make a scratchpad copy of the example with `rows = 64`, `cols = 256`, `chain_length = 1`, the `pixel_mapper_config`, `hardware_mapping` and `gpio_slowdown` lines deleted (the render demo ignores the Remap; see core memory). From the core checkout: `PYTHONPATH=. uv run --project ../led-ticker-plugins python tools/render_demo/render.py <copy> -o plugins/flair/docs/display-fonts.gif --duration 38` (one full pass: 4×6 s + 8 s + transitions; use the making-a-gif skill if the duration needs tuning; sample by playback time). Read the GIF's first/mid frames back as PNG to confirm the outlines are continuous before committing it.

- [ ] **Step 6: Write the README section** (before `## Install`)

`## Display fonts`: one paragraph (four OFL display fonts bundled, style baked into the glyphs, `font = "flair.<Name>"`, default `font_threshold` 45 declared by the plugin so no knob is needed, **bigsign only: scale 4, unreadable on 16-row signs**, `message` only at these sizes since a `two_row` band is 32 real px), the GIF (`![flair display fonts — Bungee Shade, Bungee Outline, Londrina Shadow, Londrina Outline on the bigsign](docs/display-fonts.gif)`), a `### Config` toml snippet that is the `OPEN 9-5` section copied VERBATIM from the example (the `[[playlist.section]]` block through its `font_color` line), a `### Fonts` table:

| Font | Look | `font_size` (real px) | Default `font_threshold` |
|---|---|---|---|
| `flair.BungeeShade` | solid face with a hard drop shade | 40-56 | 45 |
| `flair.BungeeOutline` | single-stroke outline | 36-52 | 45 |
| `flair.LondrinaShadow` | rounded face with offset shadow | 44-56 | 45 |
| `flair.LondrinaOutline` | rounded single-stroke outline | 36-52 | 45 |

and a `### Notes` list: requires **led-ticker-core >= 4.35** (on an older core the fonts register at 128, the log warns once, set `font_threshold = 45` per widget); licences in `src/led_ticker_flair/flair/fonts/OFL-*.txt`; a user `config/fonts/BungeeShade-Regular.ttf` is a different name (`BungeeShade-Regular`, threshold 128) and does not clash.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest plugins/flair/tests/test_display_fonts_readme.py plugins/flair/tests/test_examples_validate.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add plugins/flair/examples/config.display-fonts.bigsign.toml plugins/flair/docs/display-fonts.gif plugins/flair/README.md plugins/flair/tests/test_display_fonts_readme.py
git commit -m "docs(flair): display fonts demo config, GIF and README section with parity test"
```

---

### Task 4: CLAUDE.md invariant, lint, full suite

**Files:**
- Modify: `plugins/flair/CLAUDE.md` (Invariants list; the `flair` namespace bullet that says "has no `sprites/` directory")

- [ ] **Step 1: Add the invariant bullet**

Under `## Invariants`, after the sprites bullet: "**Display fonts are unmodified OFL files under `src/led_ticker_flair/flair/fonts/`** (the `flair` namespace has no `sprites/` but does have `fonts/`), registered by `display_fonts.register_display_fonts` as `flair.<Name>` with default `font_threshold` 45 via `api.font(..., threshold=45)` (core API `(1, 3)`; older cores get the two-arg call and ONE warning). 45 comes from the moonbunny measurement (2026-11-20) plus the local 36-56 px dangling-ends grid; re-measure on the sign before changing it, and never lower the core floor below 4.35. `tests/test_packaging.py` pins the sha256 of each TTF; `tests/test_display_fonts_readme.py` pins README/example parity." Amend the `flair` namespace bullet's "has no `sprites/` directory" to "has no `sprites/` directory (it has `fonts/`)".

- [ ] **Step 2: Lint, type-check, full suite**

Run: `make lint && uv run pyright plugins/flair/src && uv run pytest plugins/flair -q`
Expected: lint clean, 0 pyright errors in `display_fonts.py`, all tests PASS. If the lock step was deferred in Task 2, do it now and re-run.

- [ ] **Step 3: Commit**

```bash
git add plugins/flair/CLAUDE.md
git commit -m "docs(flair): display-fonts invariant"
```

---

## After the plan

- Draft PR in `led-ticker-plugins` (needs James's go for `gh pr create`), title `feat(flair): bundled display fonts with plugin-declared threshold (core >= 4.35)`. Antagonist loop per the roadmap rule (cap 5, exit on LOW/DOCS only) before the merge ask.
- Hardware check on moonbunny after merge: swap the live demo's user-font names for `flair.*`, drop its `font_threshold` lines, bump the flair pin to the new release, `docker restart led-ticker`, capture (ask first).
- Follow-up outside this plan: core docs `plugins/available.mdx` flair blurb could mention the fonts; a core `concepts/fonts` cross-link. Separate small core PR.
