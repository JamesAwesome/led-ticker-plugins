"""Placeholder so CI has a green test before the Phase 2 port.

Replaced by the real entry-point smoke test + AST import-purity tripwire
once the widgets/emoji/transitions are ported in.
"""

import led_ticker_baseball


def test_package_exposes_register():
    assert callable(led_ticker_baseball.register)
