import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "led_ticker_calendar"


def _led_ticker_imports(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "led_ticker":
                names.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "led_ticker":
                    names.append(alias.name)
    return names


def test_plugin_imports_only_public_surface():
    offenders = {}
    for py in SRC.rglob("*.py"):
        bad = [m for m in _led_ticker_imports(py) if m != "led_ticker.plugin"]
        if bad:
            offenders[py.name] = bad
    assert not offenders, (
        f"modules import led_ticker internals instead of led_ticker.plugin: {offenders}"
    )
