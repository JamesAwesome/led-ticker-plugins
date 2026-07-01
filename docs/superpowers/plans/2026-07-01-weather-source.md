# Weather Value-Token Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `weather.current` polled **source** so `text = "NYC: :weather.nyc:"` renders live "72°F Clear", updating in the background — reusing the core polled mechanism (`PolledDataSource`, led-ticker-core v4.1.0).

**Architecture:** Extract the WeatherAPI fetch out of `WeatherWidget.update()` into a shared `fetch_current(session, location) -> dict`. Add `WeatherSource(PolledDataSource)` (sibling `source.py`) that fetches, builds a fields dict, and renders a user `format` string via `str.format`. Register it via `api.source("current")`. Core drives the supervised poll loop; the source only implements `async def update()`.

**Tech Stack:** Python 3.14 (PEP 649), attrs, aiohttp, led-ticker-core ≥ 4.1.

**Source of truth:** the led-ticker spec `docs/superpowers/specs/2026-06-30-inline-value-tokens-v2-polled-design.md` §2. This plan is the plugin half; the core mechanism already shipped in v4.1.0.

## Deliberate spec deviation (not a gap)

The spec §2 listed `high_f`/`low_f` fields. WeatherAPI's `/current.json` endpoint (what the widget + the shared fetch use) returns **current conditions only** — daily high/low require `/forecast.json`. **`high_f`/`low_f` are TRIMMED from v2** and are a future forecast-endpoint enhancement. Exposed fields are current-endpoint only (Task 3). A reviewer should NOT treat their absence as a missing requirement.

## Global Constraints

- **Public surface ONLY:** every module under `src/led_ticker_weather/` imports from `led_ticker.plugin` (never `led_ticker.<internal>`), plus stdlib + `aiohttp` + `attrs`. Intra-package imports (`from led_ticker_weather.weather import …`) are fine. Enforced by `tests/test_import_purity.py` (AST rglob of `src/led_ticker_weather`).
- **Write-order:** the source sets its value ONLY via `self._set_value(str)` (core writes `current` before `version`, no await between). Never assign `self.current`/`self.version` directly in `update()`.
- **Supervised / keep-last:** core drives the poll loop (`run_monitor_loop`, backoff, survives exceptions). `update()` only `_set_value`s on success → a fetch failure keeps the last good value. Do not add a try/except that swallows + blanks the value.
- **Secrets:** `WEATHERAPI_KEY` from env, never config. Tests never hardcode a real key — use the autouse `monkeypatch.setenv` pattern (and/or mock `fetch_current` so no key/network is needed).
- **PEP 649:** no `from __future__ import annotations`. **DOCS-STYLE:** no "footgun". **Python 3.14+.**
- **Core pin:** `led-ticker-core>=4.1`.
- Gates (from the **monorepo root** `/Users/james/projects/github/jamesawesome/led-ticker-plugins-worktrees/weather-source`, NO `PYTHONPATH` prefix): `uv run pytest plugins/weather`, `uv run ruff check plugins/weather`, `uv run ruff format --check plugins/weather`, `uv run pyright plugins/weather/src`.
- Worktree `feat/weather-source`; never `main`. `git -c core.hooksPath=/dev/null` only if the hook misbehaves (committed code must still pass the gates).

## Non-Goals

high_f/low_f / any forecast-endpoint fields (trimmed — see above); sub-field tokens (`:weather.nyc.temp:`); sharing a poll with the weather WIDGET (independent per source id — documented); crypto/other sources; a format language beyond `str.format`.

## File Structure

- **Modify** `plugins/weather/pyproject.toml` — core pin `>=2.1` → `>=4.1`.
- **Modify** `plugins/weather/src/led_ticker_weather/weather.py` — extract `fetch_current`; refactor `WeatherWidget.update()` to call it. `_match_condition` stays here (shared).
- **Create** `plugins/weather/src/led_ticker_weather/source.py` — `WeatherSource(PolledDataSource)` + `validate_config`.
- **Modify** `plugins/weather/src/led_ticker_weather/__init__.py` — `register` also `api.source("current")(WeatherSource)`.
- **Create** `plugins/weather/tests/test_source.py`. **Modify** `plugins/weather/tests/test_smoke.py` (source registration), `plugins/weather/tests/test_weather.py` (widget still green after the extraction). **Modify** `plugins/weather/README.md`.

---

## Task 1: Bump the core pin + sync

**Files:** Modify `plugins/weather/pyproject.toml`.

**Interfaces — Produces:** `led-ticker-core>=4.1` resolvable; `from led_ticker.plugin import PolledDataSource` importable in the env.

- [ ] **Step 1:** In `plugins/weather/pyproject.toml`, change `"led-ticker-core>=2.1"` → `"led-ticker-core>=4.1"` in `dependencies`.

- [ ] **Step 2:** From the monorepo root, `uv sync --extra dev`. Expected: resolves `led-ticker-core` 4.1.0 (published to PyPI). If it cannot find 4.1.0 (PyPI propagation), STOP and report BLOCKED (do not pin lower).

- [ ] **Step 3:** Verify the new surface imports — run:

```bash
uv run python -c "from led_ticker.plugin import PolledDataSource; print(PolledDataSource)"
```
Expected: prints the class (no ImportError).

- [ ] **Step 4:** Confirm the existing suite still passes against 4.1.0: `uv run pytest plugins/weather -q`. Expected: all green (no behavior change yet).

- [ ] **Step 5: Commit** — `git add plugins/weather/pyproject.toml uv.lock 2>/dev/null; git commit -m "build(weather): require led-ticker-core>=4.1 (PolledDataSource + api.source)"`.

---

## Task 2: Extract the shared `fetch_current` helper

**Files:** Modify `plugins/weather/src/led_ticker_weather/weather.py`; Test `plugins/weather/tests/test_weather.py`.

**Interfaces — Produces:** `async def fetch_current(session, location) -> dict` (module-level in `weather.py`): reads `WEATHERAPI_KEY`, GETs `/current.json` with `q=location`, raises `ValueError` on missing key / API error, returns the `current` dict. `WeatherWidget.update()` now calls it.

- [ ] **Step 1: Write the failing test** in `tests/test_weather.py` (add near the existing widget tests):

```python
class TestFetchCurrent:
    async def test_fetch_current_returns_current_dict(self, monkeypatch):
        import unittest.mock as mock
        from led_ticker_weather.weather import fetch_current

        monkeypatch.setenv("WEATHERAPI_KEY", "k")
        payload = {"current": {"temp_f": 72.0, "condition": {"text": "Clear"}}}
        resp = mock.AsyncMock()
        resp.json = mock.AsyncMock(return_value=payload)
        session = mock.Mock()
        session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
        session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        current = await fetch_current(session, "NYC")
        assert current == {"temp_f": 72.0, "condition": {"text": "Clear"}}

    async def test_fetch_current_raises_on_api_error(self, monkeypatch):
        import unittest.mock as mock
        from led_ticker_weather.weather import fetch_current

        monkeypatch.setenv("WEATHERAPI_KEY", "k")
        payload = {"error": {"code": 1006, "message": "No matching location found."}}
        resp = mock.AsyncMock()
        resp.json = mock.AsyncMock(return_value=payload)
        session = mock.Mock()
        session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
        session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        with pytest.raises(ValueError, match="1006"):
            await fetch_current(session, "Nowhere")

    async def test_fetch_current_raises_without_key(self, monkeypatch):
        import unittest.mock as mock
        from led_ticker_weather.weather import fetch_current
        monkeypatch.delenv("WEATHERAPI_KEY", raising=False)
        with pytest.raises(ValueError, match="WEATHERAPI_KEY"):
            await fetch_current(mock.Mock(), "NYC")
```

(Match the repo's async-test convention — check `test_weather.py`/`pyproject.toml` for `asyncio_mode`; if not `auto`, add the `@pytest.mark.asyncio` decorator the other async tests use. The autouse `_set_weather_api_key` fixture sets the key globally — the `delenv` test overrides it, so keep that test's `monkeypatch.delenv`.)

- [ ] **Step 2: Run → FAIL** — `uv run pytest plugins/weather/tests/test_weather.py -k fetch_current -q` (ImportError: fetch_current).

- [ ] **Step 3: Implement** in `weather.py`. Add at module level (after `WEATHERAPI_URL`, before `_match_condition`):

```python
async def fetch_current(session: aiohttp.ClientSession, location: str) -> dict:
    """GET current conditions from WeatherAPI (/current.json) and return the
    `current` dict. Reads WEATHERAPI_KEY from env. Raises ValueError on a
    missing key or an API error. Shared by WeatherWidget and WeatherSource."""
    api_key = os.getenv("WEATHERAPI_KEY", "")
    if not api_key:
        raise ValueError("WEATHERAPI_KEY not set. Add it to your .env file.")
    async with session.get(WEATHERAPI_URL, params={"key": api_key, "q": location}) as response:
        data = await response.json()
    if "error" in data:
        code = data["error"].get("code", "?")
        msg = data["error"].get("message", "Unknown error")
        raise ValueError(f"WeatherAPI error {code}: {msg}")
    return data["current"]
```

Then refactor `WeatherWidget.update()` to use it (replace its inline fetch body):

```python
    async def update(self) -> None:
        logging.info("Updating weather for: %s", self.location)
        current = await fetch_current(self.session, self.location)
        if self.units == "imperial":
            self.current_temp = int(current["temp_f"])
        else:
            self.current_temp = int(current["temp_c"])
        self.weather = current["condition"]["text"]
```

- [ ] **Step 4: Run → PASS** — `uv run pytest plugins/weather/tests/test_weather.py -q` (the new fetch tests AND all pre-existing widget tests — the extraction must be behavior-identical).

- [ ] **Step 5: Commit** — `git commit -am "refactor(weather): extract shared fetch_current (DRY for widget + source)"`.

---

## Task 3: `WeatherSource(PolledDataSource)` + fields + format

**Files:** Create `plugins/weather/src/led_ticker_weather/source.py`; Test `plugins/weather/tests/test_source.py`.

**Interfaces — Consumes:** `PolledDataSource` (`led_ticker.plugin`), `fetch_current` + `_match_condition` (`led_ticker_weather.weather`). **Produces:** `WeatherSource(PolledDataSource)` with kw_only attrs `location`, `format` (default `"{temp_f}°F {condition}"`), `placeholder` (default `"…"`); `_FIELDS` tuple; `_DEFAULT_FORMAT`.

- [ ] **Step 1: Write the failing test** `tests/test_source.py`:

```python
import unittest.mock as mock

import pytest

from led_ticker_weather.source import WeatherSource, _DEFAULT_FORMAT

_CURRENT = {
    "temp_f": 72.0, "temp_c": 22.0,
    "feelslike_f": 74.0, "feelslike_c": 23.0,
    "humidity": 50, "wind_mph": 5.0,
    "condition": {"text": "Clear"},
}


def _src(**kw):
    return WeatherSource(id="weather.nyc", session=mock.Mock(), interval=1800,
                         location="NYC", **kw)


async def test_update_renders_default_format(monkeypatch):
    monkeypatch.setattr("led_ticker_weather.source.fetch_current",
                        mock.AsyncMock(return_value=_CURRENT))
    s = _src()
    await s.update()
    assert s.current == "72°F Clear"      # default "{temp_f}°F {condition}"
    assert s.version == 1                  # _set_value bumped

async def test_update_custom_format_with_emoji(monkeypatch):
    monkeypatch.setattr("led_ticker_weather.source.fetch_current",
                        mock.AsyncMock(return_value=_CURRENT))
    s = _src(format="{temp_f}° {emoji}")
    await s.update()
    assert s.current == "72° :sun:"        # Clear -> sun -> :sun: (renders as sprite downstream)

async def test_update_exposes_all_current_fields(monkeypatch):
    monkeypatch.setattr("led_ticker_weather.source.fetch_current",
                        mock.AsyncMock(return_value=_CURRENT))
    s = _src(format="{feelslike_f}|{humidity}|{wind_mph}|{temp_c}|{feelslike_c}")
    await s.update()
    assert s.current == "74|50|5|22|23"

def test_placeholder_until_first_fetch():
    s = _src(placeholder="—")
    assert s.current == "—" and s.version == 0   # nothing fetched yet

def test_location_dict_normalized():
    s = WeatherSource(id="w", session=mock.Mock(), interval=1800,
                      location={"lat": 40.7, "lon": -74.0})
    assert s.location == "40.7,-74.0"

def test_default_format_constant():
    assert _DEFAULT_FORMAT == "{temp_f}°F {condition}"
```

(Use the repo's async convention as in Task 2.)

- [ ] **Step 2: Run → FAIL** — `uv run pytest plugins/weather/tests/test_source.py -q` (ImportError).

- [ ] **Step 3: Implement** `source.py`:

```python
"""weather.current polled SOURCE — a value token like `:weather.nyc:`.

Subclasses the core PolledDataSource mechanism (led-ticker-core >= 4.1): core
drives a supervised poll loop that calls `update()` every `interval` seconds;
`update()` fetches and renders a `format` string over the exposed fields, then
`self._set_value(...)` (write-order). Current-conditions fields only.
"""

import string
from typing import Any

import attrs
from led_ticker.plugin import PolledDataSource

from led_ticker_weather.weather import _match_condition, fetch_current

_DEFAULT_FORMAT = "{temp_f}°F {condition}"

# Fields exposed to `format`. Current-endpoint only (/current.json). `emoji` is
# the colon-wrapped condition slug — it composes: token substitution runs before
# layout, so draw_with_emoji renders it as a sprite. (high_f/low_f need the
# forecast endpoint — out of scope.)
_FIELDS = (
    "temp_f", "temp_c", "condition",
    "feelslike_f", "feelslike_c", "humidity", "wind_mph",
    "emoji",
)


@attrs.define(eq=False)
class WeatherSource(PolledDataSource):
    location: Any = attrs.field(default="", kw_only=True)
    format: str = attrs.field(default=_DEFAULT_FORMAT, kw_only=True)
    placeholder: str = attrs.field(default="…", kw_only=True)

    def __attrs_post_init__(self) -> None:
        # TOML may give location as {lat, lon} (same as the widget).
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"
        # Show the placeholder until the first successful fetch (version stays 0).
        self.current = self.placeholder

    async def update(self) -> None:
        current = await fetch_current(self.session, self.location)
        condition = current["condition"]["text"]
        fields = {
            "temp_f": int(current["temp_f"]),
            "temp_c": int(current["temp_c"]),
            "condition": condition,
            "feelslike_f": int(current["feelslike_f"]),
            "feelslike_c": int(current["feelslike_c"]),
            "humidity": int(current["humidity"]),
            "wind_mph": int(current["wind_mph"]),
            "emoji": f":{_match_condition(condition)}:",
        }
        # write-order: _set_value writes current before version, no await between.
        self._set_value(self.format.format(**fields))
```

- [ ] **Step 4: Run → PASS** — `uv run pytest plugins/weather/tests/test_source.py -q`.

- [ ] **Step 5: Commit** — `git add plugins/weather/src/led_ticker_weather/source.py plugins/weather/tests/test_source.py && git commit -m "feat(weather): WeatherSource polled source (fields + format + emoji)"`.

---

## Task 4: `validate_config` + register the source

**Files:** Modify `source.py` (add `validate_config`), `__init__.py` (register); Test `test_source.py` (validate) + `test_smoke.py` (registration).

**Interfaces — Produces:** `WeatherSource.validate_config(cls, cfg) -> list[str]`; `register()` also does `api.source("current")(WeatherSource)`.

- [ ] **Step 1: Write the failing tests.** Add to `test_source.py`:

```python
def test_validate_config_missing_location():
    errs = WeatherSource.validate_config({"type": "weather.current"})
    assert any("location" in e for e in errs)

def test_validate_config_unknown_format_field():
    errs = WeatherSource.validate_config(
        {"location": "NYC", "format": "{temp_f} {bogus}"})
    assert any("bogus" in e for e in errs)

def test_validate_config_valid_block():
    errs = WeatherSource.validate_config(
        {"location": "NYC", "format": "{temp_f}°F {emoji}"})
    assert errs == []

def test_validate_config_default_format_ok():
    # format omitted -> the default is used -> no unknown-field error
    assert WeatherSource.validate_config({"location": "NYC"}) == []
```

And extend `tests/test_smoke.py` — after the widget assertion, assert the SOURCE registered:

```python
        # source registered under the same namespace
        from led_ticker.app.factories import get_source_class
        assert get_source_class("weather.current") is not None
```

(Verify the source-class accessor in led-ticker-core 4.1.0 — mirror the `get_widget_class` import the smoke test already uses. If `get_source_class` isn't at `led_ticker.app.factories`, use the accessor core exposes (e.g. check `led_ticker.sources._PLUGIN_SOURCE_TYPES` membership after `load_plugins`). Do not invent a name — confirm it.)

- [ ] **Step 2: Run → FAIL** — `uv run pytest plugins/weather/tests/test_source.py -k validate -q` (no attribute) and `test_smoke.py` (source not registered).

- [ ] **Step 3: Implement.** Add to `WeatherSource` (source.py):

```python
    @classmethod
    def validate_config(cls, cfg: dict) -> list[str]:
        errors: list[str] = []
        if not cfg.get("location"):
            errors.append("weather.current: 'location' is required.")
        fmt = cfg.get("format", _DEFAULT_FORMAT)
        for _literal, field_name, _spec, _conv in string.Formatter().parse(fmt):
            if field_name and field_name not in _FIELDS:
                errors.append(
                    f"weather.current: unknown field '{{{field_name}}}' in format "
                    f"(known: {', '.join(_FIELDS)})."
                )
        return errors
```

Update `__init__.py`:

```python
from led_ticker_weather.source import WeatherSource
from led_ticker_weather.weather import WeatherWidget


def register(api):
    api.widget("current")(WeatherWidget)
    api.source("current")(WeatherSource)
```

- [ ] **Step 4: Run → PASS** — `uv run pytest plugins/weather -q` (source validate tests + smoke registration + the full package).

- [ ] **Step 5: Commit** — `git commit -am "feat(weather): validate_config + register weather.current source"`.

---

## Task 5: Import-purity + docs

**Files:** verify `tests/test_import_purity.py`; Modify `plugins/weather/README.md`.

- [ ] **Step 1:** Run `uv run pytest plugins/weather/tests/test_import_purity.py -q`. Expected: PASS — `source.py` imports only `led_ticker.plugin` from the `led_ticker` namespace (the `from led_ticker_weather.weather import …` intra-package import is not a `led_ticker.*` import, so it's allowed). If it fails, fix the offending import to route through `led_ticker.plugin`.

- [ ] **Step 2:** Add a "Weather value token" section to `plugins/weather/README.md` (DOCS-STYLE — no "footgun", no release-history framing). Cover: the `[[source]]` block, `WEATHERAPI_KEY` from env, the exposed current-conditions fields, the `{emoji}` sprite trick, and that it polls independently of the weather *widget*:

````markdown
## Weather value token (`:id:` in any widget's text)

Besides the `weather.current` **widget**, this plugin registers a `weather.current`
**source** — a live value you embed in another widget's text with a `:id:` token.

```toml
[[source]]
id = "weather.nyc"
type = "weather.current"
location = "New York, US"          # name / zip / "lat,lon" / {lat=…, lon=…}
interval = 1800                    # seconds; how often to refresh
format = "{temp_f}°F {condition}"  # optional; this is the default
# placeholder = "…"                # optional; shown until the first fetch
```

Then reference it anywhere text is drawn:

```toml
[[sections]]
[[sections.widgets]]
type = "message"
text = "NYC: :weather.nyc:"        # -> "NYC: 72°F Clear", updating live
```

`WEATHERAPI_KEY` comes from your `.env` (never config). Available `format`
fields (current conditions): `temp_f`, `temp_c`, `condition`, `feelslike_f`,
`feelslike_c`, `humidity`, `wind_mph`, and `emoji`. The `emoji` field expands to
a condition icon — `format = "{temp_f}° {emoji}"` → `72° ☀`. The source polls
on its own `interval`, independently of the `weather.current` widget.
````

- [ ] **Step 3:** `uv run pytest plugins/weather -q` (full package green) + `uv run ruff check plugins/weather` + `uv run ruff format --check plugins/weather` + `uv run pyright plugins/weather/src`. All clean.

- [ ] **Step 4: Commit** — `git commit -am "docs(weather): document the weather.current value-token source"`.

---

## Cross-repo follow-up (NOT in this plan / worktree)

The **core** docs site value-tokens page (`docs/site/.../concepts/value-tokens.mdx` in the **led-ticker** repo) currently describes polled sources conceptually and points at "the weather plugin." Once this ships, a small led-ticker PR should add the concrete weather `[[source]]` example there and update the cross-link. Do NOT edit it from this monorepo worktree — note it for the controller.

## Self-Review notes (for the executor)

- **Spec §2 coverage:** shared fetch → T2; WeatherSource + fields + format + emoji + placeholder → T3; validate_config + register(api.source) → T4; import-purity + README → T5; core pin → T1. `high_f`/`low_f` intentionally trimmed (header) — not a gap.
- **Type consistency:** `fetch_current(session, location) -> dict`, `WeatherSource(id, session, interval, location, format, placeholder)`, `_FIELDS`, `_DEFAULT_FORMAT`, `_match_condition` — same names across tasks.
- **Load-bearing:** write-order via `_set_value` (T3); public-surface import purity (T5); keep-last-on-failure is inherent (update only `_set_value`s on success; core's loop supervises).
- Verify the async-test convention (`asyncio_mode`) and the `get_source_class` accessor against the actual env before writing those tests — both are flagged inline.
