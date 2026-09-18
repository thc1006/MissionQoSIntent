"""Smoke test: mqi.ir imports and is documented."""

import mqi.ir


def test_module_documented() -> None:
    assert mqi.ir.__doc__
