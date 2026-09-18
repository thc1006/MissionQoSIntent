"""Top-level smoke test: the package imports and exposes a version."""

import mqi


def test_version_present() -> None:
    assert mqi.__version__ == "0.1.0"
