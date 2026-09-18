"""Integration tests for the socket adapter: real ThreadingHTTPServer + urllib + build_from_env."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from collections.abc import Callable, Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from mqi.ir import MissionIR
from mqi.serve import AdmissionService
from mqi.serve.__main__ import build_from_env, make_handler

WORKLOAD_ID = "wl-0-emergency-routing"
Factory = Callable[..., AdmissionService]
Server = tuple[AdmissionService, str, int]  # (service, host, port)


@pytest.fixture
def running_server(make_service: Factory) -> Iterator[Server]:
    """Start the real ThreadingHTTPServer on an ephemeral port; yield (service, host, port)."""
    svc = make_service()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield svc, str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _raw_request(host: str, port: int, request: bytes) -> bytes:
    """Send a raw HTTP request over a socket and return the raw response bytes."""
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(request)
        sock.settimeout(5)
        chunks = []
        while True:
            try:
                data = sock.recv(4096)
            except TimeoutError:
                break
            if not data:
                break
            chunks.append(data)
            if b"\r\n\r\n" in b"".join(chunks):
                break
    return b"".join(chunks)


def test_server_serves_over_a_real_socket(running_server: Server) -> None:
    svc, host, port = running_server
    svc.handle("POST", "/load", b'{"slots": 1, "min_service_ms": 1}')
    base = f"http://{host}:{port}"
    with urllib.request.urlopen(f"{base}/healthz", timeout=5) as resp:
        assert resp.status == 200 and resp.read() == b"ok\n"
    req = urllib.request.Request(
        f"{base}/admit",
        data=json.dumps({"workload_id": WORKLOAD_ID, "request_id": "r1"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert json.loads(resp.read())["admission"] == "admit"


def test_bad_content_length_returns_400_not_crash(
    running_server: Server,
) -> None:
    _svc, host, port = running_server
    # Every malformed Content-Length must 400 + close (never crash the thread, never desync):
    #   non-numeric, negative, underscore, plus-sign, a Unicode digit (isdigit() True but int()
    #   raises), a value over the body cap, and a string past int()'s 4300-digit limit.
    for value in (b"abc", b"-5", b"1_0", b"+10", b"\xb2", b"999999999999", b"9" * 4301):
        bad = b"POST /admit HTTP/1.1\r\nHost: x\r\nContent-Length: " + value + b"\r\n\r\n"
        resp = _raw_request(host, port, bad)
        assert b"400" in resp.split(b"\r\n", 1)[0], (value[:16], resp[:80])
        assert b"connection: close" in resp.lower(), (value[:16], resp[:200])
    # a fresh connection still works (the server thread did not die)
    with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=5) as r:
        assert r.status == 200


def test_handler_sets_a_socket_timeout(make_service: Factory) -> None:
    # A withheld/slow body must not tie up a thread forever — the handler sets a connection timeout.
    handler = make_handler(make_service())
    assert getattr(handler, "timeout", None) == 15


def test_chunked_body_returns_400(running_server: Server) -> None:
    _svc, host, port = running_server
    chunked = b"POST /admit HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
    resp = _raw_request(host, port, chunked)
    assert b"400" in resp.split(b"\r\n", 1)[0], resp[:80]
    assert b"connection: close" in resp.lower(), resp[:200]  # closed -> no keep-alive desync


def test_concurrent_admits_are_serialized(
    running_server: Server,
) -> None:
    svc, host, port = running_server
    svc.handle("POST", "/load", b'{"slots": 100, "min_service_ms": 1}')  # ample L2 capacity
    base = f"http://{host}:{port}"
    results: list[str] = []
    lock = threading.Lock()

    def fire(i: int) -> None:
        req = urllib.request.Request(
            f"{base}/admit",
            data=json.dumps({"workload_id": WORKLOAD_ID, "request_id": f"c{i}"}).encode(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp, lock:
            results.append(json.loads(resp.read())["throttle"])

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(results) == 24  # every concurrent request got a well-formed response, no crash
    passed = svc.handle("GET", "/snapshot")
    l3 = json.loads(passed.body)["l3"]
    # under the lock, L3 pass + throttle counts account for all 24 (no lost/torn updates)
    assert l3["passed"] + l3["throttled"] == 24


def test_handle_holds_lock_while_dispatching(make_service: Factory) -> None:
    # Deterministic gate for the thread-safety fix (the GIL can mask the concurrency test): handle()
    # must hold self._lock while it dispatches, so removing `with self._lock` fails HERE.
    svc = make_service()
    observed: list[bool] = []
    original = svc._dispatch

    def spy(method: str, path: str, body: bytes = b"") -> object:
        observed.append(svc._lock.locked())
        return original(method, path, body)

    svc._dispatch = spy  # type: ignore[assignment]
    svc.handle("GET", "/healthz")
    assert observed == [True], "handle() did not hold the lock while dispatching"


def test_build_from_env_loads_ir(
    tmp_path: Path, ir: MissionIR, monkeypatch: pytest.MonkeyPatch
) -> None:
    ir_path = tmp_path / "ir.json"
    ir_path.write_text(ir.model_dump_json(indent=2), encoding="utf-8")
    monkeypatch.setenv("MQI_IR_PATH", str(ir_path))
    service = build_from_env()
    assert service.handle("GET", "/healthz").status == 200
