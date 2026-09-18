"""Unit tests for the Python policy-guard client (no opa binary required)."""

from typing import Any

import pytest

from mqi.policy import PolicyDenied
from mqi.policy.guard import GuardUnavailable, evaluate

_EMPTY: dict[str, Any] = {"metadata": {"tenant": "x"}, "spec": {"workloads": []}}


def test_policy_denied_carries_reasons() -> None:
    err = PolicyDenied(["reason-a", "reason-b"])
    assert err.reasons == ("reason-a", "reason-b")
    assert "reason-a" in str(err)


def test_evaluate_raises_when_opa_binary_missing() -> None:
    with pytest.raises(GuardUnavailable):
        evaluate(_EMPTY, opa_bin="/nonexistent/opa-binary")


def test_evaluate_raises_on_malformed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Proc:
        stdout = '{"result": []}'  # valid JSON, unexpected shape

    def _fake_run(*_args: object, **_kwargs: object) -> _Proc:
        return _Proc()

    monkeypatch.setattr("mqi.policy.guard.subprocess.run", _fake_run)

    with pytest.raises(GuardUnavailable):
        evaluate(_EMPTY)
