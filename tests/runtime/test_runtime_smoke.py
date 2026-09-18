"""Smoke test: mqi.runtime imports and is documented."""

import mqi.runtime


def test_module_documented() -> None:
    assert mqi.runtime.__doc__
