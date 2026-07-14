"""AST guard: plugin source may import ONLY from led_ticker.plugin.

Never from led_ticker.<internal>.
"""

import ast
import pathlib

SRC = pathlib.Path(__file__).parent.parent / "src" / "led_ticker_stocks"


def _bad_imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root == "led_ticker" and node.module != "led_ticker.plugin":
                bad.append(f"{path.name}: from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "led_ticker" and alias.name != "led_ticker.plugin":
                    bad.append(f"{path.name}: import {alias.name}")
    return bad


def test_only_public_surface_imported():
    offenders = [msg for p in SRC.rglob("*.py") for msg in _bad_imports(p)]
    assert not offenders, f"non-public led_ticker imports: {offenders}"
