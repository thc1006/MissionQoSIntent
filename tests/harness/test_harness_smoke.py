"""Smoke test: mqi.harness imports and is documented."""

import mqi.harness


def test_module_documented() -> None:
    assert mqi.harness.__doc__
