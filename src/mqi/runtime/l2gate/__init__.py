"""Runtime L2 deferred-red admission gate: slack-aware admit / defer / drop (ADR-0004)."""

from mqi.runtime.clock import Clock, ManualClock, SystemClock
from mqi.runtime.l2gate.gate import DeferredRedGate, build_request
from mqi.runtime.l2gate.models import Decision, GateMetrics, Outcome, Request
from mqi.runtime.l2gate.ordering import ORDERINGS, OrderingKey
from mqi.runtime.l2gate.signals import LoadSignal, StaticLoad

__all__ = [
    "ORDERINGS",
    "Clock",
    "Decision",
    "DeferredRedGate",
    "GateMetrics",
    "LoadSignal",
    "ManualClock",
    "OrderingKey",
    "Outcome",
    "Request",
    "StaticLoad",
    "SystemClock",
    "build_request",
]
