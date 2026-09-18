"""RenderedBundle.parse robustness: malformed / wrong-shape artifacts are rejected cleanly."""

from __future__ import annotations

import pytest

from mqi.verifier import RenderedBundle


def test_parse_rejects_malformed_yaml() -> None:
    with pytest.raises(ValueError, match="malformed YAML"):
        RenderedBundle.parse("{ bad: yaml: :", "", "")


def test_parse_rejects_non_mapping_l2() -> None:
    with pytest.raises(ValueError, match="L2 artifact must be a mapping"):
        RenderedBundle.parse("just a scalar", "", "")


def test_parse_rejects_non_mapping_l4() -> None:
    with pytest.raises(ValueError, match="L4 artifact must be a sequence of mappings"):
        RenderedBundle.parse("{}", "- 1\n- 2\n", "")


def test_parse_rejects_non_mapping_l5() -> None:
    with pytest.raises(ValueError, match="L5 artifact must be a sequence of mappings"):
        RenderedBundle.parse("{}", "", "- 1\n")


def test_parse_rejects_yaml_aliases() -> None:
    # anchor + alias — the seed of an exponential 'billion laughs' expansion
    doc = "a: &x [1, 2]\nb: *x\n"
    with pytest.raises(ValueError, match="aliases are not permitted"):
        RenderedBundle.parse(doc, "", "")
