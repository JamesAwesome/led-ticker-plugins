"""Every shipped example config must pass core's config validation (the
same path as `led-ticker validate`) with no errors; CI previously missed
examples that predate a validation rule."""

import asyncio
from pathlib import Path

import pytest
from led_ticker import _plugin_loader as L
from led_ticker.validate import validate_config

_EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.toml"))


def test_examples_found() -> None:
    assert len(_EXAMPLES) >= 20


@pytest.mark.parametrize("path", _EXAMPLES, ids=lambda p: p.name)
def test_example_validates_clean(path: Path) -> None:
    L.reset_plugins()
    try:
        L.load_plugins_for_config(path)
        result = asyncio.run(validate_config(path))
    finally:
        L.reset_plugins()
    assert not result.errors, [f"{e.location}: {e.message}" for e in result.errors]
