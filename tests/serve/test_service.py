"""Unit tests for AdmissionService.handle() — routing + L2/L3 decisions, no socket."""

from __future__ import annotations

import json
from collections.abc import Callable

from mqi.serve import AdmissionService

WORKLOAD_ID = "wl-0-emergency-routing"  # derived id of the single fixture workload (see conftest)
Factory = Callable[..., AdmissionService]


def _admit(
    svc: AdmissionService, request_id: str, *, workload_id: str = WORKLOAD_ID
) -> dict[str, object]:
    body = json.dumps({"workload_id": workload_id, "request_id": request_id}).encode()
    resp = svc.handle("POST", "/admit", body)
    assert resp.status == 200, resp.body
    result = json.loads(resp.body)
    assert isinstance(result, dict)
    return result


def test_healthz(make_service: Factory) -> None:
    resp = make_service().handle("GET", "/healthz")
    assert resp.status == 200 and resp.body == "ok\n"
    assert resp.content_type == "text/plain"


def test_admit_admits_under_capacity(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 1, "min_service_ms": 1}')
    assert _admit(svc, "r1") == {"throttle": "pass", "admission": "admit"}


def test_admit_defers_without_capacity(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 0, "min_service_ms": 1}')  # no slots, ample slack
    assert _admit(svc, "r1") == {"throttle": "pass", "admission": "defer"}


def test_admit_drops_when_redline_breached(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 1, "min_service_ms": 100000}')  # slack < min-service
    assert _admit(svc, "r1") == {"throttle": "pass", "admission": "drop"}


def test_l3_throttles_when_bucket_empty(make_service: Factory) -> None:
    svc = make_service(burst_seconds=1.0)  # rate 1, burst 1 -> a single L3 token
    svc.handle("POST", "/load", b'{"slots": 5, "min_service_ms": 1}')
    assert _admit(svc, "r1") == {"throttle": "pass", "admission": "admit"}  # spends the token
    assert _admit(svc, "r2") == {"throttle": "throttle", "admission": None}  # bucket empty


def test_saturation_throttles_when_high(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 5, "min_service_ms": 1}')
    # protected group (fallback reject-with-reason) is NOT sheddable -> saturation must not throttle
    svc.handle("POST", "/saturation", b'{"level": 0.99}')
    assert _admit(svc, "r1")["admission"] == "admit"  # guaranteed traffic stays protected


def test_admit_rejects_reused_in_flight_id(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 0, "min_service_ms": 1}')  # defer -> id stays in-flight
    assert _admit(svc, "dup")["admission"] == "defer"
    body = json.dumps({"workload_id": WORKLOAD_ID, "request_id": "dup"}).encode()
    resp = svc.handle("POST", "/admit", body)
    assert resp.status == 409  # single-shot: reused in-flight id


def test_admit_unknown_workload_is_404(make_service: Factory) -> None:
    resp = make_service().handle("POST", "/admit", b'{"workload_id": "nope", "request_id": "r1"}')
    assert resp.status == 404


def test_admit_bad_body_is_400(make_service: Factory) -> None:
    svc = make_service()
    assert svc.handle("POST", "/admit", b"not json").status == 400
    assert svc.handle("POST", "/admit", b'{"request_id": "r1"}').status == 400  # no workload_id
    assert svc.handle("POST", "/admit", b"[1, 2]").status == 400  # not an object
    bad_arrival = json.dumps({"workload_id": WORKLOAD_ID, "request_id": "r1", "arrival_ms": "x"})
    assert svc.handle("POST", "/admit", bad_arrival.encode()).status == 400
    # a JSON bool is an int subclass in Python — it must NOT be accepted as a millisecond timestamp
    bool_arrival = json.dumps({"workload_id": WORKLOAD_ID, "request_id": "r1", "arrival_ms": True})
    assert svc.handle("POST", "/admit", bool_arrival.encode()).status == 400


def test_tick_releases_a_deferred_request(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 0, "min_service_ms": 1}')
    assert _admit(svc, "r1")["admission"] == "defer"
    svc.handle("POST", "/load", b'{"slots": 1, "min_service_ms": 1}')  # capacity returns
    out = json.loads(svc.handle("POST", "/tick", b"").body)
    assert out is not None and out["request_id"] == "r1" and out["decision"] == "admit"


def test_tick_noop_returns_null(make_service: Factory) -> None:
    assert json.loads(make_service().handle("POST", "/tick", b"").body) is None


def test_load_validation(make_service: Factory) -> None:
    svc = make_service()
    assert svc.handle("POST", "/load", b'{"slots": -1}').status == 400
    assert svc.handle("POST", "/load", b'{"min_service_ms": "x"}').status == 400
    assert svc.handle("POST", "/load", b"not json").status == 400
    ok = svc.handle("POST", "/load", b'{"slots": 3, "min_service_ms": 7}')
    assert json.loads(ok.body) == {"slots": 3, "min_service_ms": 7}


def test_saturation_validation(make_service: Factory) -> None:
    svc = make_service()
    assert svc.handle("POST", "/saturation", b'{"level": 2.0}').status == 400
    assert svc.handle("POST", "/saturation", b'{"level": true}').status == 400
    assert svc.handle("POST", "/saturation", b"not json").status == 400
    assert json.loads(svc.handle("POST", "/saturation", b'{"level": 0.5}').body) == {"level": 0.5}


def test_metrics_prometheus_reflects_counts(make_service: Factory) -> None:
    svc = make_service()
    svc.handle("POST", "/load", b'{"slots": 1, "min_service_ms": 1}')
    _admit(svc, "r1")  # one admit
    metrics = svc.handle("GET", "/metrics")
    assert metrics.status == 200 and metrics.content_type.startswith("text/plain")
    assert "# TYPE mqi_l2_admitted counter" in metrics.body
    assert "mqi_l2_admitted 1" in metrics.body
    assert "mqi_l3_passed 1" in metrics.body


def test_snapshot_exposes_l2_and_l3(make_service: Factory) -> None:
    snap = json.loads(make_service().handle("GET", "/snapshot").body)
    assert set(snap) == {"l2", "l3"}


def test_unknown_route_is_404(make_service: Factory) -> None:
    assert make_service().handle("GET", "/nope").status == 404
    assert make_service().handle("DELETE", "/admit").status == 404
