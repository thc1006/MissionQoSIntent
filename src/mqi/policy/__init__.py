"""Policy guard: OPA/Rego admission gate over contracts before compilation."""

from mqi.policy.guard import GuardDecision, GuardUnavailable, PolicyDenied, evaluate

__all__ = ["GuardDecision", "GuardUnavailable", "PolicyDenied", "evaluate"]
