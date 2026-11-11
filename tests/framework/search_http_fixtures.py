"""Local HTTP fault server for actual fixed PHP; never an Elasticsearch substitute."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time
from threading import Thread
from typing import Any, Iterator
from urllib.parse import urlsplit


class SearchServer:
    def __init__(self, fault: str) -> None:
        self.fault = fault
        self.calls: list[tuple[str, str]] = []
        self.indices = ["catalog", "extra"]
        self.deleted: list[str] = []
        self.restored = False
        self.streams: dict[str, list[str]] = {}
        self.deleted_streams: list[str] = []
        self.ilm = "STOPPED"
        self.repository_exists = True
        self.record: dict[str, Any] = dict(
            cluster_uuid="original-cluster",
            version="7.17.0",
            repository="lab_admin_recovery",
            snapshot="baseline",
            snapshot_uuid="original-snapshot",
            indices=["catalog"],
            data_streams=[],
            shards=1,
        )

    def response(self, method: str, target: str) -> tuple[int, Any]:
        path = urlsplit(target).path
        self.calls.append((method, path))
        if path == "/":
            if self.fault == "blocked":
                time.sleep(1)
            return 200, dict(
                cluster_uuid=(
                    "other"
                    if self.fault == "cluster_changed" and self.deleted
                    else "original-cluster"
                ),
                version=dict(
                    number="8.0.0" if self.fault == "unsupported_version" else "7.17.0"
                ),
            )
        if path == "/_ilm/stop":
            self.ilm = "STOPPING" if self.fault == "ilm_stuck" else "STOPPED"
            return 200, dict(acknowledged=self.fault != "stop_unconfirmed")
        if path == "/_ilm/status":
            return 200, dict(operation_mode=self.ilm)
        if path == "/_data_stream":
            return 200, dict(
                data_streams=[
                    dict(
                        name=name, indices=[dict(index_name=index) for index in members]
                    )
                    for name, members in self.streams.items()
                ]
            )
        if method == "DELETE" and path.startswith("/_data_stream/"):
            name = path.removeprefix("/_data_stream/")
            self.deleted_streams.append(name)
            for index in self.streams.pop(name):
                self.indices.remove(index)
            return 200, dict(acknowledged=self.fault != "stream_unconfirmed")
        if path == "/_snapshot/lab_admin_recovery":
            if method == "PUT":
                self.repository_exists = True
                return 200, dict(acknowledged=True)
            if not self.repository_exists:
                return 404, {"error": "repository missing"}
            return 200, {
                "lab_admin_recovery": {
                    "type": "fs",
                    "settings": {
                        "location": (
                            "/wrong"
                            if self.fault == "wrong_repository"
                            else "/state/elasticsearch/snapshots"
                        )
                    },
                }
            }
        if path == "/_snapshot/lab_admin_recovery/baseline":
            snap = dict(
                snapshot="baseline",
                state="PARTIAL" if self.fault == "partial_snapshot" else "SUCCESS",
                include_global_state=True,
                failures=[],
                uuid="other" if self.fault == "wrong_snapshot" else "original-snapshot",
                version="7.17.0",
                shards=dict(total=1, successful=1, failed=0),
                indices=self.record["indices"],
                data_streams=self.record["data_streams"],
            )
            if self.fault == "snapshot_http":
                return 503, {"error": "unavailable"}
            if self.fault == "snapshot_missing":
                return 404, {"error": "missing"}
            if method == "PUT":
                if self.fault == "save_inventory_changed":
                    self.indices.append("unexpected")
                if self.fault == "save_streams_changed":
                    self.streams = {}
                return 200, dict(snapshot=snap)
            return 200, dict(snapshots=[snap])
        if path == "/_cat/indices":
            values = self.indices
            if self.fault == "wildcard":
                values = ["*"]
            if self.fault == "duplicates":
                values = ["catalog", "catalog"]
            return 200, [
                dict(
                    index=n, status="close" if self.fault == "closed_index" else "open"
                )
                for n in values
            ]
        if method == "DELETE":
            if any(path[1:] == members[-1] for members in self.streams.values()):
                return 400, {"error": "cannot delete data stream write index"}
            if self.fault == "delete_failure" and self.deleted:
                return 500, {"error": "delete failed"}
            self.deleted.append(path[1:])
            self.indices.remove(path[1:])
            return 200, dict(
                acknowledged=False if self.fault == "delete_unconfirmed" else True
            )
        if path.endswith("/_restore"):
            if self.fault == "restore_failure":
                return 500, {"error": "restore failed"}
            self.restored = True
            self.indices = list(self.record["indices"])
            if self.record["data_streams"]:
                self.streams = {"events": [".ds-events-000001"]}
            if self.fault == "wrong_final_indices":
                self.indices.append("extra")
            return 200, dict(
                snapshot=dict(
                    shards=dict(
                        total=1,
                        successful=0 if self.fault == "failed_shard" else 1,
                        failed=1 if self.fault == "failed_shard" else 0,
                    )
                )
            )
        if path == "/_cluster/health":
            return 200, dict(
                status="red" if self.fault == "red_health" else "yellow",
                timed_out=self.fault == "health_timeout",
            )
        return 500, dict(error="unexpected route")


@contextmanager
def search_server(fault: str) -> Iterator[tuple[SearchServer, int]]:
    state = SearchServer(fault)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def handle_request(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            status, value = state.response(self.command, self.path)
            raw = json.dumps(value, separators=(",", ":")).encode()
            if state.fault == "bad_json" and self.path == "/":
                raw = b"{bad"
            if state.fault == "oversize" and self.path == "/":
                raw = b"x" * 1048577
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_PUT = handle_request
        do_GET = handle_request
        do_POST = handle_request
        do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
