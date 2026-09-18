"""Smoke test: mqi.policy imports and is documented."""

import mqi.policy


def test_module_documented() -> None:
    assert mqi.policy.__doc__
