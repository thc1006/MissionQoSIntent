"""Transport-agnostic admission service wrapping the runtime L2/L3 AdmissionStack.

`AdmissionService.handle(method, path, body)` returns a `Response`; the socket layer in
`mqi.serve.__main__` is a thin adapter over it, so the routing/decoding logic is unit-testable
without a socket. The load and saturation signals are mutable in-memory stubs driven via
`POST /load` and `POST /saturation`, letting an operator (or the Stage-9 E2E harness) exercise the
ADMIT / DEFER / DROP and L3-throttle paths deterministically against a real deployed pod.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any

from mqi.ir import MissionIR
from mqi.runtime import build_admission_stack
from mqi.runtime.clock import Clock, SystemClock
from mqi.runtime.l2gate import StaticLoad
from mqi.runtime.l3 import SaturationGate, StaticSaturation


@dataclass(frozen=True)
class Response:
    """A ready-to-send HTTP response: status code, body text, and content type."""

    status: int
    body: str
    content_type: str = "application/json"


class AdmissionService:
    """Wraps one tenant group's AdmissionStack behind a tiny HTTP-shaped dispatcher."""

    def __init__(
        self,
        ir: MissionIR,
        *,
        clock: Clock | None = None,
        max_queue: int = 64,
        burst_seconds: float = 1.0,
        sat_high: float = 0.9,
        sat_low: float = 0.5,
    ) -> None:
        self._clock = clock if clock is not None else SystemClock()
        self._load = StaticLoad(slots=1, min_service_ms=1)
        self._saturation = StaticSaturation(0.0)
        self._stack = build_admission_stack(
            ir,
            clock=self._clock,
            load=self._load,
            saturation=self._saturation,
            saturation_gate=SaturationGate(high=sat_high, low=sat_low),
            max_queue=max_queue,
            burst_seconds=burst_seconds,
        )
        self._by_id = {w.id: w for w in ir.workloads}
        # ThreadingHTTPServer dispatches each connection on its own thread; the AdmissionStack it
        # wraps mutates shared state (the L2 deferred queue, the L3 token bucket, metrics), so every
        # request is serialized through this lock. Throughput is fine for an admission gate.
        self._lock = threading.Lock()

    def handle(self, method: str, path: str, body: bytes = b"") -> Response:
        """Route one request to its handler (thread-safe); unknown routes return 404."""
        with self._lock:
            return self._dispatch(method, path, body)

    def _dispatch(self, method: str, path: str, body: bytes) -> Response:
        route = (method.upper(), path.split("?", 1)[0].rstrip("/") or "/")
        if route == ("GET", "/healthz"):
            return Response(200, "ok\n", "text/plain")
        if route == ("GET", "/metrics"):
            return Response(200, self._prometheus(), "text/plain; version=0.0.4")
        if route == ("GET", "/snapshot"):
            return Response(200, _dumps(self._stack.snapshot()))
        if route == ("POST", "/admit"):
            return self._admit(body)
        if route == ("POST", "/tick"):
            out = self._stack.tick()
            return Response(200, _dumps(out.model_dump() if out is not None else None))
        if route == ("POST", "/load"):
            return self._set_load(body)
        if route == ("POST", "/saturation"):
            return self._set_saturation(body)
        return Response(404, _dumps({"error": f"no route for {method} {path}"}))

    def _admit(self, body: bytes) -> Response:
        payload = _json_obj(body)
        if payload is None:
            return Response(400, _dumps({"error": "body must be a JSON object"}))
        wid, rid = payload.get("workload_id"), payload.get("request_id")
        if not isinstance(wid, str) or not isinstance(rid, str):
            return Response(400, _dumps({"error": "workload_id and request_id must be strings"}))
        workload = self._by_id.get(wid)
        if workload is None:
            return Response(404, _dumps({"error": f"unknown workload_id {wid!r}"}))
        arrival = payload.get("arrival_ms")
        if arrival is not None and (isinstance(arrival, bool) or not isinstance(arrival, int)):
            return Response(400, _dumps({"error": "arrival_ms must be an integer (milliseconds)"}))
        arrival_ms = self._clock.now_ms() if arrival is None else arrival
        try:
            result = self._stack.admit(workload, rid, arrival_ms)
        except ValueError as exc:  # request_id already in-flight — single-shot contract
            return Response(409, _dumps({"error": str(exc)}))
        return Response(
            200,
            _dumps(
                {
                    "throttle": result.throttle.value,
                    "admission": None if result.admission is None else result.admission.value,
                }
            ),
        )

    def _set_load(self, body: bytes) -> Response:
        payload = _json_obj(body)
        if payload is None:
            return Response(400, _dumps({"error": "body must be a JSON object"}))
        for key in ("slots", "min_service_ms"):
            if key in payload:
                value = payload[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    return Response(400, _dumps({"error": f"{key} must be a non-negative integer"}))
                setattr(self._load, key, value)
        return Response(
            200, _dumps({"slots": self._load.slots, "min_service_ms": self._load.min_service_ms})
        )

    def _set_saturation(self, body: bytes) -> Response:
        payload = _json_obj(body)
        if payload is None:
            return Response(400, _dumps({"error": "body must be a JSON object"}))
        level = payload.get("level")
        if (
            isinstance(level, bool)
            or not isinstance(level, (int, float))
            or not 0.0 <= level <= 1.0
        ):
            return Response(400, _dumps({"error": "level must be a number in [0.0, 1.0]"}))
        self._saturation.value = float(level)
        return Response(200, _dumps({"level": self._saturation.value}))

    def _prometheus(self) -> str:
        gate, throttle = self._stack.gate.metrics, self._stack.throttle.metrics
        series = (
            ("mqi_l2_admitted", "L2 requests admitted", gate.admitted),
            ("mqi_l2_deferred", "L2 requests deferred (queued)", gate.deferred),
            ("mqi_l2_dropped", "L2 requests dropped (red-line / queue-full)", gate.dropped),
            ("mqi_l3_passed", "L3 requests that passed the group throttle", throttle.passed),
            ("mqi_l3_throttled", "L3 requests throttled (rate / saturation)", throttle.throttled),
        )
        lines: list[str] = []
        for name, help_text, value in series:
            lines += [f"# HELP {name} {help_text}", f"# TYPE {name} counter", f"{name} {value}"]
        return "\n".join(lines) + "\n"


def _json_obj(body: bytes) -> dict[str, Any] | None:
    """Parse `body` as a JSON object, or None if it is not valid JSON / not an object."""
    try:
        parsed = json.loads(body or b"{}")
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)
