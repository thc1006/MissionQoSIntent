"""Run the admission service over HTTP: `python -m mqi.serve` (configured from the environment).

Environment:
  MQI_IR_PATH       path to a compiled `ir.json` (required) — the tenant group this pod admits for
  MQI_LISTEN        host:port to bind (default 0.0.0.0:8080)
  MQI_MAX_QUEUE     L2 deferred-queue bound (default 64)
  MQI_BURST_SECONDS L3 token-bucket burst window in seconds (default 1.0)

Routes: GET /healthz /metrics /snapshot; POST /admit /tick /load /saturation.
See `AdmissionService` for the request/response shapes.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mqi.ir import MissionIR
from mqi.serve.service import AdmissionService

# Admission requests are tiny JSON ({workload_id, request_id, ...}); cap the body so a huge declared
# Content-Length can't force an unbounded read (memory/thread-exhaustion DoS).
_MAX_BODY_BYTES = 65536


def build_from_env() -> AdmissionService:
    """Construct the service from the environment (raises KeyError if MQI_IR_PATH is unset)."""
    ir = MissionIR.model_validate_json(Path(os.environ["MQI_IR_PATH"]).read_text(encoding="utf-8"))
    return AdmissionService(
        ir,
        max_queue=int(os.environ.get("MQI_MAX_QUEUE", "64")),
        burst_seconds=float(os.environ.get("MQI_BURST_SECONDS", "1.0")),
    )


def make_handler(service: AdmissionService) -> type[BaseHTTPRequestHandler]:
    """Build a request-handler class bound to `service` (dispatches every GET/POST to it)."""

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 15  # per-connection socket timeout: a withheld/slow body frees the thread

        def _reply(self, status: int, body: str, content_type: str, *, close: bool = False) -> None:
            payload = body.encode("utf-8")
            if close:
                self.close_connection = True  # end the keep-alive conn (framing unknown/broken)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            if close:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def _bad_framing(self, msg: str) -> None:
            # 400 AND close: the body's end is unknown on this keep-alive HTTP/1.1 connection, so
            # leftover bytes would desync the next request — close instead of leaving them unread.
            self._reply(400, '{"error": "' + msg + '"}', "application/json", close=True)

        def _dispatch(self, method: str) -> None:
            if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
                self._bad_framing("chunked bodies not supported")  # we don't decode chunked
                return
            # Canonical framing only. An absent/empty header defaults to "0" (zero-length body).
            # isascii()+isdigit() rejects -5, +10, 1_0, " 10 " AND Unicode digits like "²" (which
            # isdigit() alone accepts but int() cannot parse); int() is still guarded because a
            # 4300+-digit all-ASCII string passes isdigit() yet overflows the int-string limit.
            raw_len = self.headers.get("Content-Length", "0") or "0"
            if not (raw_len.isascii() and raw_len.isdigit()):
                self._bad_framing("invalid Content-Length header")
                return
            try:
                length = int(raw_len)
            except ValueError:
                self._bad_framing("invalid Content-Length header")
                return
            if length > _MAX_BODY_BYTES:
                self._bad_framing("request body too large")
                return
            body = self.rfile.read(length)
            resp = service.handle(method, self.path, body)
            self._reply(resp.status, resp.body, resp.content_type)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def log_message(self, format: str, *args: object) -> None:
            return  # quiet by default; the harness reads /metrics, not access logs

    return _Handler


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - socket serve loop
    """Bind MQI_LISTEN and serve forever; Ctrl-C / SIGTERM exits cleanly."""
    host, _, port = os.environ.get("MQI_LISTEN", "0.0.0.0:8080").rpartition(":")
    handler = make_handler(build_from_env())
    server = ThreadingHTTPServer((host or "0.0.0.0", int(port or "8080")), handler)
    print(f"mqi-serve: listening on {server.server_address}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
